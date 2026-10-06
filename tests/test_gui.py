"""Tests de la couche sans Qt de la GUI : dispatch SCPI + décimation d'affichage.

Pas d'import PyQt/pyqtgraph ici (voir ``scope/gui.py``) : ces tests tournent sans
display, comme ``test_control.py``/``test_waveform.py``.
"""

import struct

import numpy as np
import pytest

from scope import control, series
from scope.gui import (
    COUPLING_LABELS, PER_UNIT_LABELS, SLOPE_LABELS, START_MODE_LABELS, TDIV_VALUES, VDIV_VALUES,
    DescriptorCache, decimate, execute_command, tdiv_label, trigger_level_scpi, vdiv_label,
)


class FakeScope:
    """Faux scope : n'enregistre que les writes (règlages/run/stop/trigger)."""

    def __init__(self):
        self.written = []

    def write(self, cmd):
        self.written.append(cmd)


def _descriptor(count, vdiv, offset, interval):
    buf = bytearray(346)
    buf[0:8] = b"WAVEDESC"
    struct.pack_into("<i", buf, 116, count)
    struct.pack_into("<f", buf, 156, vdiv)
    struct.pack_into("<f", buf, 160, offset)
    struct.pack_into("<f", buf, 176, interval)
    return bytes(buf)


class CaptureFakeScope:
    """Faux scope répondant aux query_block DESC/DAT2, pour tester ("capture", ...)."""

    def __init__(self):
        self._desc = _descriptor(count=3, vdiv=1.0, offset=0.0, interval=1e-9)
        self._codes = struct.pack("b" * 3, 0, 25, -25)

    def query_block(self, command):
        if "DESC" in command:
            return self._desc
        return self._codes


# --- execute_command : réglages -------------------------------------------------
def test_execute_command_timebase():
    s = FakeScope()
    execute_command(s, ("timebase", "1MS"))
    assert s.written == ["TDIV 1MS"]


def test_execute_command_vdiv():
    s = FakeScope()
    execute_command(s, ("vdiv", "C2", "50MV"))
    assert s.written == ["C2:VDIV 50MV"]


def test_execute_command_coupling():
    s = FakeScope()
    execute_command(s, ("coupling", "C1", "d1m"))  # casse insensible (cf. control)
    assert s.written == ["C1:CPL D1M"]


def test_execute_command_enable():
    s = FakeScope()
    execute_command(s, ("enable", "C3", False))
    execute_command(s, ("enable", "C3", True))
    assert s.written == ["C3:TRA OFF", "C3:TRA ON"]


def test_execute_command_run_stop_autoset():
    s = FakeScope()
    execute_command(s, ("run",))
    execute_command(s, ("stop",))
    execute_command(s, ("autoset",))
    assert s.written == ["ARM", "STOP", "ASET"]


def test_execute_command_trigger():
    s = FakeScope()
    execute_command(s, ("trigger_source", "C2"))
    execute_command(s, ("trigger_slope", "C2", "pos"))
    execute_command(s, ("trigger_level", "C2", "1.0V"))
    assert s.written == ["TRSE EDGE,SR,C2", "C2:TRSL POS", "C2:TRLV 1.0V"]


def test_execute_command_points():
    s = FakeScope()
    execute_command(s, ("points", 1400))
    assert s.written == ["WFSU SP,1,NP,1400,FP,0"]


def test_execute_command_unknown_raises():
    s = FakeScope()
    with pytest.raises(ValueError):
        execute_command(s, ("bogus",))


# --- execute_command : capture ---------------------------------------------------
def test_execute_command_capture_writes_csv_npy(tmp_path):
    scope = CaptureFakeScope()
    result = execute_command(scope, ("capture", ["C1"], str(tmp_path), False))
    assert result["png"] is None
    assert result["channels"] == 1
    # un seul CSV combiné (pas de suffixe voie) + un .npy par voie
    csv_paths = [p for p in result["paths"] if p.endswith(".csv")]
    npy_paths = [p for p in result["paths"] if p.endswith(".npy")]
    assert len(csv_paths) == 1
    assert len(npy_paths) == 1
    assert (tmp_path / csv_paths[0].split("/")[-1]).exists()
    assert (tmp_path / npy_paths[0].split("/")[-1]).exists()


def test_execute_command_capture_multi_channel_writes_one_combined_csv(tmp_path):
    scope = CaptureFakeScope()
    result = execute_command(scope, ("capture", ["C1", "C2"], str(tmp_path), False))
    assert result["channels"] == 2
    csv_paths = [p for p in result["paths"] if p.endswith(".csv")]
    npy_paths = [p for p in result["paths"] if p.endswith(".npy")]
    assert len(csv_paths) == 1  # combiné, pas un par voie
    assert len(npy_paths) == 2  # un par voie
    lines = (tmp_path / csv_paths[0].split("/")[-1]).read_text().splitlines()
    assert lines[0] == "time_s,C1_V,C2_V"


