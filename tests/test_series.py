"""Tests de la capture temporelle (série d'expérience), sans matériel.

Calqué sur ``test_acquisition.py`` : horloge/attente injectées, scope factice,
``fetch``/``save`` mockés -- aucune vraie temporisation ni matériel requis.
"""

import dataclasses
import json
import os

import pytest

from scope import series


# --- helpers purs ------------------------------------------------------------------
def test_series_filename_pads_index_and_includes_channel():
    assert series.series_filename("essai42", 1, "C1") == "essai42_0001_C1"
    assert series.series_filename("essai42", 12, "C2") == "essai42_0012_C2"


@pytest.mark.parametrize(
    "rate, per_seconds, expected",
    [
        (10, 60, 6.0),   # 10/min -> 6s
        (1, 1, 1.0),      # 1/s -> 1s
        (2, 1, 0.5),      # 2/s -> 0.5s
    ],
)
def test_capture_interval(rate, per_seconds, expected):
    assert series.capture_interval(rate, per_seconds) == pytest.approx(expected)


@pytest.mark.parametrize("rate", [0, -1])
def test_capture_interval_rejects_non_positive_rate(rate):
    with pytest.raises(ValueError):
        series.capture_interval(rate, 60)


def test_tick_deadlines_bounded_by_duration_max():
    deadlines = series.tick_deadlines(t0=100.0, interval=2.0, duration_max=7.0)
    # t0, t0+2, t0+4, t0+6 -- t0+8 dépasserait duration_max (7s)
    assert deadlines == [100.0, 102.0, 104.0, 106.0]


def test_tick_deadlines_no_drift_accumulation():
    deadlines = series.tick_deadlines(t0=0.0, interval=0.3, duration_max=1.0)
    # instants absolus = i * interval, pas de dérive cumulée par addition répétée
    assert deadlines == [pytest.approx(i * 0.3) for i in range(len(deadlines))]


# --- start_series --------------------------------------------------------------------
class FakeScope:
    def __init__(self):
        self.writes = []

    def write(self, cmd):
        self.writes.append(cmd)

    def query(self, cmd):
        return "0"


class FakeClock:
    def __init__(self, step=0.05):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


def test_start_series_now_returns_true_immediately():
    scope = FakeScope()
    sleeps = []
    ok = series.start_series(scope, "now", clock=FakeClock(), sleep=sleeps.append)
    assert ok is True
    assert sleeps == []
    assert scope.writes == []  # aucune configuration touchée


def test_start_series_countdown_sleeps_then_true():
    scope = FakeScope()
    sleeps = []
    ok = series.start_series(
        scope, "countdown", delay_s=5.0, clock=FakeClock(), sleep=sleeps.append
    )
    assert ok is True
    assert sleeps == [5.0]


def test_start_series_threshold_configures_trigger_and_relays_wait_result():
    scope = FakeScope()
    calls = []

    def fake_wait(scope_arg, *, timeout_s):
        calls.append(timeout_s)
        return True

    threshold = {
        "channel": "C2",
        "level": "5V",
        "slope": "POS",
        "timeout_s": 30.0,
    }
    ok = series.start_series(
        scope,
        "threshold",
        threshold=threshold,
        clock=FakeClock(),
        sleep=lambda _s: None,
        wait=fake_wait,
    )
    assert ok is True
    assert calls == [30.0]
    joined = " ".join(scope.writes)
    assert "TRSE EDGE,SR,C2" in joined
    assert "C2:TRLV 5V" in joined
    assert "C2:TRSL POS" in joined
    assert "TRMD SINGLE" in joined
    assert "ARM" in joined


def test_start_series_threshold_not_reached_returns_false():
    scope = FakeScope()
    ok = series.start_series(
        scope,
        "threshold",
        threshold={"channel": "C1", "level": "1V", "slope": "POS", "timeout_s": 1.0},
        clock=FakeClock(),
        sleep=lambda _s: None,
        wait=lambda scope_arg, *, timeout_s: False,
    )
    assert ok is False


def test_start_series_unknown_mode_raises():
    with pytest.raises(ValueError):
        series.start_series(FakeScope(), "bogus", clock=FakeClock(), sleep=lambda _s: None)


