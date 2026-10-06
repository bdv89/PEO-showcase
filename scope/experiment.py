"""Fiche d'expérience et traçabilité d'une série : savoir qui a fait quoi, sur quoi, comment.

Tout vit dans le sidecar ``{id}_meta.json`` du dossier de série (pas de base
centrale : un dossier copié ou archivé reste autonome). Ce module est la seule
porte d'entrée pour le lire et l'écrire (:func:`load_meta`, :func:`update_meta`) :

- **schéma v2**, rétro-compatible : les clés historiques (``experiment_id``,
  ``captures``…) restent à la racine (``tools/extract_plateaux.py`` les lit), une
  série v1 est complétée à la lecture (:func:`migrate`) ;
- **fiche** (échantillon, bain, consigne, opérateur, tags, notes) et **historique**
  de chaque modification (date, utilisateur Windows, champ, avant, après) ;
- **empreintes SHA-256** des fichiers bruts (captures), vérifiées avant tout
  re-traitement : les données brutes ne sont jamais réécrites ;
- **analyses** : chaque passe d'extraction des plateaux est tracée avec la
  version de l'algorithme (empreinte de ``plateaux.py``) et ses paramètres ;
- **résultats** post-essai (clé / valeur / unité) et **pièces jointes** copiées
  dans ``pieces_jointes/``.

Qt-free et testable (``tests/test_experiment.py``), horloge murale injectable.
"""

from __future__ import annotations

import copy
import getpass
import hashlib
import json
import os
import re
import shutil
import threading
from datetime import date, datetime
from pathlib import Path

import numpy as np

from . import plateaux

SCHEMA = 2

# (clé pointée, libellé, obligatoire) -- l'ordre est celui du formulaire.
FICHE_FIELDS = [
    ("operateur", "Opérateur", True),
    ("objectif", "Objectif de l'essai", True),
    ("echantillon.id", "ID échantillon", True),
    ("echantillon.materiau", "Matériau", True),
    ("echantillon.surface_cm2", "Surface traitée (cm²)", True),
    ("echantillon.preparation", "Préparation", True),
    ("bain.composition", "Composition", True),
    ("bain.concentration", "Concentration", True),
    ("bain.temperature_C", "Température (°C)", True),
    ("bain.pH", "pH", True),
    ("bain.reference", "Réf. bain / âge", True),
    ("consigne.mode", "Mode piloté", True),
    ("consigne.valeur", "Consigne", True),
    ("consigne.unite", "Unité consigne", True),
    ("consigne.frequence_Hz", "Fréquence (Hz)", True),
    ("consigne.rapport_cyclique", "Rapport cyclique", True),
    ("consigne.polarite", "Polarité", True),
    ("consigne.duree_prevue", "Durée prévue", True),
    ("tags", "Tags", False),
    ("notes", "Notes", False),
]
FIELD_LABELS = {key: label for key, label, _ in FICHE_FIELDS}

# Repartent vides d'un essai à l'autre : les reprendre attribuerait l'essai au
# mauvais échantillon sans que personne ne le remarque.
NOT_PREFILLED = ("echantillon.id", "notes")

_PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_LOCK = threading.Lock()  # GUI (fiche) et thread d'acquisition (série) écrivent le même meta


class IntegrityError(Exception):
    """Des fichiers bruts ne correspondent plus à leur empreinte."""


# --- fiche ----------------------------------------------------------------------------
def empty_fiche() -> dict:
    fiche: dict = {}
    for key, _label, _req in FICHE_FIELDS:
        set_field(fiche, key, [] if key == "tags" else "")
    return fiche


def get_field(fiche: dict, key: str):
    node = fiche
    for part in key.split("."):
        node = node.get(part, "") if isinstance(node, dict) else ""
    return node


def set_field(fiche: dict, key: str, value) -> None:
    *parents, leaf = key.split(".")
    node = fiche
    for part in parents:
        node = node.setdefault(part, {})
    node[leaf] = value


