"""Connexion VISA au scope Siglent sur LAN ou USB (SCPI).

Trois transports possibles, abstraits par PyVISA via la « resource string » :
  - VXI-11  : ``TCPIP::<ip>::INSTR``        (défaut — gère proprement les blocs
              binaires grâce au flag END, idéal pour lire les waveforms)
  - Socket  : ``TCPIP::<ip>::5025::SOCKET`` (terminaison '\\n' ; fragile en binaire)
  - USB     : ``USB0::<vid>::<pid>::<serial>::INSTR`` (USBTMC, cf. :func:`find_usb_resource`)
"""

from __future__ import annotations

import struct

DEFAULT_TIMEOUT_MS = 10_000
SOCKET_PORT = 5025
# Les waveforms peuvent faire plusieurs Mo (mémoire profonde) : large chunk.
# Valable pour VXI-11/socket (chunking logiciel côté pyvisa-py, pas de limite
# noyau). ⚠️ PAS pour USB, cf. USB_CHUNK_SIZE ci-dessous.
CHUNK_SIZE = 32 * 1024 * 1024
# USBTMC (pyvisa-py + pyusb/libusb) soumet des transferts bulk dimensionnés sur
# ce chunk_size directement au noyau via usbfs -- contrairement à VXI-11/socket
# qui ne s'en servent que pour boucler des lectures logicielles. Le noyau Linux
# plafonne la mémoire totale allouable aux URBs usbfs à `usbfs_memory_mb`
# (constaté : 16 Mio sur ce système, cf. /sys/module/usbcore/parameters/
# usbfs_memory_mb) ; demander CHUNK_SIZE (32 Mio) dépasse ce plafond et
# `read_bytes` échoue avec ``usb.core.USBError: [Errno 12] Insufficient
# memory`` dès la première lecture -- reproduit sur matériel, 2026-07-13.
# 1 Mio reste très confortablement sous la limite par défaut (16 Mio, parfois
# plus bas sur d'autres systèmes) tout en restant largement supérieur à la
# taille d'un WAVEDESC (346 o) ou d'un paquet USB (quelques centaines d'octets).
USB_CHUNK_SIZE = 1 * 1024 * 1024
# Le dernier read_bytes(1) de _drain_terminator attend TOUJOURS ce timeout en
# entier (il n'y a plus rien à lire, il faut échouer pour savoir qu'on a fini) :
# c'est un coût fixe payé à CHAQUE query_block. Le firmware n'envoie que 1-2
# octets de terminaison collés au payload (même paquet réseau) : quelques ms
# suffisent très largement. Mesuré (profile_capture.py) : à 150ms, ce drain
# expliquait à lui seul l'essentiel du coût d'un petit DESC/DAT2 (~0,18s).
DRAIN_TIMEOUT_MS = 30
# Timeout du flush_input() à l'ouverture -- ne s'exécute qu'une fois par
# connexion (pas dans la boucle chaude), pas d'urgence à le réduire.
FLUSH_TIMEOUT_MS = 120
# Identifiants USB du SDS1204X-E (cf. `lsusb` : "f4ec:ee38 ... Siglent ... DSO").
USB_VENDOR_ID = 0xF4EC
USB_PRODUCT_ID = 0xEE38


def _bmp_payload_size(data: bytes) -> int:
    """Longueur déclarée du fichier BMP (champ ``bfSize``, offset 2, u32 little-endian).

    Sert à tronquer un résidu de terminaison ajouté par le firmware après ``SCDP``
    (constaté sur matériel : un octet ``\\n`` de trop, même famille de piège que les
    ``\\n``/``\\n\\n`` traînant après les blocs ``WF? DAT2``). L'en-tête BMP est
    autoritaire sur la taille réelle : tout ce qui dépasse est un artefact de
    transport, jamais des données d'image légitimes.
    """
    return struct.unpack_from("<I", data, 2)[0]


def resource_string(ip: str, *, socket: bool = False, port: int = SOCKET_PORT) -> str:
    """Construit la resource string VISA pour une adresse IP."""
    if socket:
        return f"TCPIP::{ip}::{port}::SOCKET"
    return f"TCPIP::{ip}::INSTR"


def _usb_resource_matches(resource: str, vendor_id: int, product_id: int) -> bool:
    """``True`` si ``resource`` (ex. ``USB0::62700::60984::SER::0::INSTR``) porte ce VID:PID.

    Les segments 2 et 3 (index 1, 2 après split sur ``::``) portent VID puis PID,
    en décimal ou en hex ``0x...`` selon l'implémentation VISA -- ``int(s, 0)``
    gère les deux sans ambiguïté.
    """
    parts = resource.split("::")
    if len(parts) < 3:
        return False
    try:
        return int(parts[1], 0) == vendor_id and int(parts[2], 0) == product_id
    except ValueError:
        return False


