# Inspiration — veille GitHub pour le pilote Siglent SDS1204X-E

Catalogue de dépôts GitHub étudiés en vue d'enrichir ce projet (pilote Python pour le
Siglent SDS1204X-E : contrôle SCPI/VISA, récupération/analyse de waveforms, visualisation
temps réel). Les 5 références les plus directement utiles sont clonées dans `repos/`
(voir section correspondante) ; les autres restent en liens externes.

## A. Cœur — contrôle SCPI Siglent en Python (référence directe)

| Dépôt | Langue | Cible | Ce qu'on emprunte |
|---|---|---|---|
| [lheywang/SDSpy](https://github.com/lheywang/SDSpy) | Python | Siglent SDS | API objet `Channel[i].SetCoupling()`, packaging Poetry/pip |
| [BobRyan530/sigctl](https://github.com/BobRyan530/sigctl) | Python | SDS1204 (B&K rebadgé) | VXI-11 ; `sigview.py` (temps réel) + `sigdump.py` (CSV, export Sigrok/PulseView) |
| [sanderberents/eelab](https://github.com/sanderberents/eelab) | Python | SDS1104X-U + AWG + PSU | scripts Bode / curve-tracer / datalogger / **autoscale**, contournements bugs firmware |
| [activexray/siglent](https://github.com/activexray/siglent) | Python | SSA3000X (spectre) | structure package multi-instruments |
| [TopQuark12/siglentRust](https://github.com/TopQuark12/siglentRust) | Rust | SDS2000X | perspective SCPI en Rust (early beta, ⚠ firmware) |

## B. Piloter via IA — MCP / Claude

| Dépôt | Langue | Cible | Ce qu'on emprunte |
|---|---|---|---|
| [MagnusJohansson/siglent-sds-mcp](https://github.com/MagnusJohansson/siglent-sds-mcp) | TypeScript | SDS1000X-E (dont 1204X-E) | 🔥 serveur **MCP** ; 12 tools ; SCPI socket 5025 ; parsing IEEE 488.2 + ADC→volts (même logique que notre `waveform.py`) → piste pour exposer `scope/` en MCP |

## C. GUI / applications complètes

| Dépôt | Langue | Cible | Ce qu'on emprunte |
|---|---|---|---|
| [klumw/sdsremote](https://github.com/klumw/sdsremote) | Dart/Flutter | **SDS1204X-E** | idées de features : macros SCPI (boucles/variables), screenshot, logging→PDF, profils `.lss` |
| [god233012yamil/Interfacing-an-Oscilloscope-Using-Python](https://github.com/god233012yamil/Interfacing-an-Oscilloscope-Using-Python) | Python | Rigol DS1202 | GUI PyQt5 + PyVISA + Matplotlib temps réel (comparer à notre `scope/gui.py`) |

## D. Bode plot (émulation AWG)

| Dépôt | Langue | Ce qu'on emprunte |
|---|---|---|
| [4x1md/sds1004x_bode](https://github.com/4x1md/sds1004x_bode) + forks [hb020](https://github.com/hb020/sds1004x_bode) (récent, +modèles), [donfbecker py3](https://github.com/donfbecker/sds1004x_bode_python3), [RedFantom](https://github.com/RedFantom/python-siglent-bode-server) | Python | serveur qui **émule un AWG Siglent** pour débloquer le Bode plot du scope avec un GBF tiers |

## E. Décodage / formats de waveform

| Dépôt | Langue | Ce qu'on emprunte |
|---|---|---|
| [geekman/siglent-bin2sr](https://github.com/geekman/siglent-bin2sr) | Go | format `.bin` SDS1000X-E (data @ `0x800`, 1 octet/éch., 128=zéro) → conversion volts + export Sigrok ; utile pour lire les fichiers du bouton Save/Recall |
| [little-did-I-know/SCPI-Instrument-Control](https://github.com/little-did-I-know/SCPI-Instrument-Control) | Python | export waveform multi-format NPZ/CSV/MAT/HDF5 |

## F. Briques transport & architecture (génériques)

| Dépôt | Langue | Ce qu'on emprunte |
|---|---|---|
| [lxi-tools/lxi-tools](https://github.com/lxi-tools/lxi-tools) ⭐613 | C | discovery VXI-11/mDNS, screenshot, benchmark, scripting Lua — patterns de référence |
| [alexforencich/python-vxi11](https://github.com/alexforencich/python-vxi11) | Python | driver VXI-11 pur Python (alternative directe à pyvisa-py pour LAN) |
| [python-ivi/python-ivi](https://github.com/python-ivi/python-ivi) (archivé) | Python | architecture IVI : sous-systèmes `acquisition`/`trigger`/`channels`/`measurement` |

## G. Exemples / scripts d'analyse

| Dépôt | Langue | Ce qu'on emprunte |
|---|---|---|
| [AI5GW/SIGLENT](https://github.com/AI5GW/SIGLENT) | Python | scripts FFT/MPX FM stéréo, import Bode CSV (SDS2104X HD) |
| [dimtass/web-interface-for-sdg1025](https://github.com/dimtass/web-interface-for-sdg1025) ([blog](https://www.stupid-projects.com/posts/write-python-scripts-for-your-siglent-sdg1025/)) | Python | interface web Flask+WebSocket pour instrument Siglent (AWG SDG1025, via USBTMC) |

## H. Hardware / reverse-engineering (hors périmètre logiciel, pour référence)

| Dépôt | Langue | Ce qu'on emprunte |
|---|---|---|
| [360nosc0pe/scope](https://github.com/360nosc0pe/scope) | Python/LiteX | bitstream FPGA open-source pour **SDS1204X-E** (Zynq-7000) — curiosité, pas réutilisable pour le pilote SCPI |

## Dépôts clonés localement (`repos/`)

Sélection = intersection « même matériel / mêmes 3 objectifs (piloter, récupérer/analyser,
visualiser) / code Python lisible ». Clonés en `--depth 1`.

| Dossier | Pourquoi celui-ci |
|---|---|
| `repos/siglent-sds-mcp` | piloter + parsing waveform identique à notre approche |
| `repos/sigctl` | VXI-11, waveform live + export CSV |
| `repos/SDSpy` | API objet Python pour SDS, packaging |
| `repos/eelab` | scripts d'analyse (Bode, autoscale, datalogger) |
| `repos/Interfacing-an-Oscilloscope-Using-Python` | GUI PyQt5 + PyVISA + Matplotlib temps réel |

## Pistes d'évolution pour notre projet

- [x] **Screenshot** (`sdsremote`, `lxi-tools`) → sous-commande `screenshot` (`scope/cli.py`).
- [x] **Mesures automatiques** (`siglent-sds-mcp`, `SDSpy`, `eelab`) → `scope/measure.py`
  (SCPI `PAVA?`) + sous-commande `measure` (`--params`/`--all`).
- [x] **Autoscale** (`eelab/vautoscale`) → `control.autoscale()` (volts/div + offset,
  recalculés côté client à partir de `PAVA? MIN`/`MAX`) + `set --autoscale`. Distinct de
  l'auto-setup firmware (`ASET`/`autoset()`).
- [x] **Découverte réseau** (idée reprise de `lxi-tools`, implémentée en scan TCP port
  5025 plutôt qu'en broadcast VXI-11/mDNS — plus simple, sans dépendance, marche sur le
  montage Ethernet direct) → `scope/discover.py` + sous-commande `discover`.
- [x] **Export multi-format** (`SCPI-Instrument-Control`) → `waveform.py:save()` étendu
  à NPZ (natif numpy), HDF5 (h5py) et MAT (scipy), en plus de CSV/`.npy`
  (`capture --format`).
- [ ] **MCP** (`siglent-sds-mcp`) → exposer `scope/` (connection.py, waveform.py,
  control.py) en serveur MCP pour piloter le scope en langage naturel depuis Claude.
- [ ] **Macros SCPI** (`sdsremote`, `lxi-tools`) → rejeu de séquences SCPI enregistrées.
- [ ] **Lecture des `.bin` exportés par le bouton Save/Recall** (`siglent-bin2sr`) →
  reportée : format non documenté dans ce dépôt, pas d'échantillon `.bin` disponible pour
  valider le décodage, repo de référence en Go non cloné.
- [ ] **Bode plot** (famille `sds1004x_bode`) → fonctionnalité optionnelle si un GBF
  tiers est disponible au banc.