# --- run_series ------------------------------------------------------------------------
@dataclasses.dataclass
class FakeWaveform:
    """Double léger de ``Waveform`` -- un vrai dataclass pour rester compatible
    avec ``dataclasses.replace`` (appliqué par ``capture_once`` pour le label/
    unité/facteur configurés)."""

    channel: str
    time: list = dataclasses.field(default_factory=lambda: [0.0, 1.0])
    volts: list = dataclasses.field(default_factory=lambda: [0.0, 1.0])
    label: str = ""
    unit: str = "V"
    factor: float = 1.0


def _make_fetch(failing_channel=None):
    def fetch(scope, channel):
        if channel == failing_channel:
            raise ValueError(f"{channel} : acquisition vide")
        return FakeWaveform(channel)

    return fetch


def _make_save(written):
    """Fake de ``waveform.save_capture`` : reçoit une **liste** de waveforms
    (un tick de série peut combiner plusieurs voies), imite le même nommage
    que le vrai ``save_capture`` -- un binaire par voie, un CSV combiné (sans
    suffixe de voie) une fois pour toutes les voies du tick."""

    def save(waveforms, path_base, formats=("csv", "npy")):
        binary_formats = [f for f in formats if f != "csv"]
        paths = []
        for wf in waveforms:
            for fmt in binary_formats:
                paths.append(f"{path_base}_{wf.channel}.{fmt}")
        if "csv" in formats and waveforms:
            paths.append(f"{path_base}.csv")
        written.extend(paths)
        return paths

    return save


def test_run_series_now_captures_expected_count(tmp_path):
    written = []
    config = series.SeriesConfig(
        experiment_id="essai1",
        channels=["C1"],
        outdir=str(tmp_path),
        rate=1,
        per_seconds=1,
        duration_max=2.5,
        start_mode="now",
    )
    result = series.run_series(
        config,
        FakeScope(),
        clock=FakeClock(step=0.01),
        sleep=lambda _s: None,
        fetch=_make_fetch(),
        save=_make_save(written),
    )
    assert result.started is True
    # deadlines 0, 1, 2 -> 3 captures (2.5s max)
    assert len(result.captures) == 3
    assert written == [
        os.path.join(str(tmp_path), "essai1", "essai1_0001_C1.npy"),
        os.path.join(str(tmp_path), "essai1", "essai1_0001.csv"),
        os.path.join(str(tmp_path), "essai1", "essai1_0002_C1.npy"),
        os.path.join(str(tmp_path), "essai1", "essai1_0002.csv"),
        os.path.join(str(tmp_path), "essai1", "essai1_0003_C1.npy"),
        os.path.join(str(tmp_path), "essai1", "essai1_0003.csv"),
    ]


def test_run_series_threshold_never_reached_captures_nothing(tmp_path):
    config = series.SeriesConfig(
        experiment_id="essai2",
        channels=["C1"],
        outdir=str(tmp_path),
        rate=1,
        per_seconds=1,
        duration_max=5.0,
        start_mode="threshold",
        threshold={"channel": "C1", "level": "1V", "slope": "POS", "timeout_s": 1.0},
    )
    result = series.run_series(
        config,
        FakeScope(),
        clock=FakeClock(),
        sleep=lambda _s: None,
        fetch=_make_fetch(),
        save=_make_save([]),
        wait=lambda scope_arg, *, timeout_s: False,
    )
    assert result.started is False
    assert result.captures == []
    assert not (tmp_path / "essai2").exists()


def test_run_series_isolates_channel_failure(tmp_path):
    written = []
    config = series.SeriesConfig(
        experiment_id="essai3",
        channels=["C1", "C2"],
        outdir=str(tmp_path),
        rate=1,
        per_seconds=1,
        duration_max=0.5,
        start_mode="now",
    )
    result = series.run_series(
        config,
        FakeScope(),
        clock=FakeClock(step=0.01),
        sleep=lambda _s: None,
        fetch=_make_fetch(failing_channel="C2"),
        save=_make_save(written),
    )
    assert len(result.captures) == 1
    assert result.captures[0]["errors"] == ["C2 : acquisition vide"]
    # CSV combiné (une seule voie a réussi -> pas de suffixe voie) + npy C1
    assert any(p.endswith("essai3_0001.csv") for p in written)
    assert any(p.endswith("essai3_0001_C1.npy") for p in written)