def _is_empty(value) -> bool:
    return not value or (isinstance(value, str) and not value.strip())


def missing_fields(fiche: dict) -> list[str]:
    """Clés obligatoires encore vides (blanc = vide)."""
    return [key for key, _l, required in FICHE_FIELDS if required and _is_empty(get_field(fiche, key))]


def prefill(previous: dict) -> dict:
    """Fiche de l'essai suivant : reprise de la précédente sauf :data:`NOT_PREFILLED`."""
    fiche = _merge_fiche(copy.deepcopy(previous))
    for key in NOT_PREFILLED:
        set_field(fiche, key, "")
    return fiche


def parse_tags(text: str) -> list[str]:
    """``"a, b ,,a"`` -> ``["a", "b"]`` (ordre conservé, doublons et vides retirés)."""
    tags: list[str] = []
    for tag in (t.strip() for t in text.split(",")):
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _merge_fiche(fiche) -> dict:
    """Complète une fiche partielle (champ ajouté depuis, ancienne série) avec les vides."""
    merged = empty_fiche()
    if isinstance(fiche, dict):
        for key, _l, _r in FICHE_FIELDS:
            value = get_field(fiche, key)
            if value not in ("", None):
                set_field(merged, key, value)
    return merged


# --- identifiant, horodatage, utilisateur ------------------------------------------------
def validate_prefix(prefix: str) -> str:
    """Préfixe d'ID : lettres/chiffres/tirets (``_`` est le séparateur de l'ID)."""
    prefix = prefix.strip()
    if not _PREFIX_RE.match(prefix):
        raise ValueError(f"préfixe {prefix!r} invalide : lettres, chiffres et tirets seulement")
    return prefix


def next_id(outdir, prefix: str, day: date) -> str:
    """``{prefix}_{AAAA-MM-JJ}_{NN}`` : numéro suivant le plus haut déjà présent ce jour-là."""
    base = f"{validate_prefix(prefix)}_{day.isoformat()}_"
    pattern = re.compile(re.escape(base) + r"(\d+)$")
    numbers = [0]
    if Path(outdir).is_dir():
        numbers += [int(m.group(1)) for p in Path(outdir).iterdir() if (m := pattern.match(p.name))]
    return f"{base}{max(numbers) + 1:02d}"


def now_iso(clock=None) -> str:
    """Heure murale ISO 8601 avec fuseau (``2026-10-06T10:00:00+02:00``)."""
    moment = (clock or datetime.now)()
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.isoformat(timespec="seconds")


def current_user() -> str:
    """Session Windows/Linux : l'auteur d'une modification (pas d'authentification)."""
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — pas d'utilisateur identifiable
        return "?"


# --- meta.json ----------------------------------------------------------------------------
def meta_path(series_dir) -> Path:
    """``{dossier}_meta.json``, ou l'unique ``*_meta.json`` si le dossier a été renommé."""
    folder = Path(series_dir)
    exact = folder / f"{folder.name}_meta.json"
    if exact.exists():
        return exact
    found = sorted(folder.glob("*_meta.json"))
    if len(found) != 1:
        raise FileNotFoundError(f"aucun meta.json unique dans {folder} ({len(found)} trouvé(s))")
    return found[0]


def migrate(meta: dict) -> dict:
    """Complète un meta (v1 ou v2 partiel) avec les sections v2, sans rien retirer."""
    meta["schema"] = SCHEMA
    meta["fiche"] = _merge_fiche(meta.get("fiche"))
    for key in ("resultats", "pieces_jointes", "analyses", "historique"):
        meta.setdefault(key, [])
    meta.setdefault("empreintes", {})
    return meta


def load_meta(series_dir) -> dict:
    return migrate(json.loads(meta_path(series_dir).read_text(encoding="utf-8")))


