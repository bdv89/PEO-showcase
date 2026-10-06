"""Tests de la fiche d'expérience et de la traçabilité (``scope.experiment``), sans matériel.

Séries synthétiques écrites sur disque au format réel (CSV combiné
``time_s, <nom>_<unité>, ...`` + ``{id}_meta.json``), horloge murale injectée.
"""

import json
import os
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from scope import experiment as xp

WHEN = "2026-10-06T10:00:00+02:00"


# --- fiche ---------------------------------------------------------------------------
def test_empty_fiche_has_every_field_empty():
    fiche = xp.empty_fiche()
    for key, _label, _req in xp.FICHE_FIELDS:
        assert xp.get_field(fiche, key) in ("", [])


def test_set_and_get_dotted_field():
    fiche = xp.empty_fiche()
    xp.set_field(fiche, "echantillon.id", "AL-042")
    assert fiche["echantillon"]["id"] == "AL-042"
    assert xp.get_field(fiche, "echantillon.id") == "AL-042"


def test_missing_fields_ignores_optional_tags_and_notes():
    fiche = xp.empty_fiche()
    for key, _label, required in xp.FICHE_FIELDS:
        if required:
            xp.set_field(fiche, key, "x")
    assert xp.missing_fields(fiche) == []
    xp.set_field(fiche, "bain.pH", "  ")  # blanc = vide
    assert xp.missing_fields(fiche) == ["bain.pH"]


def test_prefill_keeps_everything_but_sample_id_and_notes():
    previous = xp.empty_fiche()
    xp.set_field(previous, "operateur", "BDV")
    xp.set_field(previous, "echantillon.id", "AL-042")
    xp.set_field(previous, "notes", "étincelles")
    xp.set_field(previous, "tags", ["essai", "bipolaire"])
    fiche = xp.prefill(previous)
    assert fiche["operateur"] == "BDV" and fiche["tags"] == ["essai", "bipolaire"]
    assert fiche["echantillon"]["id"] == "" and fiche["notes"] == ""
    assert previous["echantillon"]["id"] == "AL-042"  # l'original n'est pas modifié


def test_parse_tags():
    assert xp.parse_tags(" bipolaire, Al 6061 ,,bipolaire ") == ["bipolaire", "Al 6061"]


# --- identifiant ----------------------------------------------------------------------
def test_next_id_starts_at_01(tmp_path):
    assert xp.next_id(tmp_path, "PEO", date(2026, 10, 6)) == "PEO_2026-10-06_01"


def test_next_id_follows_highest_existing_of_the_day(tmp_path):
    for name in ("PEO_2026-10-06_01", "PEO_2026-10-06_03", "PEO_2026-10-05_07", "XYZ_2026-10-06_09"):
        (tmp_path / name).mkdir()
    assert xp.next_id(tmp_path, "PEO", date(2026, 10, 6)) == "PEO_2026-10-06_04"


def test_next_id_missing_outdir(tmp_path):
    assert xp.next_id(tmp_path / "absent", "PEO", date(2026, 10, 6)) == "PEO_2026-10-06_01"


@pytest.mark.parametrize("prefix", ["", "PEO/1", "a b", "..", "PEO_"])
def test_invalid_prefix_rejected(prefix):
    with pytest.raises(ValueError):
        xp.validate_prefix(prefix)


def test_valid_prefix():
    assert xp.validate_prefix(" PEO-Ti ") == "PEO-Ti"


def test_now_iso_is_timezone_aware():
    stamp = xp.now_iso(lambda: datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc))
    assert stamp == "2026-10-06T08:00:00+00:00"


