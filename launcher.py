#!/usr/bin/env python3
"""Lanceur simple : ouvre directement la GUI du scope, pensé pour un double-clic.

Deux modes, selon que les dépendances (PyQt5/pyvisa/numpy...) sont déjà présentes
dans l'interpréteur courant :

1. **Dossier autonome Windows** (``packaging/build_embed.py``, Python embeddable +
   dépendances pré-installées) : ``deps_available()`` est vrai, aucun venv/pip
   n'est tenté, la GUI s'ouvre directement.
2. **Poste de dev** (dépendances absentes) : fallback ``bootstrap()`` -- crée
   ``.venv`` et installe ``requirements.txt`` si besoin, puis se relance dans le
   venv (``os.execv``).

Dans les deux cas, l'IP du scope est demandée une seule fois (défaut
``10.11.13.220``) via une petite fenêtre Qt et mémorisée dans
``launcher_config.json`` a cote de ce fichier.

**Journal des erreurs** : ``logs/oscilloscope.log`` (horodaté, 3 fichiers de 1 Mo
en rotation), avec ou sans console. Y sont écrits : le démarrage (version de
Python), toute exception non gérée, y compris dans l'interface après son ouverture
et dans les threads (acquisition…), et, sous ``pythonw.exe`` (dossier autonome,
pas de console : ``sys.stdout``/``stderr`` valent ``None``), toute la sortie
standard. Une exception de démarrage est aussi remontée par une boîte de dialogue.

``--check`` : vérifie que l'application est importable (sans scope ni fenêtre) et
quitte -- contrôle d'un dossier Windows reconstruit ; n'installe jamais rien.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
# Le Python embarqué du dossier Windows (fichier ._pth) n'ajoute pas le dossier du
# script à sys.path : sans cette ligne, « import scope » échoue au double-clic.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VENV = ROOT / ".venv"
READY = VENV / ".ready"
REQUIREMENTS = ROOT / "requirements.txt"
CONFIG = ROOT / "launcher_config.json"
LOG_FILE = ROOT / "logs" / "oscilloscope.log"
DEFAULT_IP = "10.11.13.220"

log = logging.getLogger("oscilloscope")

# Dépendances dont la présence signale un environnement déjà prêt (dossier
# autonome Windows ou dev avec venv actif) -- pas besoin d'être exhaustif,
# juste représentatif des trois familles (GUI, VISA, calcul).
REQUIRED_MODULES = ("PyQt5", "pyvisa", "numpy")

# Indirection pour les tests (monkeypatch sans dépendre d'importlib au complet).
_find_spec = importlib.util.find_spec


# --- couche sans Qt : détection deps, résolution IP -----------------------------


def deps_available(modules: tuple[str, ...] = REQUIRED_MODULES) -> bool:
    """True si toutes les dépendances requises sont déjà importables."""
    return all(_find_spec(name) is not None for name in modules)


def read_ip(config_path: Path) -> str | None:
    """Lit l'IP mémorisée dans ``config_path``, ou None si absente/invalide."""
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    ip = data.get("ip", "").strip()
    return ip or None


def write_ip(config_path: Path, ip: str) -> None:
    """Mémorise ``ip`` dans ``config_path``."""
    config_path.write_text(json.dumps({"ip": ip}, indent=2) + "\n", encoding="utf-8")


def resolve_ip(config_path: Path, ask: Callable[[str], str]) -> str:
    """IP à utiliser : celle déjà mémorisée, sinon demandée via ``ask`` et écrite.

    ``ask(default)`` est injecté (dialogue Qt en prod, factice dans les tests) --
    reçoit l'IP par défaut à proposer et renvoie l'IP choisie par l'utilisateur.
    """
    existing = read_ip(config_path)
    if existing is not None:
        return existing

    ip = ask(DEFAULT_IP)
    write_ip(config_path, ip)
    return ip


# --- couche Qt : dialogue de saisie, boîte d'erreur -----------------------------


def ask_ip_qt(default: str) -> str:
    """Demande l'IP du scope via une petite fenêtre Qt (défaut pré-rempli)."""
    from pyqtgraph.Qt import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ip, ok = QtWidgets.QInputDialog.getText(
        None, "Oscilloscope", "IP du scope :", text=default
    )
    if not ok or not ip.strip():
        app.quit()
        raise SystemExit("Saisie de l'IP annulée.")
    return ip.strip()


def show_error_qt(message: str) -> None:
    """Affiche ``message`` dans une boîte de dialogue Qt (fallback stderr si Qt indisponible)."""
    try:
        from pyqtgraph.Qt import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        QtWidgets.QMessageBox.critical(None, "Oscilloscope -- erreur", message)
    except Exception:
        print(message, file=sys.stderr)