def _write(path: Path, meta: dict) -> None:
    """Écriture atomique (fichier temporaire puis remplacement) : jamais de meta tronqué."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(jsonable(meta), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def create_meta(series_dir, meta: dict) -> Path:
    """Premier meta d'une série ; refuse d'écraser un meta existant (ID figé)."""
    path = Path(series_dir) / f"{meta['experiment_id']}_meta.json"
    with _LOCK:
        if path.exists():
            raise FileExistsError(f"{path} existe déjà : une série ne s'écrase jamais")
        _write(path, migrate(meta))
    return path


def update_meta(series_dir, mutate) -> dict:
    """Lit, modifie (``mutate(meta)``) et réécrit le meta sous verrou ; le retourne."""
    with _LOCK:
        path = meta_path(series_dir)
        meta = migrate(json.loads(path.read_text(encoding="utf-8")))
        mutate(meta)
        _write(path, meta)
    return meta


def jsonable(value):
    """Types numpy -> natifs, NaN/inf -> None (JSON strict)."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


# --- historique ------------------------------------------------------------------------------
def _log(meta, user, when, champ, avant, apres) -> None:
    meta["historique"].append({"date": when, "utilisateur": user, "champ": champ,
                               "avant": avant, "apres": apres})


def apply_fiche(meta: dict, fiche: dict, *, user: str, when: str) -> list[str]:
    """Reporte ``fiche`` dans le meta ; journalise chaque champ réellement modifié."""
    changed = []
    for key, _l, _r in FICHE_FIELDS:
        before, after = get_field(meta["fiche"], key), get_field(fiche, key)
        if isinstance(after, str):
            after = after.strip()
        if after != before:
            set_field(meta["fiche"], key, copy.deepcopy(after))
            _log(meta, user, when, key, before, after)
            changed.append(key)
    return changed


def set_results(meta: dict, results: list[dict], *, user: str, when: str) -> bool:
    """Remplace les résultats post-essai (liste de ``{nom, valeur, unite}``), journalisé."""
    if results == meta["resultats"]:
        return False
    _log(meta, user, when, "resultats", meta["resultats"], results)
    meta["resultats"] = copy.deepcopy(results)
    return True


# --- empreintes ---------------------------------------------------------------------------------
def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_files(series_dir, exp: str) -> list[str]:
    """Fichiers bruts d'une série : ``{exp}_NNNN.csv`` et ``{exp}_NNNN_C<n>.<ext>``
    (pas les sorties d'analyse, régénérables)."""
    pattern = re.compile(re.escape(exp) + r"_\d{4}(_C\d)?\.(csv|npy|npz|h5|mat)$")
    return sorted(p.name for p in Path(series_dir).iterdir() if p.is_file() and pattern.match(p.name))


def compute_checksums(series_dir, exp: str) -> dict:
    return {name: sha256_file(Path(series_dir) / name) for name in raw_files(series_dir, exp)}


def ensure_checksums(meta: dict, series_dir, *, user: str, when: str) -> bool:
    """Série sans empreintes (enregistrée avant le schéma v2) : les calcule maintenant,
    marquées « a posteriori » (elles prouvent l'intégrité depuis cette date seulement)."""
    if meta["empreintes"]:
        return False
    meta["empreintes"] = compute_checksums(series_dir, meta["experiment_id"])
    meta["empreintes_info"] = {"date": when, "a_posteriori": True}
    _log(meta, user, when, "empreintes", {}, f"{len(meta['empreintes'])} fichier(s), a posteriori")
    return True


def verify_checksums(meta: dict, series_dir) -> dict:
    """``{"ok", "modifie", "manquant", "nouveau"}`` : listes de noms de fichiers."""
    folder = Path(series_dir)
    report = {"ok": [], "modifie": [], "manquant": [], "nouveau": []}
    for name, digest in sorted(meta["empreintes"].items()):
        path = folder / name
        if not path.exists():
            report["manquant"].append(name)
        else:
            report["ok" if sha256_file(path) == digest else "modifie"].append(name)
    report["nouveau"] = [n for n in raw_files(folder, meta["experiment_id"]) if n not in meta["empreintes"]]
    return report