# --- meta.json v2 ------------------------------------------------------------------------
def write_series(root, exp="PEO_N_99", n=3, u=272.0, i_amp=8.0, v2=False, header=("sonde HT_V", "I_A"), scale_i=1.0):
    """Mini-série au format réel : créneaux 150 Hz ; meta v1 (anciennes séries) ou v2."""
    folder = root / exp
    folder.mkdir()
    t = -0.014 + 14e-6 * np.arange(2001)
    on = ((t + 0.0133) % (1 / 150)) < 2.07e-3
    captures = []
    for k in range(1, n + 1):
        pd.DataFrame({"time_s": t, header[0]: np.where(on, u + k, 0.0),
                      header[1]: np.where(on, i_amp * scale_i, 0.0)}).to_csv(folder / f"{exp}_{k:04d}.csv", index=False)
        np.save(folder / f"{exp}_{k:04d}_C2.npy", np.zeros(3))
        captures.append({"index": k, "timestamp": 1000.0 + 30 * k,
                         "files": [f"ailleurs\\{exp}\\{exp}_{k:04d}.csv"], "errors": []})
    meta = {"experiment_id": exp, "channels": ["C2", "C3"], "rate": 2, "per_seconds": 60,
            "points": 2000, "captures": captures}
    if v2:
        meta.update({"schema": 2, "u_channel": "C2", "i_channel": "C3",
                     "acquisition": {"voies": {"C2": {"label": header[0].rsplit("_", 1)[0], "unit": header[0].rsplit("_", 1)[1], "factor": 1.0},
                                               "C3": {"label": header[1].rsplit("_", 1)[0], "unit": header[1].rsplit("_", 1)[1], "factor": 1.0}}}})
    (folder / f"{exp}_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def test_load_meta_migrates_v1_with_defaults(tmp_path):
    folder = write_series(tmp_path)
    meta = xp.load_meta(folder)
    assert meta["schema"] == 2
    assert meta["fiche"] == xp.empty_fiche()
    for key in ("resultats", "pieces_jointes", "analyses", "historique"):
        assert meta[key] == []
    assert meta["empreintes"] == {}
    assert meta["captures"][0]["index"] == 1  # clés v1 conservées telles quelles


def test_load_meta_fills_fiche_fields_added_later(tmp_path):
    folder = write_series(tmp_path)
    meta = json.loads((folder / "PEO_N_99_meta.json").read_text())
    meta["fiche"] = {"operateur": "BDV", "echantillon": {"id": "AL-1"}}
    (folder / "PEO_N_99_meta.json").write_text(json.dumps(meta))
    fiche = xp.load_meta(folder)["fiche"]
    assert fiche["operateur"] == "BDV" and fiche["echantillon"]["id"] == "AL-1"
    assert fiche["echantillon"]["materiau"] == "" and fiche["bain"]["pH"] == ""


def test_load_meta_missing_raises(tmp_path):
    (tmp_path / "vide").mkdir()
    with pytest.raises(FileNotFoundError):
        xp.load_meta(tmp_path / "vide")


def test_update_meta_is_atomic_and_keeps_unknown_keys(tmp_path):
    folder = write_series(tmp_path)
    xp.update_meta(folder, lambda m: m.update(extra=1))
    xp.update_meta(folder, lambda m: m["resultats"].append({"nom": "e"}))
    raw = json.loads((folder / "PEO_N_99_meta.json").read_text(encoding="utf-8"))
    assert raw["extra"] == 1 and raw["resultats"] == [{"nom": "e"}]
    assert not list(folder.glob("*.tmp"))


def test_create_meta_refuses_existing_file(tmp_path):
    folder = write_series(tmp_path)
    with pytest.raises(FileExistsError):
        xp.create_meta(folder, {"experiment_id": "PEO_N_99"})


# --- historique ------------------------------------------------------------------------
def test_apply_fiche_logs_only_real_changes():
    meta = xp.migrate({"experiment_id": "x"})
    fiche = xp.empty_fiche()
    xp.set_field(fiche, "operateur", "BDV")
    xp.set_field(fiche, "tags", ["a"])
    changed = xp.apply_fiche(meta, fiche, user="bdv", when=WHEN)
    assert changed == ["operateur", "tags"]
    assert meta["historique"] == [
        {"date": WHEN, "utilisateur": "bdv", "champ": "operateur", "avant": "", "apres": "BDV"},
        {"date": WHEN, "utilisateur": "bdv", "champ": "tags", "avant": [], "apres": ["a"]},
    ]
    assert xp.apply_fiche(meta, fiche, user="bdv", when=WHEN) == []  # rien de neuf
    assert len(meta["historique"]) == 2


def test_set_results_logged():
    meta = xp.migrate({"experiment_id": "x"})
    results = [{"nom": "épaisseur", "valeur": "12", "unite": "µm"}]
    assert xp.set_results(meta, results, user="bdv", when=WHEN) is True
    assert meta["resultats"] == results
    assert meta["historique"][-1]["champ"] == "resultats"
    assert xp.set_results(meta, results, user="bdv", when=WHEN) is False


# --- empreintes ---------------------------------------------------------------------------
def test_raw_files_are_capture_files_only(tmp_path):
    folder = write_series(tmp_path, n=2)
    (folder / "PEO_N_99_plateaux.csv").write_text("analyse")
    (folder / "PEO_N_99_0001_plateaux.png").write_bytes(b"png")
    assert xp.raw_files(folder, "PEO_N_99") == [
        "PEO_N_99_0001.csv", "PEO_N_99_0001_C2.npy", "PEO_N_99_0002.csv", "PEO_N_99_0002_C2.npy"]


def test_ensure_checksums_a_posteriori_then_verify(tmp_path):
    folder = write_series(tmp_path, n=2)
    meta = xp.load_meta(folder)
    assert xp.ensure_checksums(meta, folder, user="bdv", when=WHEN) is True
    assert meta["empreintes_info"] == {"date": WHEN, "a_posteriori": True}
    assert len(meta["empreintes"]["PEO_N_99_0001.csv"]) == 64
    assert meta["historique"][-1]["champ"] == "empreintes"
    assert xp.ensure_checksums(meta, folder, user="bdv", when=WHEN) is False  # déjà là
    report = xp.verify_checksums(meta, folder)
    assert report["modifie"] == report["manquant"] == report["nouveau"] == []
    assert len(report["ok"]) == 4


def test_verify_detects_modified_missing_and_new(tmp_path):
    folder = write_series(tmp_path, n=3)
    meta = xp.load_meta(folder)
    xp.ensure_checksums(meta, folder, user="bdv", when=WHEN)
    (folder / "PEO_N_99_0001.csv").write_text("altéré")
    (folder / "PEO_N_99_0002.csv").unlink()
    np.save(folder / "PEO_N_99_0009_C2.npy", np.zeros(1))
    report = xp.verify_checksums(meta, folder)
    assert report["modifie"] == ["PEO_N_99_0001.csv"]
    assert report["manquant"] == ["PEO_N_99_0002.csv"]
    assert report["nouveau"] == ["PEO_N_99_0009_C2.npy"]


# --- pièces jointes -------------------------------------------------------------------------
def test_add_attachment_copies_without_overwrite(tmp_path):
    folder = write_series(tmp_path)
    src = tmp_path / "photo.jpg"
    src.write_bytes(b"jpeg")
    meta = xp.load_meta(folder)
    first = xp.add_attachment(meta, folder, src, user="bdv", when=WHEN)
    second = xp.add_attachment(meta, folder, src, user="bdv", when=WHEN)
    assert first == "photo.jpg" and second == "photo (2).jpg"
    assert (folder / "pieces_jointes" / "photo (2).jpg").read_bytes() == b"jpeg"
    assert meta["pieces_jointes"][0]["sha256"] == xp.sha256_file(src)
    assert meta["historique"][-1]["champ"] == "pieces_jointes"


# --- version de l'algorithme ---------------------------------------------------------------
def test_algo_version_is_hash_of_plateaux_source():
    version = xp.algo_version()
    assert len(version) == 12 and int(version, 16) >= 0


def test_algo_parameters_are_numeric_constants_only():
    params = xp.algo_parameters()
    assert params["MIN_SNR"] == 5.0  # seuils relatifs au bruit de mesure (plus de seuil en A ou V)
    assert not {"MIN_AMPLITUDE_A", "MIN_AMPLITUDE_V", "U_ABSENT_V"} & params.keys()
    assert "COLUMNS" not in params and "_PREFIXES" not in params
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in params.values())
    json.dumps(params)  # sérialisable (pas de float numpy)


