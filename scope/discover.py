"""Découverte réseau du scope par scan de sous-réseau (port SCPI 5025).

Approche simple sans dépendance : TCP-connect chaque hôte du CIDR sur le port
5025, envoyer ``*IDN?``, retenir les réponses qui s'identifient comme Siglent.
Alternative à la découverte VXI-11/mDNS (nécessiterait ``python-vxi11`` ou
``zeroconf`` et passe mal sur un montage Ethernet direct sans routeur).
"""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor

SCPI_PORT = 5025
DEFAULT_TIMEOUT_S = 0.3


def is_siglent(idn: str) -> bool:
    """Vrai si une réponse ``*IDN?`` provient d'un appareil Siglent."""
    return "siglent" in idn.lower()


def local_ipv4_cidrs(addrs=None) -> list[str]:
    """Déduit les CIDR IPv4 des interfaces locales (hors loopback).

    ``addrs`` est le résultat de ``psutil.net_if_addrs()`` (injectable pour les
    tests) ; par défaut on l'interroge réellement.
    """
    if addrs is None:
        import psutil

        addrs = psutil.net_if_addrs()
    cidrs = []
    for snics in addrs.values():
        for snic in snics:
            if snic.family != socket.AF_INET or snic.address.startswith("127."):
                continue
            iface = ipaddress.ip_interface(f"{snic.address}/{snic.netmask}")
            cidrs.append(str(iface.network))
    return cidrs


def _probe(ip: str, *, port: int, timeout_s: float, connect) -> str | None:
    """Sonde une IP : renvoie sa réponse ``*IDN?`` si Siglent, sinon ``None``."""
    try:
        with connect((ip, port), timeout_s) as sock:
            sock.sendall(b"*IDN?\n")
            idn = sock.recv(4096).decode(errors="replace").strip()
    except OSError:
        return None
    return idn if is_siglent(idn) else None


def scan(
    cidr: str,
    *,
    port: int = SCPI_PORT,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    connect=socket.create_connection,
    max_workers: int = 32,
) -> list[tuple[str, str]]:
    """Scanne un CIDR (ex. ``"10.11.13.0/24"``) et renvoie les scopes Siglent trouvés.

    ``connect`` est injectable (défaut ``socket.create_connection``) pour les
    tests sans réseau réel. Retourne une liste triée de ``(ip, idn)``.
    """
    hosts = [str(ip) for ip in ipaddress.ip_network(cidr, strict=False).hosts()]
    found: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(
            lambda ip: (ip, _probe(ip, port=port, timeout_s=timeout_s, connect=connect)),
            hosts,
        )
        for ip, idn in results:
            if idn is not None:
                found.append((ip, idn))
    return sorted(found)
