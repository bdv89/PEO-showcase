"""Tests du cœur décodage — exécutables sans matériel.

On fige des descripteurs / blocs binaires synthétiques (mêmes octets que le scope
renverrait) et on vérifie la conversion codes -> volts et l'axe temps.
"""

import struct

import numpy as np
import pytest

from scope.waveform import (
    VERT_CODES_PER_DIV,
    decode,
    fetch,
    parse_block,
    parse_descriptor,
    parse_float,
)


def _ieee_block(codes: bytes, prefix: bytes = b"C1:WF DAT2,") -> bytes:
    """Fabrique une réponse Siglent ``<prefix>#9<len><data>\\n\\n``."""
    header = b"#9" + f"{len(codes):09d}".encode()
    return prefix + header + codes + b"\n\n"


def _descriptor(count: int, vdiv: float, offset: float, interval: float) -> bytes:
    """Fabrique un bloc WAVEDESC minimal aux bons offsets."""
    buf = bytearray(346)
    buf[0:8] = b"WAVEDESC"
    struct.pack_into("<i", buf, 116, count)
    struct.pack_into("<f", buf, 156, vdiv)
    struct.pack_into("<f", buf, 160, offset)
    struct.pack_into("<f", buf, 176, interval)
    return bytes(buf)


# --- parse_float ---------------------------------------------------------------
@pytest.mark.parametrize(
    "response, expected",
    [
        ("C1:VDIV 1.00E+00V", 1.0),
        ("C1:OFST -1.50E+00V", -1.5),
        ("SARA 5.00E+08Sa/s", 5e8),
        ("TDIV 1.00E-03S", 1e-3),
    ],
)
def test_parse_float(response, expected):
    assert parse_float(response) == pytest.approx(expected)


def test_parse_float_invalid():
    with pytest.raises(ValueError):
        parse_float("no number here")


# --- parse_descriptor ----------------------------------------------------------
def test_parse_descriptor_fields():
    desc = _descriptor(count=3_500_000, vdiv=0.5, offset=-1.5, interval=2e-9)
    p = parse_descriptor(b"C1:WF DESC,#9000000346" + desc)
    assert p["count"] == 3_500_000
    assert p["vdiv"] == pytest.approx(0.5)
    assert p["offset"] == pytest.approx(-1.5)
    assert p["interval"] == pytest.approx(2e-9)


def test_parse_descriptor_no_wavedesc():
    with pytest.raises(ValueError):
        parse_descriptor(b"garbage")


# --- parse_block ---------------------------------------------------------------
def test_parse_block_strips_prefix_and_terminator():
    codes = struct.pack("b" * 4, 0, 25, -25, 127)
    out = parse_block(_ieee_block(codes))
    assert list(out) == [0.0, 25.0, -25.0, 127.0]


def test_parse_block_detects_truncation():
    raw = b"C1:WF DAT2,#9000000010" + struct.pack("b" * 4, 1, 2, 3, 4)
    with pytest.raises(ValueError):
        parse_block(raw)


# --- decode --------------------------------------------------------------------
def test_decode_voltage_formula():
    # code=25 à vdiv=1V => 25*(1/25)=1V, moins offset 0 => 1V.
    wf = decode(struct.pack("b" * 3, 0, 25, -25), vdiv=1.0, offset=0.0, interval=1e-9)
    assert wf.volts == pytest.approx([0.0, 1.0, -1.0])
    assert wf.vdiv == 1.0 and wf.channel == "C1"


def test_decode_applies_offset():
    # code=25, vdiv=2 -> 25*(2/25)=2 ; moins offset -1.5 (formule code*vdiv/25 - ofst)
    wf = decode(struct.pack("b", 25), vdiv=2.0, offset=-1.5, interval=1e-9)
    assert wf.volts[0] == pytest.approx(3.5)


def test_decode_time_axis_centered():
    interval = 2e-9
    wf = decode(np.zeros(4), vdiv=1.0, offset=0.0, interval=interval)
    # temps centré sur le trigger : (i - n/2) * interval
    assert wf.time[0] == pytest.approx(-2 * interval)
    assert wf.time[1] - wf.time[0] == pytest.approx(interval)
    assert wf.sample_rate == pytest.approx(1 / interval)


def test_decode_accepts_raw_codes_array():
    wf = decode([0, VERT_CODES_PER_DIV], vdiv=1.0, offset=0.0, interval=1e-9)
    assert wf.volts[1] == pytest.approx(1.0)


def test_decode_reuses_provided_time_axis():
    """``time=`` (audit perf 2026-07-14, cf. gui.DescriptorCache) : si fourni, il
    est réutilisé tel quel -- pas recalculé -- au lieu de reconstruire l'axe via
    ``arange`` à chaque frame."""
    cached_time = np.array([10.0, 20.0, 30.0])
    wf = decode(struct.pack("b" * 3, 0, 25, -25), vdiv=1.0, offset=0.0, interval=1e-9, time=cached_time)
    assert wf.time is cached_time  # objet réutilisé, pas une copie recalculée
    assert wf.volts == pytest.approx([0.0, 1.0, -1.0])  # décodage inchangé


