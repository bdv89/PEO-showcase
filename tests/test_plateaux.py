"""Tests de l'extraction des plateaux U/I (``scope.plateaux``), sans matériel.

Signaux synthétiques (créneaux de fréquence/rapport cyclique connus, cas types
de PEO) + une non-régression sur une vraie série (``PEO_N_43``) si elle est
présente à côté du projet.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scope import plateaux
from scope.waveform import Waveform

FREQ, DUTY = 500.0, 0.4
U_ON, I_ON = 300.0, 5.0


def square(n=4000, window=28e-3, freq=FREQ, duty=DUTY, u=U_ON, i=I_ON, bipolar=False, noise=0.0, seed=0):
    """Créneau U/I synchrone ; ``bipolar`` ajoute un plateau négatif de même durée."""
    t = np.linspace(-window / 2, window / 2, n)
    phase = ((t - t[0]) * freq) % 1.0
    on = (phase >= 0.1) & (phase < 0.1 + duty)
    sign = on.astype(float)
    if bipolar:
        sign -= ((phase >= 0.55) & (phase < 0.55 + duty * 0.9)).astype(float)
    rng = np.random.default_rng(seed)
    U = u * sign + noise * u * rng.standard_normal(n)
    I = i * sign + noise * i * rng.standard_normal(n)
    return t, U, I


# --- analyse d'une capture ------------------------------------------------------------
def test_square_wave_plateaux_levels_frequency_and_duty():
    t, U, I = square(noise=0.01)
    row, traces = plateaux.analyse_arrays(t, U, I)
    assert row["flag"] == "ok"
    assert row["n_pulses_pos"] >= 12  # 14 périodes, bords tronqués exclus
    assert row["U_med_pos"] == pytest.approx(U_ON, rel=0.01)
    assert row["I_med_pos"] == pytest.approx(I_ON, rel=0.01)
    assert row["freq_Hz"] == pytest.approx(FREQ, rel=0.02)
    assert row["duty"] == pytest.approx(DUTY, rel=0.05)
    t2, U2, I2, runs_pos, runs_neg = traces
    assert len(runs_pos) == row["n_pulses_pos"] and runs_neg == []


def test_bipolar_square_wave_has_negative_plateaux():
    t, U, I = square(bipolar=True)
    row, _ = plateaux.analyse_arrays(t, U, I)
    assert row["flag"] == "ok"
    assert row["n_pulses_neg"] >= 12
    assert row["U_med_neg"] == pytest.approx(-U_ON, rel=0.01)


def test_no_current_is_flagged_no_signal():
    t, U, _ = square()
    row, traces = plateaux.analyse_arrays(t, U, np.zeros_like(t))
    assert row["flag"] == "no_signal" and traces is None


# --- conversion d'unités ---------------------------------------------------------------
@pytest.mark.parametrize(
    "unit, scale, base",
    [("V", 1, "V"), ("mV", 1e-3, "V"), ("kV", 1e3, "V"),
     ("A", 1, "A"), ("mA", 1e-3, "A"), ("µA", 1e-6, "A"), ("uA", 1e-6, "A")],
)
def test_to_si(unit, scale, base):
    values, got_base = plateaux.to_si(np.array([2.0]), unit)
    assert got_base == base
    assert values[0] == pytest.approx(2.0 * scale)


@pytest.mark.parametrize("unit", ["W", "", "Ohm"])
def test_to_si_rejects_unknown_unit(unit):
    with pytest.raises(ValueError):
        plateaux.to_si(np.array([1.0]), unit)


def _wf(channel, t, values, unit):
    return Waveform(channel=channel, time=t, volts=values, vdiv=1.0, offset=0.0,
                    interval=float(t[1] - t[0]), unit=unit)


def test_analyse_waveforms_converts_units_before_thresholds():
    t, U, I = square()
    waveforms = {"C2": _wf("C2", t, U, "V"), "C3": _wf("C3", t, I * 1e3, "mA")}
    row, _ = plateaux.analyse_waveforms(waveforms, "C2", "C3")
    assert row["flag"] == "ok"
    assert row["I_med_pos"] == pytest.approx(I_ON, rel=0.01)


def test_analyse_waveforms_rejects_wrong_quantity():
    t, U, I = square()
    waveforms = {"C2": _wf("C2", t, U, "A"), "C3": _wf("C3", t, I, "A")}
    with pytest.raises(ValueError, match="tension"):
        plateaux.analyse_waveforms(waveforms, "C2", "C3")


def test_analyse_waveforms_missing_channel():
    t, U, _ = square()
    with pytest.raises(ValueError, match="C3"):
        plateaux.analyse_waveforms({"C2": _wf("C2", t, U, "V")}, "C2", "C3")


# --- fichiers produits -----------------------------------------------------------------
def test_save_selection_png_writes_file(tmp_path):
    t, U, I = square()
    _, (t, U, I, rp, rn) = plateaux.analyse_arrays(t, U, I)
    path = tmp_path / "x_0001_plateaux.png"
    plateaux.save_selection_png(t, U, I, rp, rn, path, title="capture 1")
    assert path.stat().st_size > 1000


def _capture(k, u):
    t, U, I = square(u=u, seed=k)
    row, traces = plateaux.analyse_arrays(t, U, I)
    runs = traces[3:] if traces else ([], [])
    return {"index": k, "t_s": 30.0 * k, **row}, (t, U, I, *runs)


def test_control_png_lists_every_capture_one_row_each(tmp_path):
    import matplotlib.image as mpimg

    heights = {}
    for n in (3, 6):
        caps = [_capture(k, 300.0) for k in range(1, n + 1)]
        path = tmp_path / f"essai{n}_controle.png"
        plateaux.save_control_png(caps, path, title="essai")
        heights[n] = mpimg.imread(path).shape[0]
    # une ligne par capture : l'image s'allonge avec le nombre de captures
    assert heights[6] > 1.8 * heights[3]


def test_control_png_includes_captures_without_signal(tmp_path):
    t, U, _ = square()
    row, _ = plateaux.analyse_arrays(t, U, 0 * t)
    caps = [_capture(1, 300.0), ({"index": 2, "t_s": 30.0, **row}, (t, U, 0 * t, [], []))]
    path = tmp_path / "essai_controle.png"
    plateaux.save_control_png(caps, path, title="essai")
    assert path.stat().st_size > 1000
    bad_label = plateaux.control_label(caps[1][0], "essai")
    assert bad_label.startswith("essai_0002.csv") and "ANOMALIE no_signal" in bad_label
    assert "ANOMALIE" not in plateaux.control_label(caps[0][0], "essai")


def test_capture_tag_matches_file_suffix():
    # « 0022 » <-> PEO_N_41_0022.csv : repérage immédiat au défilement
    assert plateaux.capture_tag({"index": 22}) == "0022"


def test_control_png_anomaly_rows_have_red_overlay(tmp_path):
    import matplotlib.image as mpimg

    t, U, _ = square()
    bad, _ = plateaux.analyse_arrays(t, U, 0 * t)
    caps = [_capture(1, 300.0), ({"index": 2, "t_s": 30.0, **bad}, (t, U, 0 * t, [], []))]
    path = tmp_path / "essai_controle.png"
    plateaux.save_control_png(caps, path, title="essai")
    img = mpimg.imread(path)[..., :3]
    h = img.shape[0]
    redness = lambda part: float((part[..., 0] - part[..., 1]).mean())  # noqa: E731
    # ligne 2 (anomalie) nettement plus rouge que la ligne 1 (ok)
    assert redness(img[h // 2:]) > redness(img[:h // 2]) + 0.05


# --- anomalies entre captures voisines (sauts de U, ruptures de régime) -------------------
def jump_df(U, I=None):
    n = len(U)
    return pd.DataFrame({"index": range(1, n + 1), "t_s": 30.0 * np.arange(n), "flag": "ok",
                         "U_med_pos": np.asarray(U, float),
                         "I_med_pos": np.full(n, 8.8) if I is None else np.asarray(I, float)})


def test_isolated_voltage_drop_is_flagged():
    df = jump_df([280, 288, 296, 304, 208, 312, 320, 320])
    plateaux.flag_jumps(df)
    assert df.loc[df["flag"] == "U_saut", "index"].tolist() == [5]


def test_voltage_drop_on_last_capture_is_flagged():
    df = jump_df([320, 336, 344, 344, 344, 200])
    plateaux.flag_jumps(df)
    assert df.loc[df["flag"] == "U_saut", "index"].tolist() == [6]


def test_fast_rise_at_start_is_not_a_jump():
    df = jump_df([176, 216, 232, 240, 248, 248, 256])  # début de PEO_N_41
    plateaux.flag_jumps(df)
    assert (df["flag"] == "ok").all()


def test_voltage_drop_with_current_change_is_not_a_voltage_jump():
    df = jump_df([280, 288, 296, 304, 208, 312, 320], I=[8.8, 8.8, 8.8, 8.8, 4.0, 8.8, 8.8])
    plateaux.flag_jumps(df)
    assert (df["flag"] == "ok").all()


def test_durable_voltage_collapse_is_a_rupture_not_jumps():
    df = jump_df([256, 320, 328, 56, 40, 40, 32, 32, 32], I=np.full(9, 7.4))  # PEO_N_22
    ruptures = plateaux.flag_jumps(df)
    assert (df["flag"] == "ok").all()
    assert ruptures == "U 328 -> 40 V (#3 -> #5)"


def test_finalize_series_updates_row_flags(tmp_path):
    rows = _rows([300, 310, 320, 330, 220, 350, 360])
    summary = plateaux.finalize_series(tmp_path, "essai", rows)
    assert [r["flag"] for r in rows].count("U_saut") == 1 and rows[4]["flag"] == "U_saut"
    assert summary["n_ok"] == 6


def test_finalize_series_writes_csv_and_png(tmp_path):
    rows = []
    for k in range(8):
        t, U, I = square(u=U_ON + 10 * k, seed=k, noise=0.005)  # U monte : courant contrôlé
        row, _ = plateaux.analyse_arrays(t, U, I)
        rows.append({"index": k + 1, "t_s": 30.0 * k, **row})
    summary = plateaux.finalize_series(tmp_path, "essai", rows)
    assert (tmp_path / "essai_plateaux.csv").exists()
    assert (tmp_path / "essai_UI_vs_t.png").exists()
    assert summary["n_ok"] == 8
    assert summary["mode_majoritaire"] == "courant contrôlé"


def test_finalize_series_without_rows_writes_nothing(tmp_path):
    assert plateaux.finalize_series(tmp_path, "essai", []) is None
    assert list(tmp_path.iterdir()) == []


# --- cas réels de PEO : pointe de coupure, voie U muette, courant haché ----------------
def peo_unipolar(freq=150.0, t_on=2.07e-3, spike=True, seed=0):
    """Capture type PEO_N_41 : 2001 points à 14 µs, U quantifié à 8 V, pointe négative
    (-80 V / -15 A, 3 points) à chaque coupure."""
    rng = np.random.default_rng(seed)
    t = -0.014 + 14e-6 * np.arange(2001)
    on = ((t + 0.0133) % (1 / freq)) < t_on
    U = np.where(on, 272.0, 0.0) + rng.choice([0.0, 8.0], t.size)
    I = np.where(on, 8.0, 0.0) + rng.normal(0, 0.2, t.size)
    if spike:
        for k in np.flatnonzero(np.diff(on.astype(int)) == -1) + 1:
            U[k:k + 3], I[k:k + 3] = -80.0, -15.0
    return t, U, I


def test_turn_off_spike_is_not_a_negative_plateau():
    row, _ = plateaux.analyse_arrays(*peo_unipolar())
    assert row["flag"] == "ok" and row["n_pulses_neg"] == 0
    assert row["freq_Hz"] == pytest.approx(150, rel=0.01)
    assert row["t_on_ms"] == pytest.approx(2.07, rel=0.05)


def test_silent_voltage_channel_is_flagged():
    t, _, I = peo_unipolar()
    U = np.random.default_rng(1).choice([0.0, 8.0], t.size)
    row, _ = plateaux.analyse_arrays(t, U, I)
    assert row["flag"] == "U_absent"


def test_chopped_current_falls_back_to_voltage():
    t, U, I = peo_unipolar(spike=False)
    I = I * np.random.default_rng(2).uniform(0, 1, t.size) ** 3  # micro-décharges
    row, _ = plateaux.analyse_arrays(t, U, I)
    assert row["ref"] == "U" and row["n_pulses_pos"] == 4


# --- mode de pilotage ------------------------------------------------------------------
def mode_series(U, I):
    n = len(U)
    return pd.DataFrame({"index": range(1, n + 1), "t_s": 30.0 * np.arange(n), "flag": "ok",
                         "U_mean_pos": U, "I_mean_pos": I})


def mode_accuracy(make, seeds=200):
    """(fraction juste, fraction inversée) capture par capture sur ``seeds`` tirages ;
    ``make(rng)`` -> (U, I, modes attendus). « indéterminé » n'est ni juste ni inversé."""
    right = wrong = total = 0
    for seed in range(seeds):
        U, I, expected = make(np.random.default_rng(seed))
        df = mode_series(U, I)
        plateaux.estimate_mode(df)
        for got, exp in zip(df["mode"], expected):
            total += 1
            right += got == exp
            wrong += got not in (exp, "indéterminé")
    return right / total, wrong / total