# --- lecture des CSV + re-traitement ------------------------------------------------------
def test_read_capture_converts_units_from_header(tmp_path):
    folder = write_series(tmp_path, header=("sonde HT_kV", "I_mA"), u=0.272, i_amp=8.0, scale_i=1e3)
    t, U, I = xp.read_capture(folder / "PEO_N_99_0001.csv")
    assert U.max() == pytest.approx(1272.0)  # (0.272 + 1) kV
    assert I.max() == pytest.approx(8.0)


def test_read_capture_selects_named_columns(tmp_path):
    folder = tmp_path
    pd.DataFrame({"time_s": [0, 1e-5], "I_A": [8.0, 8.0], "sonde HT_V": [300.0, 300.0]}).to_csv(
        folder / "c.csv", index=False)
    _, U, I = xp.read_capture(folder / "c.csv", columns=("sonde HT_V", "I_A"))
    assert U[0] == 300.0 and I[0] == 8.0


def test_read_capture_rejects_wrong_quantity(tmp_path):
    pd.DataFrame({"time_s": [0, 1], "a_A": [1, 1], "b_A": [1, 1]}).to_csv(tmp_path / "c.csv", index=False)
    with pytest.raises(ValueError, match="tension"):
        xp.read_capture(tmp_path / "c.csv")