def test_execute_command_capture_with_png(tmp_path):
    scope = CaptureFakeScope()
    result = execute_command(scope, ("capture", ["C1"], str(tmp_path), True))
    assert result["png"] is not None and result["png"].endswith(".png")
    assert (tmp_path / result["png"].split("/")[-1]).exists()


def test_execute_command_capture_applies_channel_config(tmp_path):
    from scope.channel_config import ChannelConfig

    scope = CaptureFakeScope()
    configs = {"C1": ChannelConfig(label="Icharge", unit="A", factor=10.0)}
    result = execute_command(scope, ("capture", ["C1"], str(tmp_path), False, configs))
    (csv_path,) = [p for p in result["paths"] if p.endswith(".csv")]
    lines = (tmp_path / csv_path.split("/")[-1]).read_text().splitlines()
    assert lines[0] == "time_s,Icharge_A"


# --- DescriptorCache ---------------------------------------------------------------
class CountingFakeScope:
    """Faux scope qui compte les query_block DESC/DAT2, et peut changer de count."""

    def __init__(self, count=3, vdiv=1.0, offset=0.0, interval=1e-9, codes=(0, 25, -25)):
        self.count = count
        self.vdiv = vdiv
        self.offset = offset
        self.interval = interval
        self.codes = codes
        self.desc_calls = 0
        self.dat2_calls = 0

    def query_block(self, command):
        if "DESC" in command:
            self.desc_calls += 1
            return _descriptor(self.count, self.vdiv, self.offset, self.interval)
        self.dat2_calls += 1
        return struct.pack("b" * len(self.codes), *self.codes)


def test_descriptor_cache_reuses_desc_across_frames():
    scope = CountingFakeScope()
    cache = DescriptorCache()

    cache.fetch(scope, "C1")
    cache.fetch(scope, "C1")
    cache.fetch(scope, "C1")

    assert scope.desc_calls == 1  # un seul DESC malgré 3 frames
    assert scope.dat2_calls == 3


def test_descriptor_cache_reuses_time_axis_across_frames():
    """Audit perf 2026-07-14 : l'axe temps ne doit être recalculé qu'une fois
    par descripteur, pas à chaque frame (même objet réutilisé)."""
    scope = CountingFakeScope()
    cache = DescriptorCache()

    wf1 = cache.fetch(scope, "C1")
    wf2 = cache.fetch(scope, "C1")

    assert wf2.time is wf1.time
    assert wf2.volts == pytest.approx(wf1.volts)  # décodage inchangé par ailleurs


def test_descriptor_cache_time_axis_invalidated_with_settings():
    scope = CountingFakeScope()
    cache = DescriptorCache()

    wf1 = cache.fetch(scope, "C1")
    cache.invalidate_if_setting("vdiv")
    wf2 = cache.fetch(scope, "C1")

    assert wf2.time is not wf1.time  # recalculé, pas l'axe périmé
    assert wf2.time == pytest.approx(wf1.time)  # mais identique en valeur (mêmes réglages)


def test_descriptor_cache_per_channel():
    scope = CountingFakeScope()
    cache = DescriptorCache()

    cache.fetch(scope, "C1")
    cache.fetch(scope, "C2")
    cache.fetch(scope, "C1")

    assert scope.desc_calls == 2  # un DESC par voie, pas partagé entre voies


def test_descriptor_cache_invalidate_on_setting_command():
    cache = DescriptorCache()
    cache._cache["C1"] = {"count": 3, "vdiv": 1.0, "offset": 0.0, "interval": 1e-9}

    cache.invalidate_if_setting("vdiv")

    assert cache._cache == {}


def test_descriptor_cache_ignores_non_setting_command():
    cache = DescriptorCache()
    cache._cache["C1"] = {"count": 3, "vdiv": 1.0, "offset": 0.0, "interval": 1e-9}

    cache.invalidate_if_setting("run")

    assert "C1" in cache._cache


# --- DescriptorCache : auto-guérison sur flux désynchronisé (ex. après un
# changement de réglage comme TDIV, cf. "WAVEDESC introuvable" observé sur
# matériel) ---------------------------------------------------------------------
class DesyncThenOkFakeScope:
    """Simule un flux désynchronisé : DESC illisible une fois, puis OK après resync().

    Reproduit le bug observé : un changement de réglage (ex. TDIV) laisse le
    flux binaire désaligné -- ``query_block`` peut alors lire un bloc qui ne
    contient pas ``WAVEDESC`` (cf. ``waveform.parse_descriptor``). Seul un
    ``resync()`` (répéter ``*IDN?`` jusqu'à recalage, cf. ``connection.py``)
    répare le flux ; ce fake le simule en ne « guérissant » qu'après l'appel.
    """

    def __init__(self):
        self.resync_calls = 0
        self._healed = False

    def query_block(self, command):
        if "DESC" in command:
            if not self._healed:
                # Bloc mal formé (pas de marqueur WAVEDESC) : simule la
                # désynchronisation -- parse_descriptor lèvera ValueError.
                return b"\x00" * 346
            return _descriptor(count=3, vdiv=1.0, offset=0.0, interval=1e-9)
        return struct.pack("b" * 3, 0, 25, -25)

    def resync(self):
        self.resync_calls += 1
        self._healed = True  # après resync, le flux est réaligné