def test_decode_computes_time_axis_when_not_provided():
    """Sans ``time=`` (défaut), comportement inchangé : axe centré recalculé."""
    wf = decode(struct.pack("b" * 3, 0, 25, -25), vdiv=1.0, offset=0.0, interval=1e-9)
    assert wf.time == pytest.approx([-1.5e-9, -0.5e-9, 0.5e-9])


# --- values / display_name (conversion V -> unité, cf. channel_config) --------------
def test_values_defaults_to_volts():
    wf = decode([0, VERT_CODES_PER_DIV], vdiv=1.0, offset=0.0, interval=1e-9)
    assert wf.values == pytest.approx(wf.volts)
    assert wf.unit == "V" and wf.factor == 1.0
    assert wf.display_name == "C1"


def test_values_applies_factor():
    wf = decode([0, VERT_CODES_PER_DIV], vdiv=1.0, offset=0.0, interval=1e-9, channel="C2")
    import dataclasses

    wf = dataclasses.replace(wf, label="Icharge", unit="A", factor=10.0)
    assert wf.values == pytest.approx(wf.volts * 10.0)
    assert wf.display_name == "Icharge"


# --- fetch (avec scope mocké, sans matériel) -----------------------------------
class FakeScope:
    """Faux scope : répond aux query_block DESC puis DAT2."""

    def __init__(self, count=3, vdiv=1.0, offset=0.0, interval=1e-9, codes=(0, 25, -25)):
        self._desc = _descriptor(count, vdiv, offset, interval)
        self._codes = struct.pack("b" * len(codes), *codes)
        self.blocks = []

    def query_block(self, command):
        self.blocks.append(command)
        if "DESC" in command:
            return self._desc
        return self._codes


def test_fetch_reads_descriptor_then_data():
    scope = FakeScope(count=3, vdiv=1.0, offset=0.0, codes=(0, 25, -25))
    wf = fetch(scope, "C1")
    assert "C1:WF? DESC" in scope.blocks and "C1:WF? DAT2" in scope.blocks
    assert wf.volts == pytest.approx([0.0, 1.0, -1.0])


def test_fetch_raises_on_empty_acquisition():
    scope = FakeScope(count=0)
    with pytest.raises(ValueError):
        fetch(scope, "C1")


def test_fetch_data_passes_through_cached_time_axis():
    """``fetch_data(..., time=...)`` transmet l'axe à ``decode`` sans le
    recalculer (audit perf 2026-07-14, cf. gui.DescriptorCache)."""
    from scope.waveform import fetch_data, fetch_descriptor

    scope = FakeScope(count=3, vdiv=1.0, offset=0.0, codes=(0, 25, -25))
    desc = fetch_descriptor(scope, "C1")
    cached_time = np.array([1.0, 2.0, 3.0])
    wf = fetch_data(scope, "C1", desc, time=cached_time)
    assert wf.time is cached_time




# --- save ----------------------------------------------------------------------
def test_save_writes_csv_and_npy(tmp_path):
    from scope.waveform import save

    wf = decode(np.array([0, 25, -25]), vdiv=1.0, offset=0.0, interval=1e-9)
    csv_path, npy_path = save(wf, str(tmp_path / "trace"))

    arr = np.load(npy_path)
    assert arr.shape == (3, 2)
    assert arr[1, 1] == pytest.approx(1.0)

    lines = (tmp_path / "trace.csv").read_text().splitlines()
    assert lines[0] == "time_s,C1_V"
    assert len(lines) == 4


