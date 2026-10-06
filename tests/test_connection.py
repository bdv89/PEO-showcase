"""Tests de la couche connexion sans matériel (pas d'import pyvisa)."""

import struct

import pytest

from scope.connection import (
    DRAIN_TIMEOUT_MS,
    Scope,
    _bmp_payload_size,
    find_usb_resource,
)


class FakeInst:
    """Faux ``pyvisa`` resource : ``write`` + ``read_raw`` seulement."""

    def __init__(self, payload: bytes):
        self.written = []
        self._payload = payload
        self.flushed = False

    def write(self, cmd):
        self.written.append(cmd)

    def read_raw(self):
        return self._payload


def _bare_scope(payload: bytes) -> Scope:
    """Construit un ``Scope`` sans passer par ``__init__`` (pas de pyvisa réel)."""
    scope = Scope.__new__(Scope)
    scope.inst = FakeInst(payload)
    return scope


# --- USB : découverte de la resource string --------------------------------------
class FakeResourceManager:
    """Faux ``pyvisa.ResourceManager`` : seul ``list_resources`` est utilisé."""

    def __init__(self, resources=()):
        self._resources = resources
        self.queried_patterns = []

    def list_resources(self, pattern):
        self.queried_patterns.append(pattern)
        return self._resources


def test_find_usb_resource_returns_first_match():
    # Format réel observé sur matériel (pyvisa-py, 2026-07-13) : décimal, avec
    # un numéro d'interface avant INSTR -- pas de "0x" ni 5 champs comme on le
    # supposait avant mesure.
    rm = FakeResourceManager(resources=("USB0::62700::60984::SDS123::0::INSTR",))
    resource = find_usb_resource(rm)
    assert resource == "USB0::62700::60984::SDS123::0::INSTR"


def test_find_usb_resource_matches_hex_form_too():
    # Autre implémentation VISA possible (NI-VISA) : IDs en hex "0x...".
    rm = FakeResourceManager(resources=("USB0::0xF4EC::0xEE38::SDS123::0::INSTR",))
    resource = find_usb_resource(rm)
    assert resource == "USB0::0xF4EC::0xEE38::SDS123::0::INSTR"


def test_find_usb_resource_ignores_other_vendor():
    rm = FakeResourceManager(resources=("USB0::1234::5678::OTHER::0::INSTR",))
    with pytest.raises(RuntimeError):
        find_usb_resource(rm)


def test_find_usb_resource_raises_when_not_found():
    rm = FakeResourceManager(resources=())
    with pytest.raises(RuntimeError):
        find_usb_resource(rm)


# --- TCP_NODELAY : best-effort, jamais fatal --------------------------------------
def test_enable_tcp_nodelay_silently_ignores_missing_visalib():
    scope = _bare_scope(b"")
    # FakeInst n'a pas d'attribut visalib -> doit être avalé, pas planter.
    scope._enable_tcp_nodelay()


# --- drain : timeout court, configurable ------------------------------------------
def test_drain_timeout_is_short():
    """Le drain ne doit plus attendre 150ms par query_block (cf. docs/architecture.md)."""
    assert DRAIN_TIMEOUT_MS <= 50


def _bmp(payload_after_header: bytes) -> bytes:
    """Fabrique un BMP minimal : ``BM`` + bfSize (u32 LE) + reste d'en-tête + données."""
    body = b"\x00" * 10 + payload_after_header  # 10 octets : reste de l'en-tête BMP (simplifié)
    bf_size = 2 + 4 + len(body)
    return b"BM" + struct.pack("<I", bf_size) + body


def test_screen_dump_writes_scdp_and_returns_bmp_bytes(monkeypatch):
    bmp = _bmp(b"fake-bitmap-bytes")
    scope = _bare_scope(bmp)
    monkeypatch.setattr(scope, "flush_input", lambda: setattr(scope.inst, "flushed", True))

    data = scope.screen_dump()

    assert scope.inst.written == ["SCDP"]
    assert data.startswith(b"BM")
    assert scope.inst.flushed is True


def test_screen_dump_strips_trailing_terminator_byte(monkeypatch):
    """Le firmware ajoute parfois un octet '\\n' résiduel après le BMP : à tronquer."""
    bmp = _bmp(b"fake-bitmap-bytes") + b"\n"
    scope = _bare_scope(bmp)
    monkeypatch.setattr(scope, "flush_input", lambda: None)

    data = scope.screen_dump()

    assert data == bmp[:-1]
    assert not data.endswith(b"\n")


def test_bmp_payload_size_reads_header_field():
    bmp = _bmp(b"xyz")
    assert _bmp_payload_size(bmp) == len(bmp)
    assert _bmp_payload_size(bmp + b"\n\r") == len(bmp)
