# Référence SCPI

Commandes SCPI réellement utilisées par le code, dans le dialecte **Siglent
« historique » (série X-E)**. Pour la spécification complète, voir le guide
officiel : [`siglent-sds-programming-guide.pdf`](siglent-sds-programming-guide.pdf)
(*Digital Oscilloscopes Programming Guide*, couvre la série SDS1000X-E /
SDS1004X-E).

Conventions :
- `C<n>` = voie (`C1`…`C4`).
- Les réponses numériques sont en notation scientifique avec suffixe d'unité
  (ex. `1.00E+00V`). Le code les extrait avec `parse_float` (dernier token).

## Identité

| Commande | Syntaxe | Exemple de réponse | Usage dans le code |
|----------|---------|--------------------|--------------------|
| `*IDN?` | query | `Siglent Technologies,SDS1204X-E,<série>,<firmware>` | `Scope.idn()` / sous-commande `idn` ; aussi `resync()` (recalage de file) |

## Acquisition / trigger

| Commande | Syntaxe | Exemple | Usage dans le code |
|----------|---------|---------|--------------------|
| `ARM` | write | `ARM` | `control.run()` — démarre l'acquisition continue (`set --run`, `live`) |
| `STOP` | write | `STOP` | `control.stop()` — arrête l'acquisition (`set --stop`) |
| `ASET` | write | `ASET` | `control.autoset()` — auto setup (`set --autoset`) |
| `TRSE` | write | `TRSE EDGE,SR,C1` | `control.set_trigger_source()` — trigger edge, source = voie |
| `C<n>:TRLV` | write | `C1:TRLV 1.0V` | `control.set_trigger_level()` — niveau de déclenchement |
| `C<n>:TRSL` | write | `C1:TRSL POS` | `control.set_trigger_slope()` — front : `POS`, `NEG`, `WINDOW` (validés) |
| `TRMD` | write | `TRMD SINGLE` | `control.set_trigger_mode()` — mode : `AUTO`, `NORM`, `SINGLE`, `STOP` (validés) ; `SINGLE` + `ARM` arme une acquisition unique |
| `SAST?` | query | `SAST Trig'd` | `acquisition.sample_status()` — statut d'acquisition (`Stop`/`Ready`/`Armed`/`Trig'd`) |
| `INR?` | query | `INR 8913` | `acquisition.read_inr()` / `wait_for_trigger()` — registre d'état interne ; **lit et efface** ; bit 0 = déclenché depuis la dernière lecture |

## Voies (vertical)

| Commande | Syntaxe | Exemple de réponse | Usage dans le code |
|----------|---------|--------------------|--------------------|
| `C<n>:VDIV` | write/query | `C1:VDIV 1.00E+00V` | `control.set_vdiv()` (`set --c1-vdiv 1V`) |
| `C<n>:OFST` | write/query | `C1:OFST -1.50E+00V` | `control.set_offset()` — offset vertical |
| `C<n>:CPL` | write | `C1:CPL D1M` | `control.set_coupling()` — couplage : `A1M`, `D1M`, `A50`, `D50`, `GND` |
| `C<n>:TRA` | write | `C1:TRA ON` | `control.enable_channel()` — affiche/masque la trace |

> Note : pendant une capture, VDIV et OFST ne sont **pas** relus par commande
> séparée — ils proviennent du descripteur WAVEDESC (voir plus bas), ce qui évite
> tout aller-retour et toute incohérence d'échelle.

## Base de temps / échantillonnage

| Commande | Syntaxe | Exemple de réponse | Usage dans le code |
|----------|---------|--------------------|--------------------|
| `TDIV` | write/query | `TDIV 1.00E-03S` | `control.set_timebase()` (`set --timebase 1MS`) |
| `SARA` | query | `SARA 1.00E+09Sa/s` | fréquence d'échantillonnage ; l'intervalle `1/SARA` est lu via le descripteur (`HORIZ_INTERVAL`), pas par cette commande |
| `WFSU SP,1,NP,<n>,FP,0` (`WAVEFORM_SETUP`) | write/query | `WFSU SP,1,NP,1400,FP,0` | `control.set_waveform_points()` — plafonne `WF? DAT2` à `n` points. **C'est un zoom sur le début du buffer** (résolution native, fenêtre temporelle raccourcie), pas une décimation sur toute la portée affichée. Ne touche pas l'acquisition (sûr en continu) ; **seul levier de réduction confirmé sur matériel** — `WFSU?` renvoie bien `NP` réglé **et** le volume réellement transféré change. **Plus utilisé par défaut depuis le 2026-07-08** : `live`/`gui`/`capture` fetchent toujours toute la mémoire et décimient côté client (`gui.decimate()`) — voir plus bas « Décimation vs zoom ». Reste disponible comme primitive bas niveau (`execute_command(("points", n))`) |

> **Historique — leviers testés et abandonnés.** Trois mécanismes ont été essayés avant
> `WFSU NP` ci-dessus pour réduire le volume de données transféré, tous sans effet réel :
> - `MSIZ` (`MEMORY_SIZE`, profondeur mémoire) envoyée pendant une acquisition ARMed a
>   bloqué le SDS1204X-E plusieurs minutes puis cassé la liaison SCPI/LAN ; envoyée à
>   l'arrêt, **silencieusement ignorée** (`MSIZ?` répondait toujours `14M` après `MSIZ 7K`).
> - `WFSU TYPE,0/1` (écran/mémoire) acceptée sans erreur mais **jamais reflétée** par
>   `WFSU?` (qui ne renvoie que `SP,NP,FP`, jamais `TYPE`) — aucune réduction observable.
> - `WFSU SP,<n>` seule (sparsing, sans toucher `NP`) était bien **confirmée par `WFSU?`**
>   (contrairement à `TYPE`) mais **sans effet réel sur le volume transféré** : le nombre
>   de points restait inchangé, seul le `Sa/s` affiché changeait (un artefact de calcul
>   côté client, pas une mesure réelle — `NP` reste inchangé à `0` = « tout envoyer »,
>   qui semble prioritaire sur `SP` pour `WF? DAT2` sur ce firmware).
>
> Conclusion : sur ce firmware, seul `NP` (nombre de points explicite) réduit
> vérifiablement le volume transféré ; `MSIZ`/`TYPE`/`SP` seuls sont soit inertes soit
> dangereux. Ne pas les réintroduire.
>
> **Re-testé le 2026-07-08 : `SP` reste inerte même envoyé avec `NP`/`FP` dans la même
> commande.** Hypothèse (réfutée) : les essais précédents envoyaient `SP` seul, sans
> `NP`/`FP` dans la même commande `WFSU` — peut-être ignoré comme mise à jour partielle.
> Test : `WFSU SP,4,NP,0,FP,0` (les 3 ensemble) vs `WFSU SP,1,NP,0,FP,0` (référence) sur
> `C1:WF? DAT2` : `WFSU?` confirme bien `SP,4` dans les deux cas, mais le volume transféré
> est **identique** (3 500 000 octets pour les deux), alors que le guide officiel décrit
> `SP=4` comme « sends every 4th data point » (devrait diviser par ~4). Comparé aux autres
> dépôts Siglent étudiés (`inspiration/repos/`) : le sparsing matériel fonctionne bien sur
> le dialecte **récent** `:WAV:INT <stride>` (ex. `eelab`, SDS1104X-U) mais pas sur le
> dialecte **historique X-E** (`WFSU`) de ce SDS1204X-E — cohérent avec le fait que
> `siglent-sds-mcp` (qui cible exactement notre modèle) a abandonné le sparsing matériel
> au profit du tout-transférer + décimation côté client. **`SP` est un cul-de-sac définitif
> sur ce firmware, quelle que soit la syntaxe. Ne plus jamais retester.**
>
> **`MSIZ` re-testé le 2026-07-08, hypothèse « famille de valeurs » réfutée aussi.** Le
> guide officiel (`inspiration/repos/siglent-sds-mcp/docs/programming-guide.md`) documente
> deux familles de tailles : `{7K,70K,700K,7M}` en mode non-interleaved (1 voie par ADC),
> `{14K,140K,1.4M,14M}` en interleaved. L'incident précédent avait envoyé `MSIZ 7K` alors
> que `MSIZ?` répondait `14M` — hypothèse : mauvaise famille de valeurs pour le mode actif.
> **Réfuté par un nouveau test, scope à l'arrêt, `MSIZ?` répondant déjà `7M` (même famille
> que `7K`)** : `MSIZ 7K` envoyée seule, hors boucle, reste **silencieusement ignorée**
> (`MSIZ?` répond toujours `7M` après). Sans danger cette fois (scope resté réactif,
> `*IDN?` répond normalement), mais confirme que `MSIZ` n'est pilotable en SCPI sur ce
> firmware **dans aucun cas testé** (bonne ou mauvaise famille de valeurs, à l'arrêt).
> Le gel du tout premier essai (pendant `ARM`, sondé en boucle par `WF? DESC`/`DAT2`)
> reste probablement lié au fait de l'envoyer **pendant une boucle de sondage active**,
> pas à la valeur elle-même — mais ce n'est **pas** à retester : aucune valeur de `MSIZ`
> n'a jamais eu d'effet observable sur ce firmware, seul le risque diffère selon le
> contexte d'envoi. **`MSIZ` reste un cul-de-sac définitif. Ne plus jamais retester.**
> Pour changer la profondeur mémoire, utiliser le menu Acquire du panneau physique du
> scope (hors SCPI).

## Mesures automatiques

| Commande | Syntaxe | Exemple de réponse | Usage dans le code |
|----------|---------|--------------------|--------------------|
| `C<n>:PAVA? <param>` | query | `C1:PAVA PKPK,1.23E+00V` | `measure.measure()` — sous-commande `measure` |
| `C<n>:PAVA? ALL` | query | `C1:PAVA ALL,PKPK,1.23E+00V,FREQ,1.00E+03Hz,MEAN,****V` | `measure.measure_all()` — `measure --all` |

Paramètres reconnus (`measure.VALID_PARAMS`) : `PKPK MAX MIN AMPL TOP BASE MEAN
CMEAN RMS CRMS OVSN FPRE OVSP RPRE PER FREQ PWID NWID RISE FALL WID DUTY NDUTY`
+ `ALL`. Le scope calcule lui-même la mesure (installée puis lue) ; **``****``**
en valeur signifie « mesure indisponible » (pas de signal, hors écran, mesure
non pertinente pour ce signal) — `parse_pava()` le traduit en `None` plutôt que
de lever, pour laisser l'appelant décider (cf. `control.autoscale`, qui
distingue ce cas d'un vrai signal).

Non repris de l'inspiration (`eelab`) : la phase inter-voies (`C2-C1:MEAD? PHA`)
répond avec des octets de terminaison non standards et nécessite `read_raw()`
plutôt que `query()` — écarté pour l'instant (YAGNI, cf. `inspiration/README.md`).

## Autoscale logiciel

`control.autoscale(scope, channel)` (`set --autoscale`) est **distinct** de
`ASET` (`autoset()`, auto-setup firmware). Il recalcule côté client, à partir
des mesures `PAVA? MIN`/`MAX` :

```
vpp = max - min
v0  = min + vpp / 2
OFST = -v0
VDIV = vpp / 7.5        (7,5 divisions verticales visées, cf. eelab)
```

Répété par défaut 2 fois (le réglage affine la mesure suivante). Si `MIN`/`MAX`
est indisponible (`****`, pas de signal), `autoscale` lève `ValueError` plutôt
que d'écrire un réglage aberrant.

## Lecture de waveform

Deux requêtes par voie, toutes deux lues via `Scope.query_block` (lecture
IEEE-488.2 octet-exact) :

### `C<n>:WF? DESC` — descripteur WAVEDESC

Renvoie un **bloc binaire de 346 octets** : le WAVEDESC, qui contient toutes les
échelles. Le code y lit quatre champs (offsets **à partir du marqueur
`WAVEDESC`**, **little-endian**) :

| Champ | Offset | Type | Signification | Constante (`waveform.py`) |
|-------|--------|------|---------------|---------------------------|
| `WAVE_ARRAY_COUNT` | 116 | `i32` | nombre de points | `_OFF_WAVE_ARRAY_COUNT` |
| `VERTICAL_GAIN` (VDIV) | 156 | `f32` | volts/division | `_OFF_VERTICAL_GAIN` |
| `VERTICAL_OFFSET` (OFST) | 160 | `f32` | offset vertical (V) | `_OFF_VERTICAL_OFFSET` |
| `HORIZ_INTERVAL` | 176 | `f32` | intervalle d'échantillonnage (s) = `1/SARA` | `_OFF_HORIZ_INTERVAL` |

`parse_descriptor()` localise `b"WAVEDESC"` dans le bloc puis dépacke ces offsets
avec `struct.unpack_from("<...", d, off)`. Si `count <= 0`, `fetch` lève
`ValueError` (« acquisition vide ») : le scope n'a pas déclenché.

### `C<n>:WF? DAT2` — données

Renvoie les **codes ADC** (octets signés `int8`) encapsulés dans un bloc
IEEE-488.2. La réponse complète a la forme :

```
C1:WF DAT2,#9<len><octets int8>\n\n
        │ │  └ len chiffres = nombre d'octets de données
        │ └ '9' = nombre de chiffres de len (ici 9)
        └ '#' = marqueur de bloc IEEE-488.2
