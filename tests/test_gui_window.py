"""Fenêtre principale de bout en bout (Qt hors écran), scope simulé.

Vrais widgets, vrai thread d'acquisition, vraie machine à états de série et vraie
analyse des plateaux ; seuls la connexion VISA et le fetch des voies sont simulés
(créneaux PEO : U = 272 V sur C2, I = 8 A sur C3 en mA). Ignoré si PyQt5 manque
(Python système) : lancer avec le .venv créé par install.ps1.
"""
import json
import os
import time

import numpy as np
import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pyqtgraph.Qt import QtWidgets  # noqa: E402

from scope import connection, gui, series  # noqa: E402
from scope.waveform import Waveform  # noqa: E402

CHANNELS_CONFIG = {
    "C1": {"label": "signal calib", "unit": "V", "factor": 1.0},
    "C2": {"label": "sonde HT", "unit": "V", "factor": 1.0},
    "C3": {"label": "I", "unit": "mA", "factor": 1.0},
    "C4": {"label": "", "unit": "V", "factor": 1.0},
}


def fake_fetch(scope, channel):
    t = -0.014 + 14e-6 * np.arange(2001)
    on = ((t + 0.0133) % (1 / 150)) < 2.07e-3
    level = {"C2": 272.0, "C3": 8000.0}.get(channel, 1.0)
    return Waveform(channel, t, np.where(on, level, 0.0), vdiv=1.0, offset=0.0, interval=14e-6)


class Sim:
    """Comportement du scope simulé, réglé par chaque test."""
    connect_error = None   # exception levée à l'ouverture de la liaison
    idn_error = None       # exception levée par *IDN? (liaison ouverte, scope muet)
    threshold_reached = False
    poll_error = None      # exception levée en sondant le seuil


class FakeScope:
    def __init__(self, *a, **k):
        if Sim.connect_error:
            raise Sim.connect_error

    def idn(self):
        if Sim.idn_error:  # liaison ouverte mais le scope ne répond pas (vu sur le terrain)
            raise Sim.idn_error
        return "Siglent,SDS1204X-E,SIMULÉ"

    def write(self, cmd):
        pass

    def query(self, cmd):
        return "0"

    def close(self):
        pass


class FakeRunner(series.SeriesRunner):
    def __init__(self, config, *, clock, **kw):
        def poll(_scope):
            if Sim.poll_error:
                raise Sim.poll_error
            return Sim.threshold_reached

        super().__init__(config, clock=clock, arm=lambda s, t: None, poll=poll, fetch=fake_fetch)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def make_window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "Scope", FakeScope)
    monkeypatch.setattr(gui.series, "SeriesRunner", FakeRunner)
    monkeypatch.setattr(Sim, "connect_error", None)
    monkeypatch.setattr(Sim, "idn_error", None)
    monkeypatch.setattr(Sim, "threshold_reached", False)
    monkeypatch.setattr(Sim, "poll_error", None)
    boxes = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: boxes.append(a[1:3]))
    windows = []

    def make(settings=None):
        (tmp_path / "channels_config.json").write_text(json.dumps(CHANNELS_CONFIG), encoding="utf-8")
        st = {"series_rate": "1", "series_per": "second", "series_duration": "60s",
              "outdir": str(tmp_path / "captures"), **(settings or {})}
        (tmp_path / "gui_settings.json").write_text(json.dumps(st), encoding="utf-8")
        win = gui._build_main_window("10.11.13.220", socket=True, timeout_ms=1000,
                                     config_path=tmp_path / "channels_config.json")
        win.message_boxes = boxes
        windows.append(win)
        return win

    yield make
    for win in windows:
        win.close()
        # destruction Qt explicite : sinon pyqtgraph nettoie ses légendes à la sortie de
        # Python, après Qt (AttributeError '_sizeHint' affichées, sans effet sur les tests)
        win.deleteLater()
        app.processEvents()


def pump(app, seconds, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.02)
    return bool(until and until())


def idle(win):
    return not win._armed and not win._recording


# --- connexion ------------------------------------------------------------------------
@pytest.mark.parametrize("failure", ["connect_error", "idn_error"])
def test_arming_impossible_until_connected(app, make_window, monkeypatch, failure):
    # idn_error : cas du terrain (journal du 2026-10-06 13:28) -- liaison ouverte, *IDN?
    # sans réponse : l'exception tuait le thread d'acquisition, l'UI restait « armée »
    monkeypatch.setattr(Sim, failure, TimeoutError("VI_ERROR_TMO : délai dépassé"))
    win = make_window()
    assert pump(app, 3, until=lambda: "Échec de connexion" in win.status.currentMessage())
    assert not win.btn_series_start.isEnabled()
    assert not win.btn_capture.isEnabled()
    assert "connect" in win.btn_series_start.toolTip().lower()


