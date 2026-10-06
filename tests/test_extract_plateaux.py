"""Tests du lanceur extract_plateaux.py (CLI, lecture des dossiers PEO_N_*).
L'algorithme est testé dans tests/test_plateaux.py, le re-traitement
(empreintes, traçabilité) dans tests/test_experiment.py.
Les tests ne touchent jamais aux vraies données : copies dans tmp_path.
"""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools import extract_plateaux as ep

# Données réelles, hors dépôt : ``samples/PEO_N_43``, en remontant depuis les tests
# (lecture seule : le re-traitement écrit dans le meta, on travaille sur une copie).
DATA_ROOT = next((p / "samples" for p in Path(__file__).resolve().parents
                  if (p / "samples" / "PEO_N_43").is_dir()), Path("/absent"))


def write_series(root, exp="PEO_N_99", n=3):
    """Mini-série synthétique (meta v1) : créneaux 150 Hz, U = 272 V, I = 8 A."""
    folder = root / exp
    folder.mkdir()
    caps = ",".join(f'{{"index": {k}, "timestamp": {30.0 * k}}}' for k in range(1, n + 1))
    (folder / f"{exp}_meta.json").write_text(f'{{"experiment_id": "{exp}", "captures": [{caps}]}}')
    t = -0.014 + 14e-6 * np.arange(2001)
    on = ((t + 0.0133) % (1 / 150)) < 2.07e-3
    for k in range(1, n + 1):
        pd.DataFrame({"time_s": t, "sonde HT_V": np.where(on, 272.0, 0.0),
                      "I_A": np.where(on, 8.0, 0.0)}).to_csv(folder / f"{exp}_{k:04d}.csv", index=False)
    return folder


def digests(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as e:
        ep.main(["--help"])
    assert e.value.code == 0
    assert "dossier" in capsys.readouterr().out


def test_cli_requires_data_folder():
    with pytest.raises(SystemExit) as e:
        ep.main([])
    assert e.value.code == 2


def test_cli_missing_root_exits_with_error(tmp_path, capsys):
    assert ep.main([str(tmp_path / "absent")]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_cli_root_without_experiments_warns(tmp_path, capsys):
    assert ep.main([str(tmp_path)]) == 1
    assert "WARNING" in capsys.readouterr().out


def test_cli_logs_each_folder_and_writes_outputs(tmp_path, capsys):
    write_series(tmp_path)
    assert ep.main([str(tmp_path)]) == 0
    assert "[OK] PEO_N_99 : 3 captures, 3 exploitables" in capsys.readouterr().out
    out = tmp_path / "resultats"
    df = pd.read_csv(out / "PEO_N_99_plateaux.csv", encoding="utf-8-sig")
    assert df["U_med_pos"].tolist() == [272] * 3
    assert (out / "PEO_N_99_UI_vs_t.png").exists() and (out / "synthese_modes.csv").exists()
    # contrôle : un seul PNG par essai, toutes les captures en liste
    assert [p.name for p in out.glob("PEO_N_99_controle*.png")] == ["PEO_N_99_controle.png"]


def test_raw_folder_only_gets_its_meta_updated(tmp_path):
    folder = write_series(tmp_path)
    before = digests(folder)
    assert ep.main([str(tmp_path)]) == 0
    after = digests(folder)
    assert after.keys() == before.keys()  # aucun fichier ajouté dans le dossier de données
    assert [n for n in before if before[n] != after[n]] == ["PEO_N_99_meta.json"]
    analyse = json.loads((folder / "PEO_N_99_meta.json").read_text(encoding="utf-8"))["analyses"][-1]
    assert analyse["origine"] == "re-traitement"
    assert Path(analyse["sorties"]) == tmp_path / "resultats"


def test_removed_capture_is_skipped_and_reported(tmp_path, capsys):
    folder = write_series(tmp_path)
    (folder / "PEO_N_99_0002.csv").unlink()  # capture retirée (bruitée)
    assert ep.main([str(tmp_path)]) == 0
    assert "captures retirées : #2" in capsys.readouterr().out
    out = tmp_path / "resultats"
    df = pd.read_csv(out / "PEO_N_99_plateaux.csv", encoding="utf-8-sig")
    assert df["index"].tolist() == [1, 3] and df["t_s"].tolist() == [0, 60]
    synth = pd.read_csv(out / "synthese_modes.csv", encoding="utf-8-sig", dtype={"captures_absentes": str})
    assert synth.loc[0, "captures_absentes"] == "2"


def test_modified_raw_file_is_an_error_and_other_series_continue(tmp_path, capsys):
    bad = write_series(tmp_path, "PEO_N_98")
    write_series(tmp_path, "PEO_N_99")
    assert ep.main([str(tmp_path)]) == 0  # 1er passage : empreintes a posteriori
    with open(bad / "PEO_N_98_0001.csv", "a") as fh:
        fh.write("0,0,0\n")  # donnée brute altérée
    capsys.readouterr()
    assert ep.main([str(tmp_path)]) == 1
    log = capsys.readouterr().out
    assert "ERROR PEO_N_98" in log and "PEO_N_98_0001.csv" in log
    assert "[OK] PEO_N_99" in log


@pytest.mark.skipif(not (DATA_ROOT / "PEO_N_43").is_dir(), reason="données absentes")
def test_real_series_n43_on_a_copy(tmp_path):
    folder = shutil.copytree(DATA_ROOT / "PEO_N_43", tmp_path / "PEO_N_43")
    summary = ep.process(folder, tmp_path / "resultats")
    assert summary["n_captures"] == 28 and summary["n_ok"] == 26  # #24, #31 : U_saut
    assert summary["mode_majoritaire"] == "courant contrôlé"
    assert summary["integrite"]["captures_absentes"] == [1, 22, 23]
