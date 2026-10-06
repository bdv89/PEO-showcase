"""Tests de la découverte réseau (scan port 5025) — exécutables sans matériel.

La connexion socket réelle est injectée (paramètre ``connect``) : aucun accès
réseau dans ces tests.
"""

import pytest

from scope.discover import is_siglent, local_ipv4_cidrs, scan


# --- is_siglent ------------------------------------------------------------------
def test_is_siglent_true():
    assert is_siglent("Siglent Technologies,SDS1204X-E,SDS1EBAQ1R0001,1.3.9R6")


def test_is_siglent_false():
    assert not is_siglent("Some Other Vendor,DSO-X,12345,1.0")


def test_is_siglent_empty():
    assert not is_siglent("")


# --- scan --------------------------------------------------------------------------
class _FakeSocket:
    """Simule une connexion TCP : query() renvoie une réponse cannée ou lève."""

    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.sent = None
        self.closed = False

    def sendall(self, data):
        self.sent = data

    def recv(self, n):
        return self._response.encode() if self._response else b""

    def settimeout(self, t):
        pass

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _make_connect(hosts):
    """hosts: dict ip -> réponse *IDN? (ou None -> lève ConnectionRefusedError)."""

    def connect(addr, timeout):
        ip, port = addr
        if ip not in hosts or hosts[ip] is None:
            raise ConnectionRefusedError(f"pas d'hôte à {ip}")
        return _FakeSocket(response=hosts[ip])

    return connect


def test_scan_finds_siglent_only():
    hosts = {
        "10.11.13.1": None,
        "10.11.13.2": "Siglent Technologies,SDS1204X-E,SN1,1.0",
        "10.11.13.3": "Other Vendor,X,1,1.0",
    }
    result = scan("10.11.13.0/29", connect=_make_connect(hosts))
    assert result == [("10.11.13.2", "Siglent Technologies,SDS1204X-E,SN1,1.0")]


def test_scan_no_match_returns_empty():
    hosts = {"10.11.13.1": None, "10.11.13.2": None}
    assert scan("10.11.13.0/29", connect=_make_connect(hosts)) == []


# --- local_ipv4_cidrs ---------------------------------------------------------------
class _Snic:
    """Imite ``psutil._common.snicaddr`` (seuls les champs utilisés sont fournis)."""

    def __init__(self, family, address, netmask):
        self.family = family
        self.address = address
        self.netmask = netmask


def test_local_ipv4_cidrs_filters_private_ipv4():
    import socket as _socket

    addrs = {
        "enp0s31f6": [
            _Snic(_socket.AF_INET, "10.11.13.10", "255.255.255.0"),
            _Snic(_socket.AF_INET6, "fe80::1", "ffff:ffff:ffff:ffff::"),
        ],
        "lo": [_Snic(_socket.AF_INET, "127.0.0.1", "255.0.0.0")],
    }
    assert local_ipv4_cidrs(addrs) == ["10.11.13.0/24"]


def test_local_ipv4_cidrs_empty_without_interfaces():
    assert local_ipv4_cidrs({}) == []


def test_scan_timeouts_do_not_stop_scan():
    def connect(addr, timeout):
        ip, port = addr
        if ip == "10.11.13.2":
            return _FakeSocket(response="Siglent Technologies,SDS1204X-E,SN1,1.0")
        raise TimeoutError("no response")

    result = scan("10.11.13.0/29", connect=connect)
    assert result == [("10.11.13.2", "Siglent Technologies,SDS1204X-E,SN1,1.0")]
