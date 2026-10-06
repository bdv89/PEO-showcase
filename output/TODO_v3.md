# TODO_v3 — Plateaux : source unique, mode de pilotage, anomalies, contrôle visuel

> Date : 2026-10-05 → 2026-10-06 — session « peo-plateau-extraction ».
> Rédigé à l'origine comme `TODO_v2.md`, puis écrasé par le TODO_v2 de la session GUI
> (fiche d'expérience), développée en parallèle : reconstitué ici sous un nouveau numéro.
> Phase 0 : revue de conformité aux standards, puis choix validés en session.

## Contexte
- La logique d'extraction existait en **2 copies** : `../extract_plateaux.py` (analyse a posteriori)
  et `scope/plateaux.py` (direct, GUI) → risque de divergence.
- `estimate_mode` choisissait parmi 3 fenêtres celle qui minimise `activité U + activité I` : en
  **tension contrôlée**, I est erratique partout, ce qui retenait la fenêtre où I est « calme par
  chance » → « indéterminé » à tort (PEO_N_41 #2, #4 ; 28 % des captures synthétiques).
- Revue du prisme 1 : colonnes `cvU`/`cvI` mortes, docstring périmée, constantes magiques, synthèse
  « début → fin » sensible à une capture aberrante, script sans `--help` ni journal.

## Solution
- `scope/plateaux.py` = **référence unique** ; `../extract_plateaux.py` = lanceur mince.
- Mode de pilotage : la grandeur pilotée est la **moins rugueuse** (écart à une droite) ; à
  rugosité égale, celle qui **ne dérive pas** ; 1 point aberrant écarté par fenêtre (sauf la capture
  classée).
- Anomalies entre captures voisines (`flag_jumps`) : `U_saut`, `ruptures_U`.
- PNG de contrôle : 1 par essai, une ligne par capture, numéro en grand, anomalies sous voile rouge.

## Tâches (TDD : RED → GREEN → REFACTOR)
- [x] Tests du mode (rampe U + I erratique ; changement de régime) → RED ; correction → GREEN
- [x] Tests : pas de `cv*` ; synthèse début/fin robuste ; pointe de coupure ; `U_absent` ; I haché
- [x] Nettoyage : constantes nommées (`U_ABSENT_V`, `NEG_MIN_FRACTION`, `U_REF_PENALTY`, `MODE_*`…)
- [x] Non-régression sur données réelles (PEO_N_22/41/43) au lieu de la comparaison au script
- [x] `../extract_plateaux.py` : lanceur + `--help`, journal `[OK]/WARNING/ERROR`, code de sortie
- [x] `save_control_png` (1 PNG/essai, toutes captures, voile rouge, `capture_tag` en grand)
- [x] `flag_jumps` : `U_saut` (exclu) + `ruptures_U` (signalée)
- [x] `../extract_plateaux.py` → `experiment.reprocess(out_dir=resultats/, per_capture_png=False)`
- [x] Docs : README, usage.md, architecture.md

## Bilan
- Mode de pilotage, sur 16 000 captures synthétiques :
  - justes : **71,6 % → 99,5 %** ;
  - indéterminé : 28,2 % → 0,4 % ;
  - inversées : 0,18 % → 0,10 %.
  Variantes rejetées : min(U, I) seul (54 % des séries en échec) ; Theil-Sen + MAD (ignore un I
  erratique).
- Tests du mode en **précision par capture** (≥ 99 % justes, ≤ 0,5 % inversées sur 200 tirages).
- Données réelles :
  - PEO_N_41 : tension #2–#13 → courant #14–#25 ; #22 `U_saut`.
  - PEO_N_43 : courant contrôlé ; #24 et #31 `U_saut`.
  - PEO_N_22 : rupture « U 328 -> 40 V (#4 -> #6) ».
  - Valeurs de plateau identiques à la version d'origine.
- Défaut trouvé par un test : avec 2 voisines dont une aberrante, la cohérence « résidu de droite »
  était toujours vraie → critère remplacé par « pas de saut entre voisines ».
- Traçabilité (choix utilisateur « meta.json seul ») : sur 255 fichiers des dossiers de données,
  seuls les 3 meta.json changent (champs d'origine conservés, empreintes a posteriori, captures
  retirées #1, #22, #23 pour N_43). Les meta v1 d'origine ont été sauvegardés avant le passage. Les
  tests du script travaillent sur des copies.
- Tests : `tests/` 287 OK, 1 skip ; `../test_extract_plateaux.py` 8 OK.

## Lanceur (2026-10-06, panne au double-clic du .bat)
- Cause : le Python embarqué (fichier `._pth`) n'ajoute pas le dossier du script à
  `sys.path` → `ModuleNotFoundError: scope`. Mon premier contrôle du dossier Windows
  l'avait masqué (`sys.path.insert(0, '.')` ajouté à la main) : remplacé par un vrai test.
- Correctif : `launcher.py` ajoute son dossier à `sys.path`. Test `-P` (reproduit le cas)
  + test de livraison avec le Python embarqué (`--check`), ignoré si le dossier est absent.
- Journal `logs/oscilloscope.log` : horodaté, rotation 3 x 1 Mo, exceptions non gérées
  (thread principal/slots Qt et threads), sortie standard sous pythonw. `--check` n'installe
  jamais rien (un premier test en `-I` avait déclenché le bootstrap pip : corrigé).
- Dossier Windows : `launcher.py` recopié (contrôle `--check` OK avec Python 3.12.8).
- Suites : `tests/` 294 OK, 1 skip ; script 8 OK.

## Critique Prisme 1
| Question | Réponse |
|----------|---------|
| Solution la plus simple ? | Oui : une copie supprimée au lieu de deux fichiers à synchroniser |
| Abstractions prématurées ? | Non : petites fonctions issues du découpage (`roughness_drift`, `window_stats`, `mode_score`, `start_end`, `flag_jumps`, `draw_capture`, `capture_tag`), toutes utilisées et testées ; aucune classe |
| Fonctionnalités spéculatives ? | Non : chaque ajout répond à une demande ou à un défaut constaté |

## Contraintes Qualité
- **Test** : unitaires sur signaux synthétiques + non-régression données réelles.
- **Knowledge** : pas de nouvelle dépendance.
- Couplage : `../extract_plateaux.py` dépend du dossier `Oscilloscope/` voisin.

## Historique des versions
| Version | Date | Changements |
|---------|------|-------------|
| v2 (perdu) | 2026-10-05 | Rédaction initiale, écrasée par le TODO_v2 de la session GUI |
| v3 | 2026-10-06 | Reconstitution + anomalies, PNG de contrôle, intégration `reprocess` |
