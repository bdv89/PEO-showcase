# TODO_v5 — Plateaux indépendants de l'échelle et des unités

> Date : 2026-10-06 — branche `plateaux-robustes` (worktree `PEOscillo-plateaux`).
> Demande : la série `test_2026-10-06_06` (I enregistré en mA) sort 6/6 `no_signal`.

## Phase 0 — constat
- Seuils absolus : `MIN_AMPLITUDE_A = 1 A`, `MIN_AMPLITUDE_V = 40 V`, `U_ABSENT_V = 20 V`.
  Aux calibres des PEO_N_* (pas de quantification 0,2 A et 8 V) : exactement **5 pas**
  (1 A, 40 V) et 2,5 pas (20 V). Les seuils étaient en fait liés à la résolution du scope.
- `test_2026-10-06_06` : I converti mA -> A vaut ~1e-3 A -> sous 1 A -> `no_signal` partout.
- Niveaux mesurés en pas de quantification : captures sans signal <= 3 pas ; captures avec
  signal >= 14 pas sur I (24 à 79 sur les PEO_N_*) — séparation nette, quelle que soit l'unité.
- Tests réels PEO_N_22/41/43 ignorés en silence (dossiers déplacés dans `samples/`).

## Design (Prisme 1)
- [x] `noise_level(x)` = max(pas de quantification, σ robuste des différences successives).
      Pas = plus petit |Δx| non nul **s'il revient souvent** (>= 10 % des points) : un bruit
      d'1 LSB en a un, un créneau idéal à deux valeurs (fixtures synthétiques) non.
- [x] `no_signal` : écart niveau haut − niveau bas de I <= `MIN_SNR` (5) × bruit (insensible à un offset).
- [x] Découpage : polarité retenue si son niveau > `MIN_SNR` × bruit (remplace 1 A / 40 V).
- [x] `U_absent` : |U plateau +| < `U_ABSENT_SNR` (2,5) × bruit de U (remplace 20 V).
- [x] Libellés / synthèse : courant lisible en mA (`fmt_current`, « 0.00048 » au lieu de « 0.0 »).
- Écarté (YAGNI) : niveaux relatifs à un offset pour les plateaux, unité d'affichage automatique.

| Critique | Réponse |
|----------|---------|
| Plus simple ? | 2 petites fonctions (`noise_level`, `has_signal`), 3 constantes ; le reste inchangé |
| Spéculatif ? | Non : cas réel (mA) + invariance testée |

## Exécution (TDD)
- [x] Non-régression d'abord (commit 0f3b547) : tests réels pointés vers `samples/` (ils
      re-tournent), état du code AVANT modification figé dans `samples/reference/` (hors dépôt : résultats d'essais non publiés)
      (CSV par capture + synthèses), comparé à l'identique.
- [x] RED (16 échecs) : invariance A/mA/µA/kA, sonde ×0,1/×10, bipolaire mis à l'échelle,
      bruit seul -> `no_signal` (4 types × 3 échelles), cellule bipolaire synthétique,
      `U_absent` à petite échelle, libellés mA, série réelle `test_2026-10-06_06`.
- [x] GREEN : suite complète 372 OK, 1 skip (`test_launcher` : dossier Windows autonome absent).
- [x] PNG de contrôle de la série problème vérifié à l'œil (plateaux + sur U = 300 V,
      plateaux − sur U = −20 V, 250 Hz).
- [x] `docs/usage.md` (seuils relatifs au bruit, anomalies).

## Résultats
| Série | Avant | Après |
|-------|-------|-------|
| PEO_N_22 | 15 ok, 9 no_signal, 1 U_dephase | identique |
| PEO_N_41 | 29 ok, 1 no_signal, 1 U_saut | identique |
| PEO_N_43 | 26 ok, 2 U_saut | identique |
| test_2026-10-06_06 | 6 no_signal | #1 no_signal, #2-#6 ok, 249,8 Hz, rapport cyclique 0,49, U +300 / −20 V |

## Limites connues
- Bruit coloré (filtré) : le σ des différences le sous-estime -> seuil plus permissif.
- Glitchs d'1 pas sur < 10 % des points : pas de quantification non reconnu ; la capture
  peut sortir `no_plateau` au lieu de `no_signal`.
- Série test : I des plateaux à 1-5 pas du zéro (I non résolu) ; le mode de pilotage
  (« tension contrôlée ») y est peu fiable.
