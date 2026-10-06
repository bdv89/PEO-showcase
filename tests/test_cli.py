"""Tests de la CLI : isolation des échecs par voie lors d'une capture."""

import struct

from scope import cli, series


def _descriptor(count, vdiv, offset, interval):
    buf = bytearray(346)
    buf[0:8] = b"WAVEDESC"
    struct.pack_into("<i", buf, 116, count)
    struct.pack_into("<f", buf, 156, vdiv)
    struct.pack_into("<f", buf, 160, offset)
    struct.pack_into("<f", buf, 176, interval)
    return bytes(buf)


class SelectiveFakeScope:
    """Faux scope : les voies listées dans ``failing`` lèvent à la lecture."""

    def __init__(self, failing=()):
        self._desc = _descriptor(count=3, vdiv=1.0, offset=0.0, interval=1e-9)
        self._codes = struct.pack("b" * 3, 0, 25, -25)
        self.failing = set(failing)

    def query_block(self, command):
        ch = command.split(":")[0]
        if ch in self.failing:
            raise ValueError(f"{ch} : acquisition vide")
        if "DESC" in command:
            return self._desc
        return self._codes


def test_capture_channels_saves_ok_channels_despite_one_failure(tmp_path):
    scope = SelectiveFakeScope(failing={"C3"})
    waveforms, errors = cli._capture_channels(scope, ["C1", "C3"], str(tmp_path), "20260101_000000")

    assert [wf.channel for wf in waveforms] == ["C1"]
    assert len(errors) == 1 and "C3" in errors[0]
    # CSV combiné (une seule voie a réussi -> pas de suffixe voie) + npy C1
    assert (tmp_path / "20260101_000000.csv").exists()
    assert (tmp_path / "20260101_000000_C1.npy").exists()


def test_capture_channels_writes_one_combined_csv_for_multiple_channels(tmp_path):
    scope = SelectiveFakeScope()
    waveforms, errors = cli._capture_channels(scope, ["C1", "C2"], str(tmp_path), "stamp")

    assert errors == []
    assert len(waveforms) == 2
    # un seul CSV multi-colonnes, pas un par voie
    assert (tmp_path / "stamp.csv").exists()
    assert not (tmp_path / "stamp_C1.csv").exists()
    assert not (tmp_path / "stamp_C2.csv").exists()
    lines = (tmp_path / "stamp.csv").read_text().splitlines()
    assert lines[0] == "time_s,C1_V,C2_V"
    # les .npy restent un fichier par voie
    assert (tmp_path / "stamp_C1.npy").exists()
    assert (tmp_path / "stamp_C2.npy").exists()


def test_capture_channels_applies_configs_label_to_csv_header(tmp_path):
    from scope.channel_config import ChannelConfig

    scope = SelectiveFakeScope()
    configs = {"C1": ChannelConfig(label="Vbat", unit="V", factor=1.0)}
    waveforms, errors = cli._capture_channels(
        scope, ["C1"], str(tmp_path), "stamp", configs=configs
    )

    assert errors == []
    lines = (tmp_path / "stamp.csv").read_text().splitlines()
    assert lines[0] == "time_s,Vbat_V"


def test_capture_channels_all_ok(tmp_path):
    scope = SelectiveFakeScope()
    waveforms, errors = cli._capture_channels(scope, ["C1", "C2"], str(tmp_path), "stamp")
    assert len(waveforms) == 2
    assert errors == []


def test_capture_channels_custom_formats(tmp_path):
    scope = SelectiveFakeScope()
    waveforms, errors = cli._capture_channels(
        scope, ["C1"], str(tmp_path), "stamp", formats=["npz"]
    )
    assert len(waveforms) == 1
    assert errors == []
    assert (tmp_path / "stamp_C1.npz").exists()
    assert not (tmp_path / "stamp_C1.csv").exists()