```

Exemple : `C1:WF DAT2,#9000000346` + 346 octets + `\n\n`.

**Important** : les octets de données peuvent contenir `0x0A` (`\n`), qui ne sont
**pas** des fins de message. C'est pourquoi `query_block` lit l'en-tête puis
**exactement `len` octets**, sans se fier à la terminaison, et draine ensuite les
`\n`/`\r` résiduels. `parse_block` fait la même analyse sur une réponse brute
complète (et détecte une troncature si moins de `len` octets sont reçus).

### Décodage (formule Siglent)

`decode()` applique :

```
volt = code · (VDIV / 25) − OFST          (25 codes ADC par division verticale)
t[i] = (i − n/2) · interval               (axe temps centré sur le trigger)
interval = 1 / SARA  (= HORIZ_INTERVAL du descripteur)
```

avec `code` ∈ `int8` (−128…127), `n` = nombre de points. La constante 25
(`VERT_CODES_PER_DIV`) est spécifique au dialecte Siglent X-E. Le décodage est
**vectorisé** (NumPy) et reste pur (aucune I/O), donc testable hors matériel.

Exemple : à `VDIV = 1 V`, `OFST = 0`, un code `25` donne `25·(1/25) − 0 = 1 V` ;
un code `-25` donne `-1 V`. Avec `OFST = -1.5 V` et `VDIV = 2 V`, le code `25`
donne `25·(2/25) − (−1.5) = 3.5 V`.