def test_arming_enabled_once_connected(app, make_window):
    win = make_window()
    assert pump(app, 3, until=win.btn_series_start.isEnabled)
    assert win.btn_capture.isEnabled()


# --- arrêter ----------------------------------------------------------------------------
def test_stop_while_waiting_for_threshold(app, make_window):
    win = make_window()
    pump(app, 3, until=win.btn_series_start.isEnabled)
    win.btn_series_start.click()
    assert pump(app, 3, until=lambda: "waiting_threshold" in win.status.currentMessage())
    win.btn_series_stop.click()
    assert pump(app, 3, until=lambda: idle(win) and win.btn_series_start.isEnabled())


def test_stop_resets_ui_even_if_acquisition_thread_is_gone(app, make_window):
    win = make_window()
    pump(app, 3, until=win.btn_series_start.isEnabled)
    win.btn_series_start.click()
    pump(app, 1)
    win.cmd_queue.put(("quit",))  # thread d'acquisition arrêté (liaison perdue)
    assert win.worker.wait(5000)
    win.btn_series_stop.click()
    assert pump(app, 3, until=lambda: idle(win) and not win.btn_series_stop.isEnabled())
    assert not win.btn_series_start.isEnabled()  # plus de scope : pas de nouvel armement


def test_scope_error_during_series_ends_it_cleanly(app, make_window, monkeypatch):
    monkeypatch.setattr(Sim, "poll_error", OSError("VI_ERROR_TMO : délai dépassé"))
    win = make_window()
    pump(app, 3, until=win.btn_series_start.isEnabled)
    win.btn_series_start.click()
    assert pump(app, 5, until=lambda: idle(win) and win.btn_series_start.isEnabled())
    assert any("délai dépassé" in str(b) for b in win.message_boxes)


# --- analyse en direct ------------------------------------------------------------------
def test_live_analysis_updates_while_recording(app, make_window, monkeypatch):
    monkeypatch.setattr(Sim, "threshold_reached", True)
    win = make_window({"active_channels": ["C2", "C3"]})
    pump(app, 3, until=win.btn_series_start.isEnabled)
    win.btn_series_start.click()
    assert pump(app, 10, until=lambda: len(win._evo["t"]) >= 2)
    assert win._evo["U_med_pos"][0] == pytest.approx(272, abs=8)
    assert win._evo["I_med_pos"][0] == pytest.approx(8.0, abs=0.2)
    win.btn_series_stop.click()
    assert pump(app, 10, until=lambda: idle(win))


def test_fresh_install_records_analysis_channels(app, make_window, monkeypatch):
    # installation neuve (pas de réglage mémorisé) : C2/C3 cochées, l'analyse tourne
    monkeypatch.setattr(Sim, "threshold_reached", True)
    win = make_window()
    assert win.active_channels == {"C2", "C3"}
    pump(app, 3, until=win.btn_series_start.isEnabled)
    win.btn_series_start.click()
    assert pump(app, 10, until=lambda: len(win._evo["t"]) >= 1)
    win.btn_series_stop.click()
    assert pump(app, 10, until=lambda: idle(win))


@pytest.mark.parametrize("choice, armed, analysed", [("check", True, True),
                                                     ("without", True, False),
                                                     ("cancel", False, False)])
def test_arming_asks_when_analysis_channels_not_checked(app, make_window, monkeypatch,
                                                        choice, armed, analysed):
    win = make_window({"active_channels": ["C1"]})
    pump(app, 3, until=win.btn_series_start.isEnabled)
    asked = []
    monkeypatch.setattr(win, "_ask_analysis_channels", lambda missing: asked.append(missing) or choice)
    win.btn_series_start.click()
    pump(app, 0.5)
    assert asked == [["C2", "C3"]]
    assert win._armed is armed
    if armed:
        assert (win._config.u_channel is not None) is analysed
        assert {"C2", "C3"} <= set(win._config.channels) or not analysed
        win.btn_series_stop.click()
        assert pump(app, 5, until=lambda: idle(win))