def test_reprocess_v1_series_writes_outputs_and_records_analysis(tmp_path):
    folder = write_series(tmp_path, n=4)
    (folder / "PEO_N_99_0009_plateaux.png").write_bytes(b"obsolete")  # ancienne analyse
    before = {p.name: p.read_bytes() for p in folder.glob("PEO_N_99_000?.csv")}
    summary = xp.reprocess(folder, user="bdv", when=WHEN)
    assert summary["n_captures"] == summary["n_ok"] == 4
    for name in ("PEO_N_99_plateaux.csv", "PEO_N_99_UI_vs_t.png", "PEO_N_99_controle.png",
                 "PEO_N_99_0001_plateaux.png"):
        assert (folder / name).exists(), name
    assert not (folder / "PEO_N_99_0009_plateaux.png").exists()
    assert {p.name: p.read_bytes() for p in folder.glob("PEO_N_99_000?.csv")} == before  # brut intact
    meta = xp.load_meta(folder)
    entry = meta["analyses"][-1]
    assert entry["origine"] == "re-traitement" and entry["date"] == WHEN
    assert entry["algo_version"] == xp.algo_version()
    assert entry["integrite"]["modifie"] == [] and entry["force"] is False
    assert entry["synthese"]["n_ok"] == 4
    assert meta["empreintes_info"]["a_posteriori"] is True  # 1re ouverture d'une série v1
    json.dumps(meta, allow_nan=False)  # JSON strict (pas de NaN)


def test_reprocess_uses_meta_channels_for_v2(tmp_path):
    folder = write_series(tmp_path, v2=True, header=("sonde HT_V", "I_mA"), scale_i=1e3)
    summary = xp.reprocess(folder, user="bdv", when=WHEN)
    assert summary["n_ok"] == 3
    df = pd.read_csv(folder / "PEO_N_99_plateaux.csv", encoding="utf-8-sig")
    assert df["I_med_pos"].iloc[0] == pytest.approx(8.0)


def test_reprocess_refuses_altered_data_unless_forced(tmp_path):
    folder = write_series(tmp_path)
    meta = xp.load_meta(folder)
    xp.ensure_checksums(meta, folder, user="bdv", when=WHEN)
    xp.update_meta(folder, lambda m: m.update(empreintes=meta["empreintes"], empreintes_info=meta["empreintes_info"]))
    path = folder / "PEO_N_99_0002_C2.npy"
    np.save(path, np.ones(3))
    with pytest.raises(xp.IntegrityError, match="PEO_N_99_0002_C2.npy"):
        xp.reprocess(folder, user="bdv", when=WHEN)
    xp.reprocess(folder, user="bdv", when=WHEN, force=True)
    entry = xp.load_meta(folder)["analyses"][-1]
    assert entry["force"] is True and entry["integrite"]["modifie"] == ["PEO_N_99_0002_C2.npy"]