def test_run_series_writes_meta_sidecar(tmp_path):
    config = series.SeriesConfig(
        experiment_id="essai4",
        channels=["C1"],
        outdir=str(tmp_path),
        rate=2,
        per_seconds=1,
        duration_max=0.6,
        start_mode="now",
    )
    result = series.run_series(
        config,
        FakeScope(),
        clock=FakeClock(step=0.01),
        sleep=lambda _s: None,
        fetch=_make_fetch(),
        save=_make_save([]),
    )
    meta_path = tmp_path / "essai4" / "essai4_meta.json"
    assert meta_path.exists()
    assert result.meta_path == str(meta_path)
    meta = json.loads(meta_path.read_text())
    assert meta["experiment_id"] == "essai4"
    assert meta["channels"] == ["C1"]
    assert meta["rate"] == 2
    assert meta["per_seconds"] == 1
    assert meta["points"] == 4000
    assert len(meta["captures"]) == len(result.captures)
    assert meta["u_channel"] is None and meta["i_channel"] is None  # rétro-compatible


def test_meta_records_plateau_channels(tmp_path):
    config = series.SeriesConfig(
        experiment_id="essai5", channels=["C2", "C3"], outdir=str(tmp_path),
        rate=1, per_seconds=1, duration_max=0, u_channel="C2", i_channel="C3",
    )
    (tmp_path / "essai5").mkdir()
    meta = json.loads(open(series.write_series_meta(config, [])).read())
    assert meta["u_channel"] == "C2" and meta["i_channel"] == "C3"


# --- parsing CLI (durée, unité de cadence) --------------------------------------------
@pytest.mark.parametrize(
    "text, expected",
    [
        ("30s", 30.0),
        ("5m", 300.0),
        ("2h", 7200.0),
        ("90", 90.0),  # nombre nu = secondes
        ("1.5h", 5400.0),
    ],
)
def test_parse_duration(text, expected):
    assert series.parse_duration(text) == pytest.approx(expected)


def test_parse_duration_rejects_bad_unit():
    with pytest.raises(ValueError):
        series.parse_duration("5x")


@pytest.mark.parametrize(
    "unit, expected",
    [("second", 1.0), ("minute", 60.0), ("hour", 3600.0)],
)
def test_per_unit_seconds(unit, expected):
    assert series.PER_UNIT_SECONDS[unit] == expected


def test_run_series_decimates_to_default_points(tmp_path):
    """Une capture = un instantané décimé, comme l'affichage GUI/live (défaut 4000
    points) -- pas le dump brut de la mémoire profonde. Décimation active par défaut,
    sans avoir à la demander explicitement."""
    seen = []

    def fetch(scope, channel):
        return FakeWaveform(channel)

    def fake_decimate(t, v, max_points):
        seen.append(max_points)
        return t, v

    config = series.SeriesConfig(
        experiment_id="essai5",
        channels=["C1"],
        outdir=str(tmp_path),
        rate=1,
        per_seconds=1,
        duration_max=0.5,
        start_mode="now",
    )
    series.run_series(
        config,
        FakeScope(),
        clock=FakeClock(step=0.01),
        sleep=lambda _s: None,
        fetch=fetch,
        save=_make_save([]),
        decimate=fake_decimate,
    )
    assert seen == [4000]


def test_run_series_custom_points_overrides_default(tmp_path):
    seen = []

    def fetch(scope, channel):
        return FakeWaveform(channel)

    def fake_decimate(t, v, max_points):
        seen.append(max_points)
        return t, v

    config = series.SeriesConfig(
        experiment_id="essai6",
        channels=["C1"],
        outdir=str(tmp_path),
        rate=1,
        per_seconds=1,
        duration_max=0.5,
        start_mode="now",
        points=100,
    )
    series.run_series(
        config,
        FakeScope(),
        clock=FakeClock(step=0.01),
        sleep=lambda _s: None,
        fetch=fetch,
        save=_make_save([]),
        decimate=fake_decimate,
    )
    assert seen == [100]