# --- measure ---------------------------------------------------------------------
class MeasureFakeScope:
    def __init__(self):
        self.written = []

    def query(self, cmd):
        self.written.append(cmd)
        if cmd == "C1:PAVA? PKPK":
            return "C1:PAVA PKPK,1.00E+00V"
        if cmd == "C1:PAVA? FREQ":
            return "C1:PAVA FREQ,1.00E+03Hz"
        raise AssertionError(f"unexpected query {cmd!r}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


def test_cmd_measure_prints_values(monkeypatch, capsys):
    scope = MeasureFakeScope()
    monkeypatch.setattr(cli, "_connect", lambda args: scope)
    args = cli.build_parser().parse_args(
        ["measure", "1.2.3.4", "--channels", "C1", "--params", "PKPK", "FREQ"]
    )
    assert cli.cmd_measure(args) == 0
    out = capsys.readouterr().out
    assert "PKPK" in out and "1.0" in out
    assert "FREQ" in out and "1000.0" in out


# --- discover ----------------------------------------------------------------------
def test_cmd_discover_prints_found_scopes(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "scan", lambda cidr, **kw: [("10.11.13.220", "Siglent Technologies,SDS1204X-E")]
    )
    args = cli.build_parser().parse_args(["discover", "--cidr", "10.11.13.0/24"])
    assert cli.cmd_discover(args) == 0
    out = capsys.readouterr().out
    assert "10.11.13.220" in out
    assert "Siglent" in out


# --- set --autoscale ---------------------------------------------------------------
class _NullScope:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


def test_cmd_set_autoscale_uses_active_channels(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_connect", lambda args: _NullScope())
    monkeypatch.setattr(cli.control, "active_channels", lambda scope: ["C1", "C3"])
    autoscaled = []
    monkeypatch.setattr(
        cli.control, "autoscale", lambda scope, ch: autoscaled.append(ch)
    )
    args = cli.build_parser().parse_args(["set", "1.2.3.4", "--autoscale"])
    assert cli.cmd_set(args) == 0
    assert autoscaled == ["C1", "C3"]


# --- transport par défaut de capture/series/live/gui (socket, sauf --vxi11/--usb) --
class _Args:
    def __init__(self, vxi11=False, usb=False):
        self.vxi11 = vxi11
        self.usb = usb


def test_live_transport_defaults_to_socket():
    assert cli._live_transport(_Args()) == {"socket": True, "usb": False}


def test_live_transport_vxi11_flag_forces_vxi11():
    assert cli._live_transport(_Args(vxi11=True)) == {"socket": False, "usb": False}


def test_live_transport_usb_flag_wins_over_vxi11():
    assert cli._live_transport(_Args(vxi11=True, usb=True)) == {"socket": False, "usb": True}


def test_cmd_capture_opens_scope_with_socket_by_default(monkeypatch, tmp_path):
    """Audit 2026-07-14 : capture/series fetchent la mémoire native complète comme
    live/gui, donc doivent partager leur défaut socket (VXI-11 y était ~30-50x plus
    lent, mesuré sur matériel — cf. docs/architecture.md)."""
    opened = {}

    class _RecordingScope(_NullScope):
        def __init__(self, ip, **kw):
            opened["ip"] = ip
            opened["kwargs"] = kw

        def screen_dump(self):
            raise NotImplementedError

    monkeypatch.setattr(cli, "Scope", _RecordingScope)
    monkeypatch.setattr(cli, "_capture_channels", lambda *a, **kw: ([], []))

    args = cli.build_parser().parse_args(["capture", "1.2.3.4"])
    cli.cmd_capture(args)

    assert opened["kwargs"]["socket"] is True
    assert opened["kwargs"]["usb"] is False


def test_cmd_capture_vxi11_flag_forces_vxi11(monkeypatch):
    opened = {}

    class _RecordingScope(_NullScope):
        def __init__(self, ip, **kw):
            opened["kwargs"] = kw

    monkeypatch.setattr(cli, "Scope", _RecordingScope)
    monkeypatch.setattr(cli, "_capture_channels", lambda *a, **kw: ([], []))

    args = cli.build_parser().parse_args(["--vxi11", "capture", "1.2.3.4"])
    cli.cmd_capture(args)

    assert opened["kwargs"]["socket"] is False


def test_cmd_series_opens_scope_with_socket_by_default(monkeypatch):
    opened = {}

    class _RecordingScope(_NullScope):
        def __init__(self, ip, **kw):
            opened["kwargs"] = kw

    monkeypatch.setattr(cli, "Scope", _RecordingScope)
    monkeypatch.setattr(
        cli.series,
        "run_series",
        lambda config, scope, **kw: series.RunResult(started=False),
    )

    args = cli.build_parser().parse_args(
        [
            "series", "1.2.3.4",
            "--id", "essai42", "--rate", "1", "--per", "second", "--duration", "1s",
        ]
    )
    cli.cmd_series(args)

    assert opened["kwargs"]["socket"] is True


# --- series ------------------------------------------------------------------------
def test_cmd_series_builds_config_and_calls_run_series(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "Scope", lambda ip, **kw: _NullScope())
    captured = {}

    def fake_run_series(config, scope, **kw):
        captured["config"] = config
        return series.RunResult(started=True, captures=[{"index": 1}], meta_path="meta.json")

    monkeypatch.setattr(cli.series, "run_series", fake_run_series)

    args = cli.build_parser().parse_args(
        [
            "series",
            "1.2.3.4",
            "--id", "essai42",
            "--rate", "10",
            "--per", "minute",
            "--duration", "30m",
            "--channels", "C1", "C2",
            "--outdir", str(tmp_path),
        ]
    )
    assert cli.cmd_series(args) == 0

    cfg = captured["config"]
    assert cfg.experiment_id == "essai42"
    assert cfg.channels == ["C1", "C2"]
    assert cfg.rate == 10.0
    assert cfg.per_seconds == 60.0
    assert cfg.duration_max == 1800.0
    assert cfg.start_mode == "now"
    assert cfg.outdir == str(tmp_path)


def test_cmd_series_threshold_mode_builds_threshold_dict(monkeypatch):
    monkeypatch.setattr(cli, "Scope", lambda ip, **kw: _NullScope())
    captured = {}

    def fake_run_series(config, scope, **kw):
        captured["config"] = config
        return series.RunResult(started=False)

    monkeypatch.setattr(cli.series, "run_series", fake_run_series)

    args = cli.build_parser().parse_args(
        [
            "series",
            "1.2.3.4",
            "--id", "essai42",
            "--rate", "1",
            "--per", "second",
            "--duration", "10s",
            "--start", "threshold",
            "--threshold-channel", "C2",
            "--threshold-level", "5V",
            "--threshold-slope", "POS",
            "--threshold-timeout", "20",
        ]
    )
    # seuil non atteint -> code de sortie non nul (série annulée)
    assert cli.cmd_series(args) == 1

    cfg = captured["config"]
    assert cfg.start_mode == "threshold"
    assert cfg.threshold == {
        "channel": "C2",
        "level": "5V",
        "slope": "POS",
        "timeout_s": 20.0,
    }


def test_cmd_series_countdown_mode_sets_delay(monkeypatch):
    monkeypatch.setattr(cli, "Scope", lambda ip, **kw: _NullScope())
    captured = {}

    def fake_run_series(config, scope, **kw):
        captured["config"] = config
        return series.RunResult(started=True, captures=[], meta_path=None)

    monkeypatch.setattr(cli.series, "run_series", fake_run_series)

    args = cli.build_parser().parse_args(
        [
            "series",
            "1.2.3.4",
            "--id", "essai42",
            "--rate", "1",
            "--per", "second",
            "--duration", "5s",
            "--start", "countdown",
            "--countdown", "3",
        ]
    )
    assert cli.cmd_series(args) == 0
    assert captured["config"].delay_s == 3.0