def test_voltage_ramp_with_erratic_current_is_voltage_controlled():
    # rampe de tension programmée, I erratique (micro-décharges) : l'ancien critère
    # (somme des activités) ne trouvait le bon mode que sur ~70 % des captures
    right, wrong = mode_accuracy(lambda rng: (np.linspace(200, 280, 12), rng.uniform(2, 8, 12),
                                              ["tension contrôlée"] * 12))
    assert right >= 0.99 and wrong <= 0.005


def test_regime_change_is_located_without_lag():
    def make(rng):
        U = np.r_[np.linspace(200, 270, 10), np.linspace(276, 330, 10)]
        I = np.r_[rng.uniform(3, 7, 10), 8.8 + rng.normal(0, 0.05, 10)]
        return U, I, ["tension contrôlée"] * 10 + ["courant contrôlé"] * 10

    right, wrong = mode_accuracy(make)
    assert right >= 0.99 and wrong <= 0.005


def test_constant_current_rising_voltage_is_current_controlled():
    df = mode_series(np.linspace(200, 340, 12), np.full(12, 10.8))
    assert plateaux.estimate_mode(df)["phases"] == "courant contrôlé (#1–#12)"


# --- synthèse de fin de série ------------------------------------------------------------
def _rows(u_values):
    rows = []
    for k, u in enumerate(u_values):
        t, U, I = square(u=u, seed=k, noise=0.005)
        row, _ = plateaux.analyse_arrays(t, U, I)
        rows.append({"index": k + 1, "t_s": 30.0 * k, **row})
    return rows