# --- SeriesRunner (machine à états Qt-free, pilotée pas à pas par la GUI) --------------
def test_capture_once_saves_channels_and_returns_waveforms(tmp_path):
    written = []
    config = series.SeriesConfig(
        experiment_id="essai7",
        channels=["C1"],
        outdir=str(tmp_path),
        rate=1,
        per_seconds=1,
        duration_max=1.0,
    )
    rec = series.capture_once(
        config, FakeScope(), 1, str(tmp_path), fetch=_make_fetch(), save=_make_save(written)
    )
    assert rec["index"] == 1
    assert rec["errors"] == []
    assert "C1" in rec["waveforms"]
    assert any(p.endswith("essai7_0001.csv") for p in written)


def test_capture_once_applies_channel_configs():
    """Le label/unité/facteur configuré par voie (channels_config.json) doit
    atteindre la waveform sauvée -- pas seulement en GUI (signalement
    utilisateur : l'export doit tenir compte du nom donné au signal)."""
    from scope.channel_config import ChannelConfig

    config = series.SeriesConfig(
        experiment_id="essai9",
        channels=["C1"],
        outdir="unused",
        rate=1,
        per_seconds=1,
        duration_max=1.0,
        configs={"C1": ChannelConfig(label="Vbat", unit="V", factor=2.0)},
    )
    rec = series.capture_once(
        config, FakeScope(), 1, "unused", fetch=_make_fetch(), save=_make_save([])
    )
    wf = rec["waveforms"]["C1"]
    assert wf.label == "Vbat"
    assert wf.factor == 2.0


def test_capture_once_isolates_channel_failure():
    config = series.SeriesConfig(
        experiment_id="essai8",
        channels=["C1", "C2"],
        outdir="unused",
        rate=1,
        per_seconds=1,
        duration_max=1.0,
    )
    rec = series.capture_once(
        config,
        FakeScope(),
        1,
        "unused",
        fetch=_make_fetch(failing_channel="C2"),
        save=_make_save([]),
    )
    assert rec["errors"] == ["C2 : acquisition vide"]
    assert list(rec["waveforms"]) == ["C1"]


def test_arm_threshold_writes_expected_scpi():
    scope = FakeScope()
    series.arm_threshold(
        scope, {"channel": "C2", "level": "5V", "slope": "POS", "timeout_s": 30.0}
    )
    joined = " ".join(scope.writes)
    assert "TRSE EDGE,SR,C2" in joined
    assert "C2:TRLV 5V" in joined
    assert "C2:TRSL POS" in joined
    assert "TRMD SINGLE" in joined
    assert "ARM" in joined


def _runner_config(tmp_path, **overrides):
    defaults = dict(
        experiment_id="run1",
        channels=["C1"],
        outdir=str(tmp_path),
        rate=1,
        per_seconds=1,
        duration_max=2.5,
        start_mode="now",
    )
    defaults.update(overrides)
    return series.SeriesConfig(**defaults)


def _drive(runner, scope, clock, max_steps=1000):
    """Fait avancer un SeriesRunner jusqu'à la fin, collecte tous les events."""
    events = []
    steps = 0
    while not runner.finished and steps < max_steps:
        events.extend(runner.step(scope, clock()))
        steps += 1
    assert steps < max_steps, "SeriesRunner ne termine jamais (boucle infinie ?)"
    return events


def test_series_runner_now_mode_captures_and_finishes(tmp_path):
    written = []
    config = _runner_config(tmp_path, start_mode="now")
    runner = series.SeriesRunner(
        config,
        clock=FakeClock(step=0.5),
        fetch=_make_fetch(),
        save=_make_save(written),
    )
    events = _drive(runner, FakeScope(), FakeClock(step=0.5))

    kinds = [e.kind for e in events]
    assert kinds[0] == "started"
    assert kinds.count("capture") == 3  # deadlines 0, 1, 2 <= 2.5s
    assert kinds[-1] == "done"
    assert runner.result.started is True
    assert len(runner.result.captures) == 3
    assert runner.result.meta_path is not None


def test_series_runner_countdown_then_runs(tmp_path):
    config = _runner_config(tmp_path, start_mode="countdown", delay_s=2.0, duration_max=0.5)
    clock = FakeClock(step=0.5)
    runner = series.SeriesRunner(config, clock=clock, fetch=_make_fetch(), save=_make_save([]))

    events = _drive(runner, FakeScope(), clock)
    kinds = [e.kind for e in events]
    assert "countdown" in kinds
    assert "started" in kinds
    assert kinds.index("countdown") < kinds.index("started")
    assert runner.result.started is True


