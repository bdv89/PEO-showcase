# TODO_v2 — Fiche d'expérience, traçabilité, re-traitement, refonte de l'onglet Mesure

> Date : 2026-10-06 — Boucle 1 (design), à critiquer avant exécution.
> Objectif : savoir **qui a fait quelle expérience, sur quoi, comment**, sans cahier de labo.

## Décisions (Phase 0)
| Sujet | Décision |
|---|---|
| Fiche | Échantillon, bain, consigne de pilotage, opérateur, notes, tags libres avec suggestions |
| Après l'essai | Résultats mesurés (clé / valeur / unité) + pièces jointes, modifiables après coup |
| Stockage | Tout dans `{id}_meta.json` : le dossier de série reste autonome |
| ID | `{préfixe}_AAAA-MM-JJ_NN` (préfixe modifiable, défaut PEO), figé au lancement, aucun dossier existant écrasé |
| Rigueur | Historique des modifications, SHA-256 des fichiers bruts, version de l'algorithme tracée |
| Lancement | Armement à la main à chaque essai ; l'enregistrement démarre à la détection du signal |
| Fiche incomplète | Pas de blocage. Pendant la manip : bandeau + champs vides en rouge, et on **reste sur l'onglet Mesure** |
| Re-traitement | « Ouvrir une série… » (sélecteur de dossier), résultats régénérés dans le dossier de la série |
| Onglet Mesure | 3 colonnes : Expérience \| Scope \| live, pré-rempli avec la session précédente |
| Look | Charte Materianova (inventaire_cibles), clair + bascule sombre, logo embarqué |

## Schéma `meta.json` v2 (rétro-compatible)
Les clés actuelles restent à la racine (`experiment_id`, `channels`, `rate`, `captures`…), parce que
`extract_plateaux.py` lit `captures[i].timestamp`. Ajouts :
```
schema: 2, uuid, station (nom du PC), utilisateur_windows
dates: {armee, debut (détection), fin}            # ISO 8601, heure locale + fuseau
fiche: {operateur, objectif,
        echantillon: {id, materiau, surface_cm2, preparation},
        bain: {composition, concentration, temperature_C, pH, reference},
        consigne: {mode, valeur, unite, frequence_Hz, rapport_cyclique, polarite, duree_prevue},
        tags: [], notes}
acquisition: {voies: {C2: {label, unit, factor}...}, scope: {vdiv, couplage, tdiv, trigger}}
captures[i].heure                                  # ISO, en plus du timestamp monotone
empreintes: {fichier: sha256}                      # calculées en fin de série
resultats: [{nom, valeur, unite, date}]
pieces_jointes: [{fichier, sha256, ajoute_le}]     # copiées dans {série}/pieces_jointes/
analyses: [{date, algo_version, parametres, synthese}]
historique: [{date, utilisateur, champ, avant, apres}]
```
Une série ancienne (PEO_N_22…) s'ouvre normalement. Sa fiche se complète après coup, et ce
complément est journalisé. Ses empreintes sont calculées à la première ouverture et marquées
« enregistrées a posteriori ».

## Tâches (TDD)
1. `scope/experiment.py` (cœur pur, Qt-free) : génération de l'ID (`next_id`), dataclass de la
   fiche, `missing_fields`, lecture/écriture du meta v2 avec migration v1 → v2, `apply_edit`
   (avec journal), `sha256` et `verify_checksums`, ajout de pièces jointes et de résultats,
   suggestions de tags (parcours des meta d'un dossier racine).
2. `series.py` : dates ISO (armement, début, fin, heure de chaque capture), empreintes en fin de
   série, acquisition (configuration des voies et réglages scope) dans le meta, refus si le dossier existe.
3. `plateaux.py` : `ALGO_VERSION` + `parametres()` (instantané des constantes) ;
   `reprocess(series_dir)` = vérification des empreintes, analyse des CSV, sorties régénérées,
   entrée ajoutée dans `analyses`. Les données brutes ne sont jamais modifiées.
   `extract_plateaux.py` peut réutiliser cette fonction.
4. GUI, onglet **Mesure** en 3 colonnes :
   - **Expérience** : ID (lecture seule, proposé), opérateur, échantillon, bain, consigne, tags
     (autocomplétion), notes, bouton **Armer** ;
   - **Scope** : voies, timebase, trigger, seuil de départ, cadence et durée ;
   - **live**.
   Bandeau d'alerte et champs vides en rouge pendant une manip si la fiche est incomplète. La
   fiche reste modifiable pendant l'enregistrement : chaque modification est écrite dans le meta
   et journalisée.
5. GUI, onglet **Analyse** :
   - en-tête avec ID, échantillon, tags et boutons « Ouvrir une série… », « Fiche », « Re-traiter » ;
   - sélecteur de capture pour parcourir une série ouverte ;
   - dialogue **Fiche** : champs, résultats, pièces jointes, historique en lecture seule, état
     des empreintes.
6. Thème : QSS Materianova (clair et sombre) + graphes pyqtgraph assortis, bascule mémorisée,
   logo SVG local (`scope/assets/`).
7. Documentation (usage, architecture, README) et rebuild du dossier Windows.

## Points tranchés (2026-10-06)
- Pré-remplissage : tout reprendre **sauf** l'ID d'échantillon et les notes (repartent vides).
- Préfixe de l'ID **modifiable** (champ de la fiche, mémorisé ; défaut `PEO`).
- Catalogue / recherche : hors périmètre (préoccupation ultérieure).

## Exécution (2026-10-06)
- [x] 1. `scope/experiment.py` + `tests/test_experiment.py` (38 tests). Version d'algo = SHA-256
      de `plateaux.py` (pas de numéro à incrémenter ; `plateaux.py` reste à la session
      « peo-plateau-extraction », non modifié ici).
- [x] 2. `series.py` : meta créé à la détection, dates ISO, heure par capture, empreintes en fin
      de série, réglages réels (WAVEDESC), refus d'un dossier existant (+4 tests).
- [x] 3. `experiment.reprocess` (vérif. empreintes, `force`, captures retirées tracées).
      Copie de PEO_N_22 : 15/25, courant contrôlé, 75 empreintes a posteriori.
- [x] 4-5. GUI : en-tête logo + thème, bandeau d'alerte, Mesure 3 colonnes (Expérience | Scope |
      live), Analyse (Ouvrir / Fiche… / Re-traiter / parcours des captures).
- [x] 6. `scope/theme.py` (QSS Materianova clair/sombre, +5 tests), logo local `scope/assets/`.
- [x] 7. Docs (usage, architecture, README) ; dossier Windows reconstruit, testé avec son Python.
- Tests : 285 (284 OK + 1 skip) ; test préexistant du séparateur de chemin corrigé.
- Reste : essai sur matériel ; `{id}_controle.png` produit au re-traitement seulement (pas en direct).