def find_usb_resource(resource_manager, *, vendor_id: int = USB_VENDOR_ID, product_id: int = USB_PRODUCT_ID) -> str:
    """Découvre la resource string USBTMC du scope branché (VID:PID Siglent).

    La resource string USB VISA inclut un numéro de série que seul l'instrument
    connaît (``USB0::<vid>::<pid>::<serial>::INSTR``) : on ne peut pas la
    construire à la main, il faut l'obtenir via ``list_resources``.

    ⚠️ Filtrage fait manuellement sur les entiers VID/PID plutôt que par un motif
    VISA (``fnmatch``-style passé à ``list_resources``) : constaté sur matériel
    (2026-07-13) que ``pyvisa-py`` restitue les IDs en **décimal**, pas en hex
    (``USB0::62700::60984::SDSMMGKD903276::0::INSTR``, 6 champs avec un numéro
    d'interface avant ``INSTR``) — un motif ``0x{vid:04X}`` ne matche jamais,
    donc l'ancienne version ne trouvait jamais l'instrument même bien branché
    et autorisé (udev/plugdev en place). On demande large (``USB?*::INSTR``) et
    on compare les segments VID/PID convertis en entier (accepte les deux
    écritures, décimale ou ``0x`` hex, au cas où une autre implémentation VISA
    utilise l'hex).
    """
    matches = [r for r in resource_manager.list_resources("USB?*::INSTR") if _usb_resource_matches(r, vendor_id, product_id)]
    if not matches:
        raise RuntimeError(
            "aucun oscilloscope Siglent trouvé en USB (VID:PID "
            f"{vendor_id:04x}:{product_id:04x}) — vérifier le câble, que "
            "pyusb/libusb sont installés, et les droits udev "
            "(cf. docs/architecture.md)."
        )
    return matches[0]


