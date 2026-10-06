"""Regenerate the showcase screenshots (docs/screenshots/) from the SYNTHETIC demo series.

The real application runs off-screen; only the oscilloscope is simulated: it replays
the captures of examples/demo-data/PEO_DEMO_01 (one per second instead of one per
30 s, to keep the run short). Everything else -- arming, threshold start, CSV
writing, live plateau analysis, end-of-series synthesis, record form,
traceability, re-processing -- is the production code path.

    .venv\\Scripts\\python.exe tools\\capture_showcase.py
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from pyqtgraph.Qt import QtWidgets  # noqa: E402

from scope import connection, experiment, gui, gui_experiment, plateaux, series  # noqa: E402
from scope.waveform import Waveform  # noqa: E402

DEMO = ROOT / "examples" / "demo-data" / "PEO_DEMO_01"
OUT = ROOT / "docs" / "screenshots"
FILES = sorted(DEMO.glob("PEO_DEMO_01_[0-9][0-9][0-9][0-9].csv"))
DEMO_FICHE = {
    "operateur": "Demo operator", "objectif": "Showcase run (synthetic data)",
    "echantillon.id": "DEMO-001", "echantillon.materiau": "Al alloy (demo)",
    "echantillon.surface_cm2": "12.5", "echantillon.preparation": "Degreased, rinsed",
    "bain.composition": "Silicate-alkaline (demo)", "bain.concentration": "10 g/L",
    "bain.temperature_C": "20", "bain.pH": "12", "bain.reference": "Demo bath",
    "consigne.mode": "courant", "consigne.valeur": "8.8", "consigne.unite": "A",
    "consigne.frequence_Hz": "150", "consigne.rapport_cyclique": "0.31",
    "consigne.polarite": "unipolaire", "consigne.duree_prevue": "8 min",
}


class ReplayScope:
    def __init__(self, *a, **k):
        pass

    def idn(self):
        return "Siglent Technologies,SDS1204X-E,SIMULATED (replays demo data)"

    def write(self, cmd):
        pass

    def query(self, cmd):
        return "0"

    def close(self):
        pass


calls = {"C2": 0, "C3": 0}


def replay_fetch(scope, channel):
    k = calls[channel]
    calls[channel] += 1
    d = pd.read_csv(FILES[min(k, len(FILES) - 1)])
    return Waveform(channel, d.iloc[:, 0].to_numpy(float), d.iloc[:, 1 if channel == "C2" else 2].to_numpy(float),
                    vdiv=1.0, offset=0.0, interval=float(d.iloc[1, 0] - d.iloc[0, 0]))


class ReplayRunner(series.SeriesRunner):
    def __init__(self, config, *, clock, **kw):
        armed_at = time.monotonic()
        super().__init__(config, clock=clock, poll=lambda s: time.monotonic() - armed_at > 1.5,
                         fetch=replay_fetch)


def main() -> None:
    if not FILES:
        sys.exit("demo data missing: run python examples/make_demo_data.py")
    connection.Scope = ReplayScope
    gui.series.SeriesRunner = ReplayRunner
    # Public screenshots: never the real workstation or Windows account names
    series.socket.gethostname = lambda: "demo-station"
    experiment.current_user = lambda: "demo"
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="peo_showcase_"))
    (tmp / "channels_config.json").write_text(json.dumps({
        "C1": {"label": "calib", "unit": "V", "factor": 1.0},
        "C2": {"label": "HV probe", "unit": "V", "factor": 1.0},
        "C3": {"label": "I", "unit": "A", "factor": 1.0},
        "C4": {"label": "", "unit": "V", "factor": 1.0}}), encoding="utf-8")
    (tmp / "gui_settings.json").write_text(json.dumps({
        "active_channels": ["C2", "C3"], "series_rate": "1", "series_per": "second",
        "series_duration": f"{len(FILES) - 1}s", "outdir": str(tmp / "captures"), "id_prefix": "PEO",
        "start_mode": "threshold", "trig_src": "C2", "trig_slope": "POS", "trig_level": "1",
        "vdiv": {"C2": "1V", "C3": "200MV"}, "coupling": {"C2": "D1M", "C3": "D1M"}, "tdiv": "2MS"}),
        encoding="utf-8")

    app = QtWidgets.QApplication([])
    win = gui._build_main_window("10.11.13.220", socket=True, timeout_ms=1000,
                                 config_path=tmp / "channels_config.json")
    win.resize(1500, 950)
    win.show()

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if until is not None and until():
                return True
            time.sleep(0.02)
        return bool(until and until())

    def save(widget, name):
        widget.grab().save(str(OUT / name))
        print(f"  {OUT / name}")

    fiche = experiment.empty_fiche()
    for key, value in DEMO_FICHE.items():
        experiment.set_field(fiche, key, value)
    win.fiche_form.set_fiche(fiche)
    assert pump(10, until=win.btn_series_start.isEnabled), "simulated scope not connected"
    pump(1)
    print("screenshots:")
    save(win, "01-measure.png")

    win.btn_series_start.click()
    assert pump(30, until=lambda: len(win._evo["t"]) >= 9), "live analysis did not progress"
    pump(0.3)
    save(win, "02-analysis-live.png")
    assert pump(30, until=lambda: not (win._armed or win._recording)), "series did not finish"
    pump(1)
    save(win, "03-analysis-end.png")

    series_dir = next((tmp / "captures").glob("PEO_*"))
    _, FicheDialog = gui_experiment.widgets()
    dialog = FicheDialog(series_dir, (), win)
    dialog.resize(900, 640)
    tabs = dialog.findChild(QtWidgets.QTabWidget)
    tabs.setCurrentIndex(tabs.count() - 1)  # Traçabilité
    dialog.show()
    pump(0.5)
    save(dialog, "04-traceability.png")
    dialog.close()

    # Re-processing (same function as tools/extract_plateaux.py): control sheet + U/I/f vs t
    work = tmp / "reprocess"
    experiment.reprocess(shutil.copytree(DEMO, work / DEMO.name), user="demo",
                         when=experiment.now_iso(), out_dir=work / "out", per_capture_png=False)
    # Control sheet excerpt: captures 10-15, so that the isolated dip (#13) shows its red veil.
    # Flags between captures (U_saut) are set by the end-of-series synthesis, as in the app.
    rows, captures = [], []
    for k, f in enumerate(FILES, start=1):
        d = pd.read_csv(f)
        t, U, I = (d.iloc[:, j].to_numpy(float) for j in range(3))
        row, traces = plateaux.analyse_arrays(t, U, I)
        row = {"index": k, "t_s": 30.0 * (k - 1), **row}
        rows.append(row)
        captures.append((row, traces or (t, U, I, [], [])))
    (work / "synthesis").mkdir()
    plateaux.finalize_series(work / "synthesis", "PEO_DEMO_01", rows)  # updates the flags in place (U_saut)
    plateaux.save_control_png(captures[9:15], OUT / "05-control-sheet.png", title="PEO_DEMO_01")
    print(f"  {OUT / '05-control-sheet.png'}")
    shutil.copy(work / "out" / "PEO_DEMO_01_UI_vs_t.png", OUT / "06-ui-vs-t.png")
    print(f"  {OUT / '06-ui-vs-t.png'}")
    win.close()


if __name__ == "__main__":
    main()
