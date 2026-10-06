"""Récupération et décodage des waveforms du SDS1004X-E.

Méthode robuste validée sur le matériel : on lit le **descripteur** WAVEDESC
(``C<n>:WF? DESC``, bloc binaire de 346 octets) qui contient toutes les échelles,
puis les **données** (``C<n>:WF? DAT2``, octets signés int8). La conversion suit
la formule Siglent ::

    volt   = code * (vdiv / 25) - offset
    t[i]   = (i - n/2) * interval        (intervalle = 1 / SARA, centré sur le trigger)

Les lectures binaires passent par :meth:`scope.Scope.query_block` (lecture par
octets exacts) pour éviter toute désynchronisation due aux ``\\n`` internes.

La fonction :func:`decode` est *pure* (octets/codes + échelles → numpy), testable
sans matériel.
"""

from __future__ import annotations

import csv
import re
import struct
from dataclasses import dataclass

import numpy as np

VERT_CODES_PER_DIV = 25  # codes ADC par division verticale (Siglent X-E)

# Décalages dans le bloc WAVEDESC (à partir du marqueur "WAVEDESC"), little-endian.
_OFF_WAVE_ARRAY_COUNT = 116  # i32 : nombre de points
_OFF_VERTICAL_GAIN = 156     # f32 : volts/div (VDIV)
_OFF_VERTICAL_OFFSET = 160   # f32 : offset vertical (OFST), en volts
_OFF_HORIZ_INTERVAL = 176    # f32 : intervalle d'échantillonnage (s) = 1/SARA

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


@dataclass
class Waveform:
    """Une trace décodée : axes temps (s) et tension (V) + métadonnées.

    ``label``/``unit``/``factor`` : réglage d'affichage/export de la voie (cf.
    ``channel_config.ChannelConfig``), à défaut neutre (pas de nom, volts,
    facteur 1) -- ``decode``/``fetch`` restent en volts bruts, la conversion
    est appliquée par l'appelant via :func:`dataclasses.replace` (cf. gui.py).
    """

    channel: str
    time: np.ndarray
    volts: np.ndarray
    vdiv: float
    offset: float
    interval: float
    label: str = ""
    unit: str = "V"
    factor: float = 1.0

    @property
    def sample_rate(self) -> float:
        return 1.0 / self.interval if self.interval else float("inf")

    @property
    def values(self) -> np.ndarray:
        """Valeurs converties (``volts * factor``) dans ``unit``."""
        return self.volts * self.factor

    @property
    def display_name(self) -> str:
        """Nom affiché : ``label`` s'il est renseigné, sinon ``channel``."""
        return self.label or self.channel


def parse_float(response: str) -> float:
    """Extrait le premier flottant d'une réponse SCPI (suffixe d'unité ignoré).

    On ne regarde que le dernier token pour éviter de capter le chiffre du nom de
    voie (``"C1:OFST -1.5V"`` ne doit pas renvoyer le « 1 » de ``C1``).
    """
    token = response.split()[-1] if response.split() else response
    match = _FLOAT_RE.search(token)
    if match is None:
        raise ValueError(f"aucune valeur numérique dans {response!r}")
    return float(match.group())


def parse_descriptor(desc: bytes) -> dict:
    """Extrait les échelles du bloc WAVEDESC : vdiv, offset, interval, count."""
    start = desc.find(b"WAVEDESC")
    if start < 0:
        raise ValueError("WAVEDESC introuvable dans le descripteur")
    d = desc[start:]
    return {
        "count": struct.unpack_from("<i", d, _OFF_WAVE_ARRAY_COUNT)[0],
        "vdiv": struct.unpack_from("<f", d, _OFF_VERTICAL_GAIN)[0],
        "offset": struct.unpack_from("<f", d, _OFF_VERTICAL_OFFSET)[0],
        "interval": struct.unpack_from("<f", d, _OFF_HORIZ_INTERVAL)[0],
    }


