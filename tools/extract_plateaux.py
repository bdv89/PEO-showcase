"""Extraction des plateaux U/I des séries PEO enregistrées (analyse a posteriori).

Lanceur mince : chaque dossier PEO_N_* est re-traité par ``scope/experiment.py``
(``reprocess``), qui s'appuie sur ``scope/plateaux.py``, source unique de
l'algorithme (aussi utilisée en direct par la GUI).

Usage (depuis la racine du dépôt ; les données ne font pas partie du dépôt) :
``python tools/extract_plateaux.py "D:/Mesures/PEO"``

- Intégrité : les fichiers bruts sont vérifiés par empreinte SHA-256 (calculées au
  premier passage pour les anciennes séries) ; un fichier modifié est une erreur.
- Traçabilité : seul le ``meta.json`` du dossier de série est mis à jour (empreintes,
  captures retirées, version de l'algorithme, historique). Les données brutes ne
  sont jamais modifiées.
- Sorties dans ``<dossier_racine>/resultats/`` : par série ``{exp}_plateaux.csv``,
  ``{exp}_UI_vs_t.png`` et ``{exp}_controle.png`` (toutes les captures, une ligne
  chacune), plus ``synthese_modes.csv``.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # racine du dépôt
from scope import experiment  # noqa: E402


def process(folder, out):
    """Re-traite une série (dossier PEO_N_*) ; sorties dans ``out``. Retourne la
    synthèse (dict, avec ``"integrite"``) ; ``experiment.IntegrityError`` si un
    fichier brut a été modifié."""
    return experiment.reprocess(folder, user=experiment.current_user(), when=experiment.now_iso(),
                                out_dir=out, per_capture_png=False)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Extrait U et I des plateaux de chaque capture des séries PEO_N_* "
                    "et écrit les séries U(t), I(t) dans <dossier>/resultats/. "
                    "Seul le meta.json de chaque série est mis à jour (traçabilité).",
        epilog="Exemple : python tools/extract_plateaux.py \"D:/Mesures/PEO\"")
    parser.add_argument("dossier", type=Path, help="dossier contenant les séries PEO_N_*")
    root = parser.parse_args(argv).dossier
    if not root.is_dir():
        print(f"ERROR dossier introuvable : {root}")
        return 1
    folders = sorted(f for f in root.glob("PEO_N_*") if f.is_dir())
    if not folders:
        print(f"WARNING aucun dossier PEO_N_* dans {root}")
        return 1
    out = root / "resultats"
    summaries, status = [], 0
    for folder in folders:
        try:
            s = process(folder, out)
        except experiment.IntegrityError as e:  # jamais de re-traitement forcé en silence
            print(f"ERROR {folder.name} : {e}")
            status = 1
            continue
        absent = s["integrite"].get("captures_absentes", [])
        print(f"[OK] {s['experiment']} : {s['n_captures']} captures, {s['n_ok']} exploitables"
              + (f", {s['mode_majoritaire']}" if s.get("mode_majoritaire") else "")
              + (f" (captures retirées : {', '.join(f'#{i}' for i in absent)})" if absent else ""))
        summary = {k: v for k, v in s.items() if k != "integrite"}
        summaries.append({**summary, "captures_absentes": " ".join(map(str, absent))})
    if summaries:
        pd.DataFrame(summaries).to_csv(out / "synthese_modes.csv", index=False, float_format="%.4g",
                                       encoding="utf-8-sig")
    print(f"Résultats : {out}")
    return status


if __name__ == "__main__":
    sys.exit(main())