def test_summary_start_end_robust_to_one_outlier(tmp_path):
    summary = plateaux.finalize_series(tmp_path, "essai", _rows([200, 224, 240, 300, 344, 344, 200]))
    assert summary["U_pos_debut_fin"] == "224 -> 344"
    assert summary["I_pos_debut_fin"] == "5.0 -> 5.0"


def test_no_unused_cv_columns(tmp_path):
    summary = plateaux.finalize_series(tmp_path, "essai", _rows([300, 310, 320]))
    header = (tmp_path / "essai_plateaux.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert "cv" not in header and not [k for k in summary if k.startswith("cv")]


# --- non-régression sur une vraie série (dossier voisin du projet) ------------------------
DATA = next((p for p in Path(__file__).resolve().parents if (p / "PEO_N_43").is_dir()), None)


def run_series(tmp_path, exp):
    """Analyse un dossier PEO réel comme le ferait le script ; -> (synthèse, df)."""
    folder = DATA / exp
    meta = json.loads((folder / f"{exp}_meta.json").read_text())
    t0, rows = meta["captures"][0]["timestamp"], []
    for cap in meta["captures"]:
        path = folder / f"{exp}_{cap['index']:04d}.csv"
        if path.exists():
            d = pd.read_csv(path)
            row, _ = plateaux.analyse_arrays(*(d.iloc[:, k].to_numpy(float) for k in range(3)))
            rows.append({"index": cap["index"], "t_s": cap["timestamp"] - t0, **row})
    summary = plateaux.finalize_series(tmp_path, exp, rows)
    df = pd.read_csv(tmp_path / f"{exp}_plateaux.csv", encoding="utf-8-sig").set_index("index")
    return summary, df


@pytest.mark.skipif(DATA is None, reason="données PEO absentes")
def test_regression_peo_n_43(tmp_path):
    summary, df = run_series(tmp_path, "PEO_N_43")
    # #24 (248 V) et #31 (200 V) : chutes de U isolées, I inchangé
    assert summary["n_captures"] == 28 and summary["n_ok"] == 26
    assert df.index[df["flag"] == "U_saut"].tolist() == [24, 31]
    assert df.loc[2, "U_med_pos"] == 200 and df.loc[13, "U_med_pos"] == 280
    assert df["I_med_pos"].between(10.7, 11.1).all()
    assert summary["freq_Hz"] == pytest.approx(150, rel=0.01)
    assert summary["U_pos_debut_fin"] == "224 -> 344"
    assert summary["ruptures_U"] == ""
    # I à 10,8 A tout du long : jamais « tension contrôlée » (la fin, où U et I sont
    # tous deux constants, peut rester « indéterminé »)
    assert summary["mode_majoritaire"] == "courant contrôlé"
    assert "tension contrôlée" not in set(df["mode"])


@pytest.mark.skipif(DATA is None or not (DATA / "PEO_N_41").is_dir(), reason="données PEO absentes")
def test_regression_peo_n_41_regime_change(tmp_path):
    # rampe de tension (I erratique) puis limite de courant atteinte à #14 (I = 8,8 A)
    _, df = run_series(tmp_path, "PEO_N_41")
    assert df.index[df["flag"] == "U_saut"].tolist() == [22]  # 208 V au lieu de ~304 V
    assert set(df.loc[3:13, "mode"]) == {"tension contrôlée"}
    assert set(df.loc[14:25, "mode"].drop(22)) == {"courant contrôlé"}


@pytest.mark.skipif(DATA is None or not (DATA / "PEO_N_22").is_dir(), reason="données PEO absentes")
def test_regression_peo_n_22_voltage_collapse_is_a_rupture(tmp_path):
    summary, df = run_series(tmp_path, "PEO_N_22")
    assert "U_saut" not in set(df["flag"])  # la suite reste cohérente : rien d'exclu
    assert summary["ruptures_U"] == "U 328 -> 40 V (#4 -> #6)"


# --- accumulation en direct pendant une série ----------------------------------------------
def test_live_analysis_accumulates_and_finishes(tmp_path):
    live = plateaux.LiveAnalysis(tmp_path, "essai", "C2", "C3")
    for k in range(4):
        t, U, I = square(u=U_ON + 10 * k, seed=k)
        rec = live.add(k + 1, 1000.0 + 30 * k, {"C2": _wf("C2", t, U, "V"), "C3": _wf("C3", t, I, "A")})
        assert rec["row"]["t_s"] == pytest.approx(30.0 * k)  # relatif à la 1re capture
        assert rec["row"]["index"] == k + 1
        assert (tmp_path / f"essai_{k + 1:04d}_plateaux.png").exists()
    summary = live.finish()
    assert summary["n_captures"] == 4
    assert (tmp_path / "essai_plateaux.csv").exists()


def test_live_analysis_no_signal_keeps_row_without_png(tmp_path):
    live = plateaux.LiveAnalysis(tmp_path, "essai", "C2", "C3")
    t, U, _ = square()
    rec = live.add(1, 0.0, {"C2": _wf("C2", t, U, "V"), "C3": _wf("C3", t, 0 * t, "A")})
    assert rec["row"]["flag"] == "no_signal" and rec["traces"] is None
    assert not (tmp_path / "essai_0001_plateaux.png").exists()
    assert live.rows == [rec["row"]]