def parse_block(raw: bytes) -> np.ndarray:
    """Décode un bloc binaire IEEE-488.2 ``...#<n><len><données>`` en codes int8.

    Utile pour traiter une réponse brute complète (avec en-tête). Quand on lit via
    :meth:`Scope.query_block`, l'en-tête est déjà retiré : passer directement les
    octets à :func:`decode`.
    """
    marker = raw.find(b"#")
    if marker < 0:
        raise ValueError("bloc IEEE introuvable (pas de '#')")
    ndigits = int(raw[marker + 1 : marker + 2])
    len_start = marker + 2
    data_start = len_start + ndigits
    nbytes = int(raw[len_start:data_start])
    payload = raw[data_start : data_start + nbytes]
    if len(payload) != nbytes:
        raise ValueError(f"bloc tronqué : {len(payload)} octets reçus, {nbytes} attendus")
    return np.frombuffer(payload, dtype=np.int8).astype(np.float64)


def decode(
    codes, vdiv: float, offset: float, interval: float, channel: str = "C1", time=None
) -> Waveform:
    """Convertit des codes (octets int8 ou tableau) en :class:`Waveform`.

    ``codes`` : charge utile de ``DAT2`` (octets, sans en-tête) ou tableau de codes.

    ``time`` : axe temps déjà calculé (même longueur que ``codes``), à réutiliser
    tel quel plutôt que de le reconstruire -- optimisation pour un appelant qui
    répète les mêmes ``n``/``interval`` d'une frame à l'autre (cf.
    ``gui.DescriptorCache``, qui met en cache le descripteur *et* cet axe pour
    l'affichage temps réel/série sur mémoire profonde). ``None`` (défaut) :
    calculé comme avant, comportement inchangé pour un appel ponctuel
    (:func:`fetch`).
    """
    if isinstance(codes, (bytes, bytearray)):
        arr = np.frombuffer(codes, dtype=np.int8).astype(np.float64)
    else:
        arr = np.asarray(codes, dtype=np.float64)

    volts = arr * (vdiv / VERT_CODES_PER_DIV) - offset
    n = len(volts)
    if time is None:
        time = (np.arange(n) - n / 2.0) * interval  # centré sur le trigger
    return Waveform(channel, time, volts, vdiv, offset, interval)


def fetch_descriptor(scope, channel: str = "C1") -> dict:
    """Lit et parse uniquement le descripteur (``WF? DESC``), sans les données.

    Utile pour mettre en cache vdiv/offset/interval entre deux frames quand les
    réglages n'ont pas changé (cf. ``gui.DescriptorCache``) : DESC coûte à peu
    près aussi cher que DAT2 pour un petit payload (mesuré,
    ``tools/profile_capture.py``), donc l'économiser à chaque frame divise par
    ~2 le nombre de requêtes en régime stable.

    Lève ``ValueError`` si la voie ne contient aucun échantillon (acquisition vide).
    """
    desc = scope.query_block(f"{channel}:WF? DESC")
    p = parse_descriptor(desc)
    if p["count"] <= 0:
        raise ValueError(
            f"{channel} : acquisition vide (aucun échantillon). "
            "Vérifier qu'un signal est présent et que le scope déclenche."
        )
    return p


def fetch_data(scope, channel: str, desc: dict, time=None) -> Waveform:
    """Lit uniquement les données (``WF? DAT2``) et décode avec un descripteur déjà connu.

    ``desc`` doit provenir d'un appel précédent à :func:`fetch_descriptor` sur
    la **même configuration** (TDIV/VDIV/OFST/couplage) : c'est à l'appelant
    d'invalider son cache dès qu'un réglage qui affecte les échelles change
    (cf. ``gui.DescriptorCache``). Ne vérifie pas ici que ``desc`` est encore
    valide -- c'est le rôle de l'appelant (ou de :class:`gui.DescriptorCache`,
    qui recoupe ``desc["count"]`` avec la taille réellement reçue).

    ``time`` : axe temps déjà calculé pour ce ``desc``, transmis tel quel à
    :func:`decode` (voir sa docstring) -- l'appelant garantit qu'il correspond
    bien à ce descripteur.
    """
    data = scope.query_block(f"{channel}:WF? DAT2")
    return decode(data, desc["vdiv"], desc["offset"], desc["interval"], channel, time=time)