def test_series_runner_threshold_reached_calls_arm_then_runs(tmp_path):
    armed = []
    polls = iter([False, False, True])
    config = _runner_config(
        tmp_path,
        start_mode="threshold",
        threshold={"channel": "C1", "level": "1V", "slope": "POS", "timeout_s": 10.0},
        duration_max=0.5,
    )
    clock = FakeClock(step=0.05)
    runner = series.SeriesRunner(
        config,
        clock=clock,
        arm=lambda scope, threshold: armed.append(threshold),
        poll=lambda scope: next(polls),
        fetch=_make_fetch(),
        save=_make_save([]),
    )

    events = _drive(runner, FakeScope(), clock)
    kinds = [e.kind for e in events]
    assert kinds[0] == "armed"
    assert "waiting_threshold" in kinds
    assert "started" in kinds
    assert len(armed) == 1  # armé une seule fois, pas à chaque sondage
    assert runner.result.started is True


def test_series_runner_threshold_never_reached_fails_without_files(tmp_path):
    config = _runner_config(
        tmp_path,
        start_mode="threshold",
        threshold={"channel": "C1", "level": "1V", "slope": "POS", "timeout_s": 1.0},
    )
    clock = FakeClock(step=1.0)  # dépasse vite le timeout_s=1.0
    runner = series.SeriesRunner(
        config,
        clock=clock,
        arm=lambda scope, threshold: None,
        poll=lambda scope: False,
        fetch=_make_fetch(),
        save=_make_save([]),
    )

    events = _drive(runner, FakeScope(), clock)
    assert events[-1].kind == "failed"
    assert runner.result.started is False
    assert runner.result.captures == []
    assert runner.result.meta_path is None
    assert not (tmp_path / config.experiment_id).exists()


def test_series_runner_request_stop_finalizes_with_partial_captures(tmp_path):
    written = []
    config = _runner_config(tmp_path, duration_max=10.0)  # durée large, on arrête nous-même
    clock = FakeClock(step=0.5)
    runner = series.SeriesRunner(config, clock=clock, fetch=_make_fetch(), save=_make_save(written))

    events = []
    # laisse passer exactement 2 captures puis demande l'arrêt
    while len([e for e in events if e.kind == "capture"]) < 2:
        events.extend(runner.step(FakeScope(), clock()))
    runner.request_stop()
    events.extend(_drive(runner, FakeScope(), clock))

    assert events[-1].kind == "done"
    assert len(runner.result.captures) == 2
    assert runner.result.meta_path is not None


def test_series_runner_scope_error_while_waiting_threshold_ends_cleanly(tmp_path):
    # scope débranché pendant l'attente du seuil : la série se termine (au lieu de
    # remonter l'exception et de tuer le thread d'acquisition de la GUI)
    config = _runner_config(
        tmp_path, start_mode="threshold",
        threshold={"channel": "C1", "level": "1V", "slope": "POS", "timeout_s": 60.0},
    )

    def poll(scope):
        raise OSError("VI_ERROR_TMO : délai dépassé")

    clock = FakeClock(step=0.5)
    runner = series.SeriesRunner(config, clock=clock, arm=lambda s, t: None, poll=poll,
                                 fetch=_make_fetch(), save=_make_save([]))
    events = _drive(runner, FakeScope(), clock)
    assert runner.finished and events[-1].kind == "failed"
    assert "délai dépassé" in events[-1].message
    assert runner.result.started is False
    assert not (tmp_path / config.experiment_id).exists()


def test_series_runner_scope_error_while_running_keeps_captures(tmp_path, monkeypatch):
    config = _runner_config(tmp_path, duration_max=10.0)
    clock = FakeClock(step=0.5)
    runner = series.SeriesRunner(config, clock=clock, fetch=_make_fetch(), save=_make_save([]))
    events = []
    while len([e for e in events if e.kind == "capture"]) < 2:
        events.extend(runner.step(FakeScope(), clock()))

    def lost(*a, **k):
        raise ConnectionResetError("connexion perdue")

    monkeypatch.setattr(series, "capture_once", lost)
    events.extend(_drive(runner, FakeScope(), clock))
    assert runner.finished and events[-1].kind == "failed"
    assert "connexion perdue" in events[-1].message
    assert runner.result.started is True and len(runner.result.captures) == 2
    assert runner.result.meta_path is not None  # captures déjà faites conservées