def test_save_csv_applies_conversion_and_label(tmp_path):
    import csv
    import dataclasses

    from scope.waveform import save

    wf = decode(
        np.array([0, 25, -25]), vdiv=1.0, offset=0.0, interval=1e-9, channel="C2"
    )
    wf = dataclasses.replace(wf, label="Icharge", unit="A", factor=10.0)
    (csv_path,) = save(wf, str(tmp_path / "trace"), formats=["csv"])

    with open(csv_path, newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["time_s", "Icharge_A"]
    assert float(rows[1][1]) == pytest.approx(0.0)   # code=0   -> 0V ×10
    assert float(rows[2][1]) == pytest.approx(10.0)  # code=25  -> 1V ×10
    assert float(rows[3][1]) == pytest.approx(-10.0)  # code=-25 -> -1V ×10


def test_save_npz(tmp_path):
    from scope.waveform import save

    wf = decode(np.array([0, 25, -25]), vdiv=1.0, offset=0.0, interval=1e-9, channel="C2")
    paths = save(wf, str(tmp_path / "trace"), formats=["npz"])
    assert paths == [str(tmp_path / "trace.npz")]

    npz = np.load(paths[0])
    assert npz["volts"].shape == (3,)
    assert npz["volts"][1] == pytest.approx(1.0)
    assert float(npz["vdiv"]) == pytest.approx(1.0)
    assert float(npz["offset"]) == pytest.approx(0.0)
    assert float(npz["interval"]) == pytest.approx(1e-9)
    assert str(npz["channel"]) == "C2"


def test_save_hdf5(tmp_path):
    h5py = pytest.importorskip("h5py")
    from scope.waveform import save

    wf = decode(np.array([0, 25, -25]), vdiv=1.0, offset=0.0, interval=1e-9)
    paths = save(wf, str(tmp_path / "trace"), formats=["hdf5"])
    assert paths == [str(tmp_path / "trace.h5")]

    with h5py.File(paths[0], "r") as f:
        assert f["volts"].shape == (3,)
        assert f["volts"][1] == pytest.approx(1.0)
        assert f.attrs["vdiv"] == pytest.approx(1.0)
        assert f.attrs["channel"] == "C1"


def test_save_mat(tmp_path):
    scipy_io = pytest.importorskip("scipy.io")
    from scope.waveform import save

    wf = decode(np.array([0, 25, -25]), vdiv=1.0, offset=0.0, interval=1e-9)
    paths = save(wf, str(tmp_path / "trace"), formats=["mat"])
    assert paths == [str(tmp_path / "trace.mat")]

    mat = scipy_io.loadmat(paths[0])
    assert mat["volts"].ravel() == pytest.approx([0.0, 1.0, -1.0])


def test_save_multiple_formats(tmp_path):
    from scope.waveform import save

    wf = decode(np.array([0, 25, -25]), vdiv=1.0, offset=0.0, interval=1e-9)
    paths = save(wf, str(tmp_path / "trace"), formats=["csv", "npy", "npz"])
    assert paths == [
        str(tmp_path / "trace.csv"),
        str(tmp_path / "trace.npy"),
        str(tmp_path / "trace.npz"),
    ]


def test_save_invalid_format(tmp_path):
    from scope.waveform import save

    wf = decode(np.array([0, 25, -25]), vdiv=1.0, offset=0.0, interval=1e-9)
    with pytest.raises(ValueError):
        save(wf, str(tmp_path / "trace"), formats=["bogus"])


# --- save_combined_csv / save_capture (export multi-voies) ------------------------------
def _wf(channel, codes=(0, 25, -25), *, label="", unit="V", factor=1.0):
    import dataclasses

    wf = decode(np.array(codes), vdiv=1.0, offset=0.0, interval=1e-9, channel=channel)
    return dataclasses.replace(wf, label=label, unit=unit, factor=factor)


def test_save_combined_csv_writes_one_column_per_waveform(tmp_path):
    from scope.waveform import save_combined_csv

    wfs = [_wf("C1", label="Vbat"), _wf("C2", codes=(0, 10, -10), label="Icharge", unit="A", factor=2.0)]
    path = save_combined_csv(wfs, str(tmp_path / "trace"))

    assert path == str(tmp_path / "trace.csv")
    import csv

    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["time_s", "Vbat_V", "Icharge_A"]
    assert len(rows) == 4  # en-tête + 3 points
    # C2 : code=10 -> 0.4V *2 = 0.8
    assert float(rows[2][2]) == pytest.approx(0.8)


def test_save_combined_csv_uses_channel_name_without_label():
    from scope.waveform import save_combined_csv

    wfs = [_wf("C1"), _wf("C2")]
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = save_combined_csv(wfs, f"{tmp}/trace")
        with open(path, newline="") as fh:
            header = fh.readline().strip()
    assert header == "time_s,C1_V,C2_V"


def test_save_combined_csv_rejects_mismatched_lengths(tmp_path):
    from scope.waveform import save_combined_csv

    wfs = [_wf("C1", codes=(0, 25, -25)), _wf("C2", codes=(0, 25))]
    with pytest.raises(ValueError):
        save_combined_csv(wfs, str(tmp_path / "trace"))


def test_save_combined_csv_rejects_empty_list(tmp_path):
    from scope.waveform import save_combined_csv

    with pytest.raises(ValueError):
        save_combined_csv([], str(tmp_path / "trace"))


def test_save_capture_writes_one_combined_csv_and_per_channel_binaries(tmp_path):
    from scope.waveform import save_capture

    wfs = [_wf("C1", label="Vbat"), _wf("C2", label="Icharge")]
    paths = save_capture(wfs, str(tmp_path / "20260101_000000"), formats=("csv", "npy"))

    assert str(tmp_path / "20260101_000000.csv") in paths
    assert str(tmp_path / "20260101_000000_C1.npy") in paths
    assert str(tmp_path / "20260101_000000_C2.npy") in paths
    assert len(paths) == 3
    assert (tmp_path / "20260101_000000.csv").exists()
    assert (tmp_path / "20260101_000000_C1.npy").exists()
    assert (tmp_path / "20260101_000000_C2.npy").exists()
    # pas de CSV par voie
    assert not (tmp_path / "20260101_000000_C1.csv").exists()


def test_save_capture_without_csv_format_skips_combined_file(tmp_path):
    from scope.waveform import save_capture

    wfs = [_wf("C1")]
    paths = save_capture(wfs, str(tmp_path / "trace"), formats=("npy",))

    assert paths == [str(tmp_path / "trace_C1.npy")]
    assert not (tmp_path / "trace.csv").exists()


def test_save_capture_empty_waveforms_returns_no_paths(tmp_path):
    from scope.waveform import save_capture

    assert save_capture([], str(tmp_path / "trace")) == []