def fetch(scope, channel: str = "C1") -> Waveform:
    """Lit le descripteur puis les données d'une voie et décode la trace.

    Le nombre de points transmis dépend de ``WFSU NP`` (cf.
    ``control.set_waveform_points``) mais n'affecte pas la formule de
    décodage : les points renvoyés restent à l'intervalle natif du descripteur
    (``NP`` tronque, il ne décime pas), donc aucun ajustement n'est nécessaire
    ici.

    Instantané simple (pas de cache) : pour une boucle qui répète les mêmes
    réglages frame après frame, préférer :func:`fetch_descriptor` une fois +
    :func:`fetch_data` en boucle (ou ``gui.DescriptorCache``).

    Lève ``ValueError`` si la voie ne contient aucun échantillon (acquisition vide).
    """
    p = fetch_descriptor(scope, channel)
    return fetch_data(scope, channel, p)


def decimate(time_arr, volts_arr, max_points: int = 4000):
    """Sous-échantillonne pour l'affichage/export léger, en gardant le dernier point.

    Fonction pure (déplacée de ``gui.py`` le 2026-07-13 pour être réutilisable
    hors GUI, ex. ``series.py``, sans tirer PyQt/pyqtgraph dans un chemin
    headless). ``gui.py``/``live.py`` la ré-importent depuis ici pour l'affichage
    temps réel ; comportement inchangé.
    """
    t = np.asarray(time_arr)
    v = np.asarray(volts_arr)
    n = len(t)
    if n <= max_points:
        return t, v
    step = max(1, n // max_points)
    dt, dv = t[::step], v[::step]
    if dt[-1] != t[-1]:
        dt = np.append(dt, t[-1])
        dv = np.append(dv, v[-1])
    return dt, dv


def _save_csv(wf: Waveform, path_base: str) -> str:
    path = f"{path_base}.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time_s", f"{wf.display_name}_{wf.unit}"])
        writer.writerows(zip(wf.time.tolist(), wf.values.tolist()))
    return path


def _save_npy(wf: Waveform, path_base: str) -> str:
    path = f"{path_base}.npy"
    np.save(path, np.column_stack([wf.time, wf.values]))
    return path


def _save_npz(wf: Waveform, path_base: str) -> str:
    path = f"{path_base}.npz"
    np.savez_compressed(
        path,
        time=wf.time,
        volts=wf.volts,
        values=wf.values,
        vdiv=wf.vdiv,
        offset=wf.offset,
        interval=wf.interval,
        channel=wf.channel,
        label=wf.label,
        unit=wf.unit,
        factor=wf.factor,
    )
    return path


def _save_hdf5(wf: Waveform, path_base: str) -> str:
    try:
        import h5py
    except ImportError as exc:
        raise ImportError(
            "export HDF5 nécessite h5py (pip install h5py)"
        ) from exc
    path = f"{path_base}.h5"
    with h5py.File(path, "w") as fh:
        fh.create_dataset("time", data=wf.time)
        fh.create_dataset("volts", data=wf.volts)
        fh.create_dataset("values", data=wf.values)
        fh.attrs["vdiv"] = wf.vdiv
        fh.attrs["offset"] = wf.offset
        fh.attrs["interval"] = wf.interval
        fh.attrs["channel"] = wf.channel
        fh.attrs["label"] = wf.label
        fh.attrs["unit"] = wf.unit
        fh.attrs["factor"] = wf.factor
    return path