# --- pièces jointes ----------------------------------------------------------------------------
def add_attachment(meta: dict, series_dir, source, *, user: str, when: str) -> str:
    """Copie ``source`` dans ``pieces_jointes/`` (jamais d'écrasement : `` (2)``)."""
    source = Path(source)
    dest_dir = Path(series_dir) / "pieces_jointes"
    dest_dir.mkdir(exist_ok=True)
    dest, n = dest_dir / source.name, 1
    while dest.exists():
        n += 1
        dest = dest_dir / f"{source.stem} ({n}){source.suffix}"
    shutil.copy2(source, dest)
    entry = {"fichier": dest.name, "sha256": sha256_file(dest), "ajoute_le": when, "source": str(source)}
    meta["pieces_jointes"].append(entry)
    _log(meta, user, when, "pieces_jointes", None, dest.name)
    return dest.name


# --- analyses -------------------------------------------------------------------------------------
def algo_version() -> str:
    """Empreinte (12 hex) du source de ``plateaux.py`` : change à toute modification
    de l'algorithme, sans numéro de version à penser à incrémenter."""
    return sha256_file(plateaux.__file__)[:12]


def algo_parameters() -> dict:
    """Constantes numériques MAJUSCULES de ``plateaux`` (seuils, tolérances…)."""
    params = {}
    for name, value in vars(plateaux).items():
        if name.isupper() and not name.startswith("_") and not isinstance(value, (bool, np.bool_)):
            if isinstance(value, (int, np.integer)):
                params[name] = int(value)
            elif isinstance(value, (float, np.floating)):
                params[name] = float(value)
    return params


def record_analysis(meta: dict, summary: dict | None, *, origine: str, user: str, when: str,
                    integrite: dict | None = None, force: bool = False) -> dict:
    """Ajoute une passe d'analyse au meta (version + paramètres + synthèse)."""
    entry = {
        "date": when,
        "utilisateur": user,
        "origine": origine,
        "algo_version": algo_version(),
        "parametres": algo_parameters(),
        "force": force,
        "integrite": {k: v for k, v in (integrite or {}).items() if k != "ok"},
        "synthese": jsonable(summary or {}),
    }
    meta["analyses"].append(entry)
    return entry


# --- re-traitement ----------------------------------------------------------------------------------
def read_capture(path, columns=None):
    """CSV de capture -> ``(t, U en V, I en A)``. ``columns`` : noms des colonnes U et I
    (défaut : 2e et 3e colonnes, comme les anciennes séries). Unité lue dans le suffixe
    du nom de colonne (``sonde HT_kV`` -> kV) puis convertie (:func:`plateaux.to_si`)."""
    import pandas as pd

    d = pd.read_csv(path)
    names = list(columns) if columns else list(d.columns[1:3])
    t = d.iloc[:, 0].to_numpy(float)
    arrays = []
    for name, expected, word in zip(names, ("V", "A"), ("tension", "courant")):
        unit = name.rsplit("_", 1)[1] if "_" in name else ""
        values, base = plateaux.to_si(d[name].to_numpy(float), unit)
        if base != expected:
            raise ValueError(f"{Path(path).name} : colonne {name!r} en {unit}, une {word} est attendue")
        arrays.append(values)
    return t, arrays[0], arrays[1]


def capture_columns(meta: dict):
    """Noms des colonnes U/I d'après les voies enregistrées (série v2), sinon None."""
    voies = meta.get("acquisition", {}).get("voies", {})
    u, i = meta.get("u_channel"), meta.get("i_channel")
    if not (u in voies and i in voies):
        return None
    return tuple(f"{voies[ch].get('label') or ch}_{voies[ch].get('unit', 'V')}" for ch in (u, i))