# --- traçabilité (meta v2) -----------------------------------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402

from scope import experiment  # noqa: E402
from scope.channel_config import ChannelConfig  # noqa: E402


class WallClock:
    """Heure murale factice : +1 s à chaque lecture."""

    def __init__(self):
        self.t = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


def _real_save(waveforms, path_base, formats=("csv", "npy")):
    """Écrit vraiment un fichier par capture (pour les empreintes)."""
    path = f"{path_base}.csv"
    with open(path, "w") as fh:
        fh.write("time_s,C1_V\n0,1\n")
    return [path]


def _traced_runner(tmp_path, **overrides):
    fiche = experiment.empty_fiche()
    experiment.set_field(fiche, "operateur", "BDV")
    config = _runner_config(tmp_path, fiche=fiche, armed_at="2026-10-06T07:59:00+00:00",
                            configs={"C1": ChannelConfig(label="sonde HT", unit="kV", factor=2.0)},
                            **overrides)
    return series.SeriesRunner(config, clock=FakeClock(step=0.5), fetch=_make_fetch(),
                               save=_real_save, wall_clock=WallClock())


def test_runner_creates_meta_at_start_with_fiche_and_dates(tmp_path):
    runner = _traced_runner(tmp_path)
    clock = FakeClock(step=0.5)
    events = runner.step(FakeScope(), clock())
    assert events[0].kind == "started"
    meta = experiment.load_meta(tmp_path / "run1")  # existe dès la détection
    assert meta["fiche"]["operateur"] == "BDV"
    assert meta["dates"]["armee"] == "2026-10-06T07:59:00+00:00"
    assert meta["dates"]["debut"].startswith("2026-10-06T08:00")
    assert meta["acquisition"]["voies"]["C1"] == {"label": "sonde HT", "unit": "kV", "factor": 2.0}
    assert len(meta["uuid"]) == 32 and meta["station"] and meta["utilisateur_windows"]


def test_runner_final_meta_has_wall_times_checksums_and_keeps_fiche_edits(tmp_path):
    runner = _traced_runner(tmp_path)
    clock = FakeClock(step=0.5)
    runner.step(FakeScope(), clock())
    # modification de la fiche pendant l'enregistrement (thread UI)
    experiment.update_meta(tmp_path / "run1", lambda m: experiment.apply_fiche(
        m, dict(m["fiche"], notes="arc visible"), user="bdv", when="2026-10-06T08:00:30+00:00"))
    _drive(runner, FakeScope(), clock)
    meta = experiment.load_meta(tmp_path / "run1")
    assert meta["fiche"]["notes"] == "arc visible"          # non écrasée par la fin de série
    assert meta["historique"][-1]["champ"] == "notes"
    assert all(c["heure"].startswith("2026-10-06T08:") for c in meta["captures"])
    assert meta["dates"]["fin"] > meta["dates"]["debut"]
    assert sorted(meta["empreintes"]) == ["run1_0001.csv", "run1_0002.csv", "run1_0003.csv"]
    assert meta["empreintes_info"]["a_posteriori"] is False
    assert experiment.verify_checksums(meta, tmp_path / "run1")["modifie"] == []


def test_runner_refuses_existing_non_empty_series_dir(tmp_path):
    (tmp_path / "run1").mkdir()
    (tmp_path / "run1" / "run1_meta.json").write_text("{}")
    runner = _traced_runner(tmp_path)
    events = runner.step(FakeScope(), FakeClock()())
    assert events[0].kind == "failed" and "existe" in events[0].message
    assert runner.result.started is False
    assert (tmp_path / "run1" / "run1_meta.json").read_text() == "{}"  # rien écrasé


def test_run_series_cli_also_refuses_existing_dir(tmp_path):
    (tmp_path / "run1").mkdir()
    (tmp_path / "run1" / "x.csv").write_text("")
    with pytest.raises(FileExistsError):
        series.run_series(_runner_config(tmp_path), FakeScope(), clock=FakeClock(),
                          sleep=lambda _s: None, fetch=_make_fetch(), save=_make_save([]))