# --- bootstrap venv (fallback dev) ----------------------------------------------


def venv_python() -> Path:
    """Chemin du python du venv, selon la plateforme (cible reelle : Windows)."""
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def in_venv() -> bool:
    """True si l'interpreteur courant est deja celui de .venv."""
    return Path(sys.prefix).resolve() == VENV.resolve()


def bootstrap() -> None:
    """Cree .venv et installe les dependances si besoin, puis se relance dedans.

    Fallback dev uniquement (dossier autonome Windows : deps_available() déjà
    vrai, ce chemin n'est jamais emprunté). Ne revient jamais si la relance
    réussit (os.execv remplace le processus).
    """
    py = venv_python()

    if not py.exists():
        print(f"Creation de l'environnement virtuel dans {VENV} ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])

    if not READY.exists():
        print(f"Installation des dependances depuis {REQUIREMENTS.name} ...")
        subprocess.check_call([str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
        READY.write_text("ok\n", encoding="utf-8")

    print("Environnement pret, redemarrage ...")
    os.execv(str(py), [str(py), str(__file__), *sys.argv[1:]])


# --- journal des erreurs ------------------------------------------------------------


class _LogStream:
    """Flux de sortie (print) écrit dans le journal, ligne par ligne."""

    def __init__(self, level: int) -> None:
        self.level = level

    def write(self, text: str) -> None:
        for line in text.rstrip().splitlines():
            log.log(self.level, line)

    def flush(self) -> None:
        pass


def setup_error_log(log_file: Path | None = None) -> Path:
    """Journal horodaté (rotation 3 x 1 Mo) + capture des exceptions non gérées,
    du thread principal (dont les slots Qt : PyQt5 appelle ``sys.excepthook`` et
    n'interrompt plus l'application) comme des autres threads."""
    log_file = Path(log_file or LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    for old in log.handlers[:]:
        old.close()
        log.removeHandler(old)
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    def excepthook(exc_type, exc, tb):
        log.error("Exception non gérée", exc_info=(exc_type, exc, tb))
        if sys.stderr is not None and not isinstance(sys.stderr, _LogStream):
            sys.__excepthook__(exc_type, exc, tb)  # console : aussi à l'écran

    def thread_excepthook(args):
        name = args.thread.name if args.thread else "?"
        log.error("Exception dans le thread %s", name,
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    return log_file


def _redirect_output_for_windowed_mode() -> None:
    """Sous pythonw.exe, stdout/stderr valent None : la sortie standard part dans
    le journal. Avec une console, ne change rien."""
    if sys.stdout is None:
        sys.stdout = _LogStream(logging.INFO)
    if sys.stderr is None:
        sys.stderr = _LogStream(logging.ERROR)


def check() -> int:
    """``--check`` : l'application est-elle importable ? (dossier Windows reconstruit)"""
    import scope.gui  # noqa: F401  (import complet : Qt, pyqtgraph, numpy, pandas…)

    print(f"scope OK ({Path(scope.gui.__file__).parent})")
    log.info("--check : scope OK")
    return 0


def main(argv: list[str] | None = None) -> int | None:
    argv = sys.argv[1:] if argv is None else argv
    log_file = setup_error_log() or LOG_FILE
    _redirect_output_for_windowed_mode()
    log.info("Démarrage : Python %s (%s) %s", sys.version.split()[0], sys.executable, " ".join(argv))
    try:
        if not deps_available():
            if "--check" in argv:  # contrôle seulement : jamais d'installation
                print(f"Dépendances manquantes pour {sys.executable}")
                log.error("--check : dépendances manquantes (%s)", sys.executable)
                return 1
            if in_venv():
                # Déjà dans un venv mais dépendances manquantes : pas de boucle
                # de bootstrap possible, l'erreur doit remonter telle quelle.
                raise RuntimeError(
                    "Dépendances manquantes dans .venv -- réinstaller "
                    f"{REQUIREMENTS.name} (pip install -r {REQUIREMENTS})."
                )
            bootstrap()
            return None  # inatteignable si bootstrap() reussit (execv) ; garde-fou sinon
        if "--check" in argv:
            return check()

        ip = resolve_ip(CONFIG, ask_ip_qt)
        from scope.gui import run_gui

        log.info("Connexion au scope %s", ip)
        print(f"Connexion au scope {ip} ...")
        run_gui(ip, socket=True)
        log.info("Fermeture normale")
        return 0
    except SystemExit:
        raise
    except Exception:
        log.exception("Échec du lancement")
        message = traceback.format_exc()
        show_error_qt(
            "Échec du lancement de l'oscilloscope.\n\n"
            f"Détails dans {log_file}.\n\n{message}"
        )
        raise


if __name__ == "__main__":
    sys.exit(main())