def test_descriptor_cache_resyncs_and_retries_on_malformed_block():
    scope = DesyncThenOkFakeScope()
    cache = DescriptorCache()

    wf = cache.fetch(scope, "C1")  # doit s'auto-guérir, pas lever d'exception

    assert scope.resync_calls == 1
    assert wf.volts == pytest.approx([0.0, 1.0, -1.0])


def test_descriptor_cache_raises_if_still_broken_after_resync():
    class AlwaysBrokenFakeScope:
        def __init__(self):
            self.resync_calls = 0

        def query_block(self, command):
            return b"\x00" * 346

        def resync(self):
            self.resync_calls += 1

    scope = AlwaysBrokenFakeScope()
    cache = DescriptorCache()

    with pytest.raises(ValueError):
        cache.fetch(scope, "C1")
    assert scope.resync_calls == 1  # une seule tentative de resync, pas de boucle infinie


def test_descriptor_cache_discard_removes_one_channel():
    cache = DescriptorCache()
    cache._cache["C1"] = {"count": 3, "vdiv": 1.0, "offset": 0.0, "interval": 1e-9}
    cache._cache["C2"] = {"count": 3, "vdiv": 1.0, "offset": 0.0, "interval": 1e-9}

    cache.discard("C1")

    assert "C1" not in cache._cache and "C2" in cache._cache


def test_descriptor_cache_refetches_on_count_mismatch():
    """Le buffer a changé sans commande connue : le cache doit s'auto-corriger."""
    scope = CountingFakeScope(count=3)
    cache = DescriptorCache()
    cache.fetch(scope, "C1")
    assert scope.desc_calls == 1

    scope.count = 5  # changement "silencieux" (hors execute_command)
    scope.codes = (0, 25, -25, 50, -50)
    wf = cache.fetch(scope, "C1")

    assert scope.desc_calls == 2  # a détecté l'écart et relu un descripteur frais
    assert len(wf.volts) == 5


# --- decimate ---------------------------------------------------------------------
def test_decimate_noop_when_already_small():
    t = np.arange(10)
    v = np.arange(10) * 2
    dt, dv = decimate(t, v, max_points=4000)
    np.testing.assert_array_equal(dt, t)
    np.testing.assert_array_equal(dv, v)


def test_decimate_reduces_and_keeps_endpoints():
    t = np.arange(100_000)
    v = np.arange(100_000)
    dt, dv = decimate(t, v, max_points=1000)
    assert len(dt) <= 1001
    assert dt[0] == 0
    assert dt[-1] == 99_999
    assert dv[-1] == 99_999


# --- libellés lisibles (codes SCPI gardés en interne) --------------------------------------
@pytest.mark.parametrize("code, label", [("2MV", "2 mV/div"), ("500MV", "500 mV/div"),
                                         ("1V", "1 V/div"), ("10V", "10 V/div")])
def test_vdiv_label(code, label):
    assert vdiv_label(code) == label


@pytest.mark.parametrize("code, label", [("2NS", "2 ns/div"), ("500US", "500 µs/div"),
                                         ("1MS", "1 ms/div"), ("1S", "1 s/div")])
def test_tdiv_label(code, label):
    assert tdiv_label(code) == label


def test_every_scpi_value_has_a_distinct_label():
    # aucun code laissé brut, aucun libellé ambigu (deux codes, même libellé)
    assert len({vdiv_label(v) for v in VDIV_VALUES}) == len(VDIV_VALUES)
    assert len({tdiv_label(v) for v in TDIV_VALUES}) == len(TDIV_VALUES)
    assert set(COUPLING_LABELS) == control.VALID_COUPLING
    assert set(SLOPE_LABELS) == control.VALID_SLOPE
    assert set(START_MODE_LABELS) == series.VALID_START_MODES
    assert set(PER_UNIT_LABELS) == set(series.PER_UNIT_SECONDS)


def test_start_modes_listed_threshold_first():
    assert list(START_MODE_LABELS) == ["threshold", "now", "countdown"]
    assert START_MODE_LABELS["threshold"] == "Au seuil"


@pytest.mark.parametrize("text, scpi", [("1", "1V"), ("1.0V", "1V"), ("0,5", "0.5V"),
                                        (" -2.5 v ", "-2.5V"), ("0.05", "0.05V")])
def test_trigger_level_scpi(text, scpi):
    assert trigger_level_scpi(text) == scpi


@pytest.mark.parametrize("text", ["", "abc", "1 kV", "V"])
def test_trigger_level_scpi_rejects_invalid(text):
    with pytest.raises(ValueError):
        trigger_level_scpi(text)
