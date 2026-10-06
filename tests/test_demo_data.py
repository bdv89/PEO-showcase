"""The synthetic demo series (examples/make_demo_data.py) must exhibit, after the real
analysis chain, exactly the features it was designed with -- the showcase claims rest
on it. Runs on a copy: re-processing writes into the series' meta.json."""
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scope import experiment

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo-data" / "PEO_DEMO_01"


@pytest.fixture(scope="module")
def analysed(tmp_path_factory):
    work = tmp_path_factory.mktemp("demo")
    if not DEMO.is_dir():
        subprocess.run([sys.executable, str(ROOT / "examples" / "make_demo_data.py")], check=True)
    series = shutil.copytree(DEMO, work / DEMO.name)
    summary = experiment.reprocess(series, user="test", when="2026-10-06T12:00:00+02:00",
                                   out_dir=work / "out", per_capture_png=False)
    df = pd.read_csv(work / "out" / "PEO_DEMO_01_plateaux.csv", encoding="utf-8-sig").set_index("index")
    return summary, df


def test_demo_series_is_fully_analysed(analysed):
    summary, df = analysed
    assert summary["n_captures"] == 16 and summary["n_ok"] == 15
    assert df["freq_Hz"].dropna().between(148, 152).all()
    assert df["duty"].dropna().between(0.28, 0.34).all()


def test_demo_voltage_dip_is_flagged(analysed):
    _, df = analysed
    assert df.index[df["flag"] == "U_saut"].tolist() == [13]


def test_demo_regime_change_is_found(analysed):
    _, df = analysed
    assert (df.loc[2:7, "mode"] == "tension contrôlée").all()
    assert (df.loc[10:16, "mode"].drop(13) == "courant contrôlé").all()
    assert df.loc[10:16, "I_med_pos"].drop(13).between(8.6, 9.0).all()


def test_demo_data_is_labelled_synthetic():
    meta = (DEMO / "PEO_DEMO_01_meta.json").read_text(encoding="utf-8")
    assert "SYNTHETIC" in meta
