#!/usr/bin/env python3
"""Assemble un dossier Windows autonome (Python embeddable + dépendances)
pour le panneau de contrôle de l'oscilloscope -- exécutable depuis NixOS/Linux.

Ne compile rien : les wheels Windows (PyQt5, numpy, scipy, h5py...) sont de
simples zips qui embarquent déjà leurs DLL. On les télécharge en ciblant
``win_amd64``/``cp312`` et on les extrait tels quels dans le ``site-packages``
du Python embeddable -- aucun besoin de booter Windows pour construire, ce
dossier ne fait qu'exécuter le résultat.

Usage ::

    python packaging/build_embed.py [--out dist/Oscilloscope]

Produit ``dist/Oscilloscope/`` : dossier à copier tel quel sous Windows, avec
``Oscilloscope.bat`` (double-clic, pas de console) et ``Oscilloscope-debug.bat``
(console visible, pour diagnostiquer).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "dist" / "Oscilloscope"
REQUIREMENTS_APP = ROOT / "requirements-app.txt"

PYTHON_VERSION = "3.12.8"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
PTH_FILENAME = "python312._pth"

# Fichiers à ne pas copier depuis la racine du repo dans le dossier livré
# (config utilisateur : régénérée au premier lancement, pas de valeur figée
# à embarquer).
SKIP_COPY_FILES = {"launcher_config.json"}

BAT_TEMPLATE = """@echo off
pushd "%~dp0"
"%~dp0python\\{python_exe}" "%~dp0launcher.py" %*
popd
"""


def log(message: str) -> None:
    print(f"[build_embed] {message}")


def download(url: str, dest: Path) -> None:
    if dest.exists():
        log(f"déjà téléchargé : {dest.name}")
        return
    log(f"téléchargement {url} ...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def extract_python_embed(zip_path: Path, python_dir: Path) -> None:
    log(f"extraction de l'embeddable Python dans {python_dir} ...")
    python_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(python_dir)


def patch_pth_file(python_dir: Path) -> Path:
    """Décommente ``import site`` et ajoute ``Lib\\site-packages`` au ``._pth``.

    Sans ça, l'embeddable ignore complètement site-packages -- aucune
    dépendance installée n'est importable (piège n°1 de l'embeddable).
    """
    pth_files = list(python_dir.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError(f"aucun fichier ._pth trouvé dans {python_dir}")
    pth_path = pth_files[0]

    lines = pth_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    has_site_packages = False
    for line in lines:
        stripped = line.strip()
        if stripped in ("#import site", "import site"):
            new_lines.append("import site")
            continue
        if stripped == "Lib\\site-packages":
            has_site_packages = True
        new_lines.append(line)

    if not has_site_packages:
        # Avant la ligne "import site" pour rester dans l'esprit du fichier généré.
        insert_at = next(
            (i for i, l in enumerate(new_lines) if l.strip() == "import site"),
            len(new_lines),
        )
        new_lines.insert(insert_at, "Lib\\site-packages")

    pth_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    log(f"{pth_path.name} patché (import site + Lib\\site-packages)")
    return pth_path


def download_and_extract_wheels(site_packages: Path, wheelhouse: Path) -> None:
    site_packages.mkdir(parents=True, exist_ok=True)
    wheelhouse.mkdir(parents=True, exist_ok=True)

    log("téléchargement des wheels win_amd64/cp312 (pip download) ...")
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--platform",
            "win_amd64",
            "--python-version",
            "312",
            "--implementation",
            "cp",
            "--abi",
            "cp312",
            "-r",
            str(REQUIREMENTS_APP),
            "-d",
            str(wheelhouse),
        ]
    )

    wheels = sorted(wheelhouse.glob("*.whl"))
    if not wheels:
        raise RuntimeError(f"aucun wheel téléchargé dans {wheelhouse}")

    for wheel in wheels:
        log(f"extraction {wheel.name}")
        with zipfile.ZipFile(wheel) as zf:
            zf.extractall(site_packages)


def copy_app_code(out_dir: Path) -> None:
    log("copie du code applicatif (scope/, launcher.py) ...")
    scope_dst = out_dir / "scope"
    if scope_dst.exists():
        shutil.rmtree(scope_dst)
    shutil.copytree(
        ROOT / "scope",
        scope_dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("launcher.py", "channels_config.json"):
        src = ROOT / name
        if src.exists() and name not in SKIP_COPY_FILES:
            shutil.copy2(src, out_dir / name)


def write_bat_files(out_dir: Path) -> None:
    (out_dir / "Oscilloscope.bat").write_text(
        BAT_TEMPLATE.format(python_exe="pythonw.exe"), encoding="utf-8"
    )
    (out_dir / "Oscilloscope-debug.bat").write_text(
        BAT_TEMPLATE.format(python_exe="python.exe"), encoding="utf-8"
    )
    log("Oscilloscope.bat / Oscilloscope-debug.bat générés")


def check_fail_fast(python_dir: Path) -> None:
    """Vérifie la présence des fichiers dont l'absence casse silencieusement
    l'appli au runtime Windows (plugin Qt, runtime MSVC) -- mieux vaut échouer
    ici, au build, qu'au double-clic chez l'utilisateur."""
    site_packages = python_dir / "Lib" / "site-packages"

    qwindows = site_packages / "PyQt5" / "Qt5" / "plugins" / "platforms" / "qwindows.dll"
    if not qwindows.exists():
        raise RuntimeError(
            f"plugin de plateforme Qt introuvable : {qwindows} -- "
            "le wheel PyQt5 attendu embarque ce fichier, vérifier la version téléchargée."
        )
    log(f"OK : {qwindows.relative_to(python_dir)}")

    vcruntime = python_dir / "vcruntime140_1.dll"
    if not vcruntime.exists():
        # Absent des vieux embeddables ; scipy récent en a besoin. On le
        # récupère depuis un wheel qui le bundle (numpy/scipy le font
        # généralement dans leur dossier *.libs).
        candidates = list(site_packages.rglob("vcruntime140_1.dll"))
        if not candidates:
            raise RuntimeError(
                "vcruntime140_1.dll introuvable (ni dans l'embeddable, ni dans "
                "les wheels) -- scipy risque d'échouer au chargement sous Windows."
            )
        shutil.copy2(candidates[0], vcruntime)
        log(f"vcruntime140_1.dll copié depuis {candidates[0]}")
    else:
        log(f"OK : {vcruntime.relative_to(python_dir)}")


def build(out_dir: Path) -> None:
    downloads = ROOT / "packaging" / "_downloads"
    wheelhouse = ROOT / "packaging" / "_wheelhouse"

    embed_zip = downloads / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    python_dir = out_dir / "python"

    download(PYTHON_EMBED_URL, embed_zip)
    extract_python_embed(embed_zip, python_dir)
    patch_pth_file(python_dir)
    download_and_extract_wheels(python_dir / "Lib" / "site-packages", wheelhouse)
    copy_app_code(out_dir)
    write_bat_files(out_dir)
    check_fail_fast(python_dir)

    log(f"dossier prêt : {out_dir}")
    log("copier ce dossier sous Windows et double-cliquer Oscilloscope.bat")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="dossier de sortie (défaut : dist/Oscilloscope)"
    )
    args = parser.parse_args()
    build(args.out.resolve())


if __name__ == "__main__":
    main()