def test_reprocess_traces_captures_removed_before_checksums(tmp_path):
    folder = write_series(tmp_path, n=3)
    (folder / "PEO_N_99_0002.csv").unlink()  # retirée AVANT la 1re ouverture (série v1)
    summary = xp.reprocess(folder, user="bdv", when=WHEN)
    assert summary["n_captures"] == 2
    integrite = xp.load_meta(folder)["analyses"][-1]["integrite"]
    assert integrite["manquant"] == []              # pas dans les empreintes (prises après)
    assert integrite["captures_absentes"] == [2]    # mais listée au meta : retrait tracé


def test_reprocess_skips_removed_capture(tmp_path):
    folder = write_series(tmp_path, n=3)
    xp.reprocess(folder, user="bdv", when=WHEN)
    (folder / "PEO_N_99_0002.csv").unlink()  # capture retirée volontairement (bruitée)
    summary = xp.reprocess(folder, user="bdv", when=WHEN)
    assert summary["n_captures"] == 2
    assert xp.load_meta(folder)["analyses"][-1]["integrite"]["manquant"] == ["PEO_N_99_0002.csv"]


def test_record_analysis_makes_summary_json_safe():
    meta = xp.migrate({"experiment_id": "x"})
    xp.record_analysis(meta, {"n_ok": np.int64(3), "freq_Hz": np.float64("nan"), "mode": "c"},
                       origine="série", user="bdv", when=WHEN)
    entry = meta["analyses"][0]
    assert entry["synthese"] == {"n_ok": 3, "freq_Hz": None, "mode": "c"}
    json.dumps(meta, allow_nan=False)


# --- tags ------------------------------------------------------------------------------------
def test_collect_tags_from_all_series(tmp_path):
    for k, tags in enumerate((["bipolaire", "Al"], ["Al", "Ti"])):
        folder = write_series(tmp_path, exp=f"S{k}")
        xp.update_meta(folder, lambda m, t=tags: m["fiche"].update(tags=t))
    (tmp_path / "pas_une_serie").mkdir()
    assert xp.collect_tags(tmp_path) == ["Al", "Ti", "bipolaire"]


def test_find_meta_is_any_single_meta_json(tmp_path):
    folder = write_series(tmp_path, exp="renomme")
    os.rename(folder / "renomme_meta.json", folder / "PEO_N_1_meta.json")  # dossier renommé à la main
    assert xp.meta_path(folder).name == "PEO_N_1_meta.json"


# --- sorties hors du dossier de série (script extract_plateaux.py) -----------------------------
def test_reprocess_out_dir_keeps_series_folder_clean_except_meta(tmp_path):
    folder = write_series(tmp_path, n=3)
    before = sorted(p.name for p in folder.iterdir())
    out = tmp_path / "resultats"
    summary = xp.reprocess(folder, user="bdv", when=WHEN, out_dir=out, per_capture_png=False)
    assert sorted(p.name for p in folder.iterdir()) == before  # seul le meta a changé
    assert sorted(p.name for p in out.iterdir()) == [
        "PEO_N_99_UI_vs_t.png", "PEO_N_99_controle.png", "PEO_N_99_plateaux.csv"]
    entry = xp.load_meta(folder)["analyses"][-1]
    assert entry["sorties"] == str(out)
    assert summary["integrite"] == entry["integrite"]


def test_reprocess_returns_summary_with_integrity(tmp_path):
    folder = write_series(tmp_path, n=3)
    (folder / "PEO_N_99_0003.csv").unlink()
    summary = xp.reprocess(folder, user="bdv", when=WHEN)
    assert summary["n_captures"] == 2 and "mode_majoritaire" in summary
    assert summary["integrite"]["captures_absentes"] == [3]
    assert summary["integrite"]["modifie"] == []