class Scope:
    """Wrapper minimal autour d'une ressource VISA ouverte.

    Utilisable comme context manager ::

        with Scope("192.168.1.50") as s:
            print(s.idn())
    """

    def __init__(
        self,
        ip: str | None = None,
        *,
        socket: bool = False,
        usb: bool = False,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        resource_manager=None,
    ) -> None:
        # Import paresseux : permet de tester les modules de décodage sans pyvisa.
        import pyvisa

        self._owns_rm = resource_manager is None
        self._rm = resource_manager or pyvisa.ResourceManager("@py")
        if usb:
            # Pas d'IP en USB : la resource string se découvre (numéro de série
            # inconnu à l'avance), cf. find_usb_resource().
            self.resource = find_usb_resource(self._rm)
        else:
            self.resource = resource_string(ip, socket=socket)
        # open_timeout non précisé -> pyvisa-py établit la liaison VXI-11 (RPC
        # portmapper + create_link) avec VI_TMO_IMMEDIATE (0 ms), ce qui la fait
        # dégénérer en relances lentes côté RPC. On le borne explicitement au
        # même timeout que les I/O.
        self.inst = self._rm.open_resource(self.resource, open_timeout=timeout_ms)
        self.inst.timeout = timeout_ms
        self.inst.chunk_size = USB_CHUNK_SIZE if usb else CHUNK_SIZE
        if socket:
            self.inst.read_termination = "\n"
            self.inst.write_termination = "\n"
            self._enable_tcp_nodelay()
        if not usb:
            # Purge tout résidu laissé en file par une session précédente
            # (lecture binaire interrompue) -> évite le décalage d'une réponse.
            # Sauté en USB (constaté sur matériel, 2026-07-13) : sur ce
            # transport, un flush à vide (rien en attente juste après
            # l'ouverture) ne lève pas un ``pyvisa.errors.VisaIOError``
            # (seule exception attrapée par ``flush_input``) mais une
            # ``usb.core.USBError`` ("Pipe error") -- le mécanisme interne
            # d'abandon-sur-timeout de l'USBTMC de ``pyvisa-py`` échoue lui-
            # même. Une connexion USB fraîchement ouverte (numéro de série
            # redécouvert à chaque fois par ``find_usb_resource``) n'a de
            # toute façon pas le même risque de résidu qu'une liaison VXI-11/
            # socket persistante -- rien à purger.
            self.flush_input()

    def _enable_tcp_nodelay(self) -> None:
        """Désactive l'algorithme de Nagle sur le socket sous-jacent (transport socket).

        Best-effort : passe par une API interne non documentée de pyvisa-py
        (aucune API publique n'expose le socket). Échec silencieux si la
        structure change de version -- ce n'est qu'une micro-optimisation par
        aller-retour, jamais un pré-requis fonctionnel.
        """
        import socket as _socket

        try:
            session = self.inst.visalib.sessions[self.inst.session]
            session.interface.setsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)
        except Exception:
            pass

    # --- SCPI bas niveau (socle de la console) ---------------------------------
    def write(self, command: str) -> None:
        self.inst.write(command)

    def query(self, command: str) -> str:
        return self.inst.query(command).strip()

    def read_raw(self) -> bytes:
        return self.inst.read_raw()

    def query_block(self, command: str) -> bytes:
        """Écrit ``command`` puis lit la réponse comme un bloc IEEE-488.2 exact.

        Robuste pour les réponses binaires (waveform/descripteur) : on lit
        l'en-tête ``...#<n><len>``, exactement ``len`` octets, puis le
        terminateur. Évite que ``read_raw`` coupe le binaire sur un ``\\n``
        interne et laisse des octets en file (source de désynchronisation).
        Retourne uniquement la charge utile (octets de données).
        """
        self.inst.write(command)
        # Avance jusqu'au marqueur de bloc '#'.
        while self.inst.read_bytes(1) != b"#":
            pass
        ndigits = int(self.inst.read_bytes(1))
        nbytes = int(self.inst.read_bytes(ndigits))
        payload = self.inst.read_bytes(nbytes)
        self._drain_terminator()
        return payload

    def _drain_terminator(self) -> None:
        """Vide les octets de terminaison restants ('\\n' ou '\\n\\n').

        Lit octet par octet avec un timeout court : après une réponse, seuls des
        retours-ligne traînent, puis la lecture expire -> file propre. Marche
        pour VXI-11 comme pour socket (insensible au mode de terminaison).

        Le dernier ``read_bytes(1)`` (qui constate qu'il n'y a plus rien) attend
        tout le timeout avant d'échouer : c'est payé à chaque ``query_block``,
        donc ``DRAIN_TIMEOUT_MS`` doit rester court (les 1-2 octets de
        terminaison, quand ils existent, arrivent avec le payload dans le même
        paquet -- pas besoin de plusieurs dizaines de ms pour les voir)."""
        import pyvisa

        saved = self.inst.timeout
        self.inst.timeout = DRAIN_TIMEOUT_MS
        try:
            while self.inst.read_bytes(1) in (b"\n", b"\r"):
                pass
        except pyvisa.errors.VisaIOError:
            pass
        finally:
            self.inst.timeout = saved

    def flush_input(self) -> None:
        """Vide les octets en attente en entrée (résidu d'une session précédente).

        Lit en brut avec un timeout court jusqu'à ce qu'il n'y ait plus rien :
        nettoie tout reliquat d'une lecture binaire interrompue qui décalerait
        les réponses suivantes. Ne s'exécute qu'à l'ouverture (pas dans la
        boucle chaude) : pas de raison de le presser comme ``_drain_terminator``."""
        import pyvisa

        saved = self.inst.timeout
        self.inst.timeout = FLUSH_TIMEOUT_MS
        try:
            while True:
                self.inst.read_bytes(1)
        except pyvisa.errors.VisaIOError:
            pass
        finally:
            self.inst.timeout = saved

    def resync(self, expected: str = "Siglent", attempts: int = 20) -> None:
        """Purge la file de sortie en interrogeant ``*IDN?`` jusqu'à resync."""
        good = 0
        for _ in range(attempts):
            if self.query("*IDN?").startswith(expected):
                good += 1
                if good >= 2:
                    return
            else:
                good = 0

    def idn(self) -> str:
        return self.query("*IDN?")

    def screen_dump(self) -> bytes:
        """Dump de l'écran (SCPI ``SCDP``). Renvoie un BMP brut (commence par ``b'BM'``).

        Contrairement aux waveforms, ce n'est **pas** un bloc IEEE-488.2 (pas
        d'en-tête ``#<n><len>``) : le transfert est délimité par le flag END en
        VXI-11, donc ``read_raw()`` suffit. Fonctionne en mode socket aussi, mais
        VXI-11 (transport par défaut) est recommandé car il délimite proprement
        la fin de transfert sans dépendre d'une terminaison ``\\n``.

        Le firmware ajoute parfois un octet de terminaison résiduel après les
        données BMP (constaté sur matériel) : on tronque à la taille déclarée
        par l'en-tête BMP (``bfSize``), seule source fiable.
        """
        self.inst.write("SCDP")
        data = self.inst.read_raw()
        self.flush_input()
        return data[: _bmp_payload_size(data)]

    # --- cycle de vie ----------------------------------------------------------
    def close(self) -> None:
        try:
            self.inst.close()
        finally:
            if self._owns_rm:
                self._rm.close()

    def __enter__(self) -> "Scope":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