def _save_mat(wf: Waveform, path_base: str) -> str:
    try:
        from scipy.io import savemat
    except ImportError as exc:
        raise ImportError(
            "export MAT nécessite scipy (pip install scipy)"
        ) from exc
    path = f"{path_base}.mat"
    savemat(
        path,
        {
            "time": wf.time,
            "volts": wf.volts,
            "values": wf.values,
            "vdiv": wf.vdiv,
            "offset": wf.offset,
            "interval": wf.interval,
            "channel": wf.channel,
            "label": wf.label,
            "unit": wf.unit,
            "factor": wf.factor,
        },
    )
    return path


def save_combined_csv(waveforms: list[Waveform], path_base: str) -> str:
    """Un seul CSV multi-colonnes pour plusieurs voies de la même acquisition.

    En-tête : ``time_s, <display_name1>_<unit1>, <display_name2>_<unit2>, ...``
    (``display_name`` = label configuré, sinon nom de voie brut). L'axe temps
    de la **première** waveform est réutilisé pour toutes les colonnes -- les
    voies d'une même capture partagent la même base de temps/acquisition.

    Lève ``ValueError`` si ``waveforms`` est vide, ou si les voies n'ont pas
    toutes le même nombre de points (axes incompatibles, ex. voies issues
    d'acquisitions différentes) -- pas d'alignement silencieux de colonnes
    dépareillées.
    """
    if not waveforms:
        raise ValueError("aucune waveform à sauver")
    n = len(waveforms[0].time)
    for wf in waveforms:
        if len(wf.time) != n:
            raise ValueError(
                f"axes temps incompatibles ({wf.channel} : {len(wf.time)} pts, "
                f"attendu {n}) -- voies issues d'acquisitions différentes ?"
            )
    path = f"{path_base}.csv"
    header = ["time_s"] + [f"{wf.display_name}_{wf.unit}" for wf in waveforms]
    columns = [waveforms[0].time.tolist()] + [wf.values.tolist() for wf in waveforms]
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(zip(*columns))
    return path


def save_capture(waveforms: list[Waveform], path_base: str, formats=("csv", "npy")) -> list[str]:
    """Sauve une capture multi-voies : un CSV **combiné** (une fois, si
    ``"csv"`` est demandé) + un fichier **par voie** pour les formats
    binaires restants (npy/npz/hdf5/mat, via :func:`save`, nommé
    ``f"{path_base}_{wf.channel}"``). Point d'entrée unique réutilisé par la
    GUI, la CLI et les séries -- DRY, un seul endroit qui décide de la forme
    d'une capture multi-voies.
    """
    binary_formats = [f for f in formats if f != "csv"]
    paths = []
    for wf in waveforms:
        if binary_formats:
            paths.extend(save(wf, f"{path_base}_{wf.channel}", formats=binary_formats))
    if "csv" in formats and waveforms:
        paths.append(save_combined_csv(waveforms, path_base))
    return paths


FORMAT_WRITERS = {
    "csv": _save_csv,
    "npy": _save_npy,
    "npz": _save_npz,
    "hdf5": _save_hdf5,
    "mat": _save_mat,
}
VALID_FORMATS = frozenset(FORMAT_WRITERS)


def save(wf: Waveform, path_base: str, formats=("csv", "npy")) -> list[str]:
    """Sauve la trace dans un ou plusieurs formats. Retourne les chemins écrits.

    Formats disponibles : ``csv`` (lisible), ``npy`` (rapide, numpy natif),
    ``npz`` (numpy compressé, avec métadonnées), ``hdf5`` (nécessite h5py),
    ``mat`` (nécessite scipy). Défaut inchangé : ``csv`` + ``npy``.
    """
    paths = []
    for fmt in formats:
        if fmt not in VALID_FORMATS:
            raise ValueError(f"format invalide {fmt!r}, attendu {sorted(VALID_FORMATS)}")
        paths.append(FORMAT_WRITERS[fmt](wf, path_base))
    return paths