## Capture d'écran

| Commande | Syntaxe | Réponse | Usage dans le code |
|----------|---------|---------|--------------------|
| `SCDP` (`SCREEN_DUMP`) | write, puis lecture brute | image BMP brute (commence par `b'BM'`) | `Scope.screen_dump()` / sous-commande `screenshot` |

**Différence avec `WF? DESC`/`DAT2`** : ce n'est **pas** un bloc IEEE-488.2 (pas
d'en-tête `#<n><len>`) — le transfert est délimité par le flag END en VXI-11. On
lit donc avec `read_raw()`, pas `query_block()`.

## Attente de déclenchement (fondation capture conditionnelle)

Séquence pour armer un trigger unique et attendre son déclenchement, **par
sondage** (pas de commande bloquante côté firmware) :

```
control.set_trigger_mode(scope, "SINGLE")   # TRMD SINGLE
read_inr(scope)                             # purge un résidu, AVANT armement
control.run(scope)                          # ARM — arme l'acquisition unique
wait_for_trigger(scope, timeout_s=10.0)      # sonde INR? jusqu'au bit 0, ou timeout
```

`wait_for_trigger` (module `scope/acquisition.py`) sonde `INR?` en boucle courte
(`poll_s`, défaut 50 ms) jusqu'à ce que le bit 0 (déclenché depuis la dernière
lecture) passe à 1, ou que `timeout_s` soit dépassé.