def reprocess(series_dir, *, user: str, when: str, force: bool = False,
              out_dir=None, per_capture_png: bool = True) -> dict:
    """Re-traite une série enregistrée avec l'algorithme actuel.

    Vérifie d'abord les empreintes (calculées a posteriori si absentes) : un fichier
    brut modifié bloque le re-traitement (:class:`IntegrityError`) sauf ``force``. Une
    capture absente est permise (retirée volontairement) mais tracée. Écrit dans
    ``out_dir`` (défaut : le dossier de série) : ``{exp}_plateaux.csv``,
    ``{exp}_UI_vs_t.png``, ``{exp}_controle.png`` et, si ``per_capture_png``, un
    ``{exp}_NNNN_plateaux.png`` par capture. Les données brutes ne sont jamais écrites ;
    le meta du dossier de série reçoit toujours la trace de l'analyse (traçabilité).
    Retourne la synthèse de :func:`plateaux.finalize_series` + ``"integrite"``."""
    folder = Path(series_dir)
    out = Path(out_dir) if out_dir is not None else folder
    out.mkdir(parents=True, exist_ok=True)
    meta = load_meta(folder)
    exp = meta["experiment_id"]
    n_hist = len(meta["historique"])
    new_checksums = ensure_checksums(meta, folder, user=user, when=when)
    report = verify_checksums(meta, folder)
    if report["modifie"] and not force:
        raise IntegrityError("fichiers bruts modifiés depuis l'enregistrement : " + ", ".join(report["modifie"]))

    columns = capture_columns(meta)
    caps = sorted(meta["captures"], key=lambda c: c["index"])
    t0 = caps[0]["timestamp"] if caps else 0.0  # origine : début de l'acquisition
    rows, captures, absent = [], [], []
    for cap in caps:
        path = folder / f"{exp}_{cap['index']:04d}.csv"
        if not path.exists():  # retirée volontairement (bruitée…) : tracée, pas bloquante
            absent.append(cap["index"])
            continue
        t, U, I = read_capture(path, columns)
        row, traces = plateaux.analyse_arrays(t, U, I)
        row = {"index": cap["index"], "t_s": cap["timestamp"] - t0, **row}
        rows.append(row)
        captures.append((row, traces or (t, U, I, [], [])))

    summary = plateaux.finalize_series(out, exp, rows) or {"experiment": exp, "n_captures": 0, "n_ok": 0}
    if per_capture_png:
        stale = re.compile(re.escape(exp) + r"_\d{4}_plateaux\.png$")
        for old in out.iterdir():
            if stale.match(old.name):
                old.unlink()
        for row, (t, U, I, runs_pos, runs_neg) in captures:  # flags finaux (U_saut) connus ici
            if runs_pos or runs_neg:
                plateaux.save_selection_png(t, U, I, runs_pos, runs_neg,
                                            out / f"{exp}_{row['index']:04d}_plateaux.png",
                                            title=f"{exp} — capture {row['index']} ({row['flag']})")
    if captures:
        plateaux.save_control_png(captures, out / f"{exp}_controle.png", title=exp)

    # Captures listées au meta sans CSV : seul témoin d'un retrait antérieur aux
    # empreintes (série v1), qui n'apparaît donc pas dans « manquant ».
    entry = record_analysis(meta, summary, origine="re-traitement", user=user, when=when,
                            integrite={**report, "captures_absentes": absent}, force=force)
    entry["sorties"] = str(out)
    new_history = meta["historique"][n_hist:]

    def persist(m):
        if new_checksums and not m["empreintes"]:
            m["empreintes"], m["empreintes_info"] = meta["empreintes"], meta["empreintes_info"]
        m["historique"].extend(new_history)
        m["analyses"].append(entry)

    update_meta(folder, persist)
    return {**summary, "integrite": entry["integrite"]}


# --- tags -----------------------------------------------------------------------------------------
def collect_tags(root) -> list[str]:
    """Tags déjà utilisés dans les séries de ``root`` (suggestions d'autocomplétion)."""
    tags: set[str] = set()
    root = Path(root)
    if not root.is_dir():
        return []
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        try:
            meta = json.loads(meta_path(folder).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fiche_tags = meta.get("fiche", {}).get("tags", []) if isinstance(meta.get("fiche"), dict) else []
        tags.update(t for t in fiche_tags if isinstance(t, str))
    return sorted(tags)
