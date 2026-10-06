# TODO_v1 — GUI en onglets + extraction des plateaux en direct

> Date : 2026-10-05 — plan validé (Phase 0 : voir questions/réponses de session)

## Décisions
- Onglet « Mesure » : paramètres + live (réglage). Onglet « Analyse » : dernière capture
  de série (plateaux surlignés) | U/I/f vs t rempli à chaque capture.
- Voies U/I choisies dans la GUI ; unités converties en V/A (mA→A, kV→V…) avant analyse.
- Mode de pilotage : pas en live ; passe complète en fin de série (CSV + `_UI_vs_t.png`).
- pandas ajouté aux dépendances ; logique reprise de `../extract_plateaux.py` (inchangé).
- 1 PNG matplotlib de sélection de plateaux par capture, dans le dossier série.
- Tout l'onglet paramètres mémorisé (`gui_settings.json`), rechargé sans envoi SCPI.

## Tâches (TDD : RED → GREEN → REFACTOR)
- [x] `scope/plateaux.py` + `tests/test_plateaux.py` (créneau synthétique, no_signal,
      to_si, PNG, finalize_series, non-régression vs extract_plateaux sur PEO_N_22)
- [x] `SeriesConfig.u_channel/i_channel` (rétro-compatible) + meta
- [x] `load/save_gui_settings` + tests
- [x] GUI : QTabWidget, combos U/I, onglet Analyse, signal `plateau_ready`, finalize en fin de série
- [x] Dépendance pandas (requirements, flake/shell, pyproject)
- [x] Docs : README, usage.md, architecture.md

## Bilan
- 216 tests OK, 1 skip ; 1 échec **préexistant** (`test_run_series_now_captures_expected_count` :
  séparateur `\` vs `/` sous Windows, indépendant de ce travail).
- Smoke test GUI offscreen (PyQt5) : onglets, restauration des réglages sans SCPI, tracés Analyse.
- Arborescence remise à plat (scope/, tests/, docs/, standards/… étaient imbriqués) :
  `pytest` marche sans PYTHONPATH.
- Dossier Windows autonome reconstruit (`Oscilloscope/`, Python 3.12.8 + pandas 3.0.6),
  cache `_wheelhouse` vidé (anciennes versions mélangées). Vérifié avec son propre Python :
  synthèse PEO_N_22 identique au script (15/25, courant contrôlé), fenêtre OK.
  Ancienne copie conservée dans `Oscilloscope_ancien/` (supprimée le 2026-10-06, avec
  `Oscilloscope_1/` : programme seul, aucune donnée).
- Reste : test sur matériel.