> **Piège constaté sur matériel (SDS1204X-E) — purger *avant* d'armer, jamais
> après.** Une première version purgeait `INR?` **après** `ARM` (« pour vider le
> latch »). Sur un signal rapide/propre (carré ~1 kHz testé), le trigger peut
> déjà être latché en moins d'une milliseconde — et le mode `SINGLE` ne se
> ré-arme pas tout seul après un déclenchement. Cette purge tardive consommait
> donc le déclenchement **réel** au lieu d'un résidu, et le `capture --single`
> faisait systématiquement timeout même avec un signal parfaitement valide.
> Correction : purger `INR?` (si besoin) **avant** `control.run()`, jamais entre
> l'armement et le sondage. `wait_for_trigger` ne purge plus rien lui-même.
>
> Autre piège relevé au passage : `SAST?` (statut d'acquisition) ne répond de
> façon fiable **qu'après un `ARM`** — envoyée seule sur une connexion fraîche
> (scope en `STOP`), elle ne répond jamais et fait timeout côté client. `INR?`,
> en revanche, répond de façon fiable dans tous les états testés. C'est
> pourquoi `wait_for_trigger` s'appuie uniquement sur `INR?`, jamais `SAST?`.
>
> Alternative existante mais **non retenue** : la commande bloquante `WAIT <t>`
> (bloque le traitement SCPI côté firmware jusqu'au trigger ou timeout) —
> jamais validée sur ce matériel, écartée par prudence après l'incident `MSIZ`
> (voir plus haut).

**Réutilisé tel quel par `series.py`** (mode de démarrage `--start threshold`
de la sous-commande `series`, cf. `docs/usage.md` § `series`) : même séquence
`TRSE`/`C<n>:TRLV`/`C<n>:TRSL`/`TRMD SINGLE`/`ARM` (`series.arm_threshold`),
puis attente du déclenchement — bloquante (`wait_for_trigger`) côté CLI,
sondage `INR?` non bloquant, un appel par tour de boucle (`series._default_poll`,
même primitive `triggered(read_inr(scope))`) côté GUI (`series.SeriesRunner`,
pour ne pas geler le thread d'acquisition pendant l'attente).

## Pipeline complet d'une capture

```
fetch(scope, "C1")
 ├─ query_block("C1:WF? DESC")  → 346 octets WAVEDESC
 │    parse_descriptor → count, vdiv, offset, interval
 │    count <= 0 ?  →  ValueError "acquisition vide"
 ├─ query_block("C1:WF? DAT2")  → octets int8 (codes)
 └─ decode(codes, vdiv, offset, interval, "C1")  → Waveform(time[], volts[])
```

## Pour aller plus loin

Le guide officiel ([`siglent-sds-programming-guide.pdf`](siglent-sds-programming-guide.pdf))
détaille l'ensemble du jeu de commandes (mesures, FFT, math, curseurs, sortie
écran, etc.) ainsi que la structure complète du bloc WAVEDESC. Si le PDF est
absent, la page officielle est :
<https://siglentna.com/resources/documents/digital-oscilloscopes/>.
