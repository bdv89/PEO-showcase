"""Tests de la couche sans Qt du launcher : détection des dépendances et
résolution de l'IP du scope (lecture/écriture config, décision demander/pas).

Pas d'import Qt ici (voir ``scope/gui.py``/``tests/test_gui.py`` pour le même
principe) : ``launcher.py`` n'importe Qt que dans son wrapper ``ask_ip_qt``,
jamais au niveau module.
"""

import json
from pathlib import Path

import pytest

import launcher


# --- deps_available --------------------------------------------------------


def test_deps_available_true_when_all_importable(monkeypatch):
    monkeypatch.setattr(launcher, "_find_spec", lambda name: object())
    assert launcher.deps_available() is True


def test_deps_available_false_when_one_missing(monkeypatch):
    def fake_find_spec(name):
        return None if name == "PyQt5" else object()

    monkeypatch.setattr(launcher, "_find_spec", fake_find_spec)
    assert launcher.deps_available() is False


# --- read_ip / write_ip -----------------------------------------------------


def test_read_ip_existing_config(tmp_path):
    config = tmp_path / "launcher_config.json"
    config.write_text(json.dumps({"ip": "192.168.1.50"}), encoding="utf-8")
    assert launcher.read_ip(config) == "192.168.1.50"


def test_read_ip_missing_config(tmp_path):
    config = tmp_path / "launcher_config.json"
    assert launcher.read_ip(config) is None


def test_read_ip_illisible_config(tmp_path):
    config = tmp_path / "launcher_config.json"
    config.write_text("{ceci n'est pas du json", encoding="utf-8")
    assert launcher.read_ip(config) is None


def test_read_ip_empty_field(tmp_path):
    config = tmp_path / "launcher_config.json"
    config.write_text(json.dumps({"ip": "  "}), encoding="utf-8")
    assert launcher.read_ip(config) is None


def test_write_ip_persists(tmp_path):
    config = tmp_path / "launcher_config.json"
    launcher.write_ip(config, "10.11.13.220")
    assert json.loads(config.read_text(encoding="utf-8")) == {"ip": "10.11.13.220"}


# --- resolve_ip --------------------------------------------------------------


def test_resolve_ip_uses_existing_config_without_asking(tmp_path):
    config = tmp_path / "launcher_config.json"
    config.write_text(json.dumps({"ip": "192.168.1.50"}), encoding="utf-8")

    def ask(default):
        raise AssertionError("ask ne doit pas être appelé si la config existe déjà")

    assert launcher.resolve_ip(config, ask) == "192.168.1.50"


def test_resolve_ip_asks_and_persists_when_no_config(tmp_path):
    config = tmp_path / "launcher_config.json"
    calls = []

    def ask(default):
        calls.append(default)
        return "10.0.0.5"

    ip = launcher.resolve_ip(config, ask)

    assert ip == "10.0.0.5"
    assert calls == [launcher.DEFAULT_IP]
    assert json.loads(config.read_text(encoding="utf-8")) == {"ip": "10.0.0.5"}


def test_resolve_ip_proposes_default_ip(tmp_path):
    config = tmp_path / "launcher_config.json"
    captured = {}

    def ask(default):
        captured["default"] = default
        return default

    launcher.resolve_ip(config, ask)

    assert captured["default"] == "10.11.13.220"


# --- lancement sans le dossier du script dans sys.path (Python embarqué) ------------------
# Le Python embarqué du dossier Windows (fichier ._pth) n'ajoute pas le dossier du script
# à sys.path (ModuleNotFoundError: scope au double-clic). « -P » reproduit ce cas.
# (pas « -I » : il masque aussi les paquets utilisateur -> faux « deps manquantes »)
def test_launcher_puts_its_folder_on_sys_path(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    script = Path(launcher.__file__)
    code = ("import runpy; runpy.run_path(r'%s', run_name='lanceur'); "
            "import scope; print('scope OK')" % script)
    res = subprocess.run([sys.executable, "-P", "-c", code], cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert "scope OK" in res.stdout


WINDOWS_PYTHON = Path(launcher.__file__).parent / "Oscilloscope" / "python" / "python.exe"


@pytest.mark.skipif(not WINDOWS_PYTHON.exists(), reason="dossier Windows autonome absent")
def test_windows_folder_check_with_its_own_python(tmp_path):
    # Contrôle de livraison : le lanceur du dossier Windows, avec SON Python embarqué.
    import subprocess

    dist = WINDOWS_PYTHON.parent.parent
    res = subprocess.run([str(WINDOWS_PYTHON), str(dist / "launcher.py"), "--check"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "scope OK" in res.stdout


def test_check_never_installs_anything(monkeypatch, capsys):
    monkeypatch.setattr(launcher, "deps_available", lambda *a: False)
    monkeypatch.setattr(launcher, "bootstrap", lambda: pytest.fail("--check ne doit rien installer"))
    monkeypatch.setattr(launcher, "setup_error_log", lambda *a: None)
    assert launcher.main(["--check"]) == 1


# --- journal des erreurs ------------------------------------------------------------------
@pytest.fixture
def error_log(tmp_path, monkeypatch):
    """Journal dans tmp_path ; hooks et flux restaurés après le test."""
    import sys
    import threading

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    path = launcher.setup_error_log(tmp_path / "logs" / "oscilloscope.log")
    yield path
    for h in launcher.log.handlers[:]:
        h.close()
        launcher.log.removeHandler(h)


def test_uncaught_exception_is_logged_with_traceback_and_time(error_log):
    import re
    import sys

    try:
        raise ValueError("voie C3 introuvable")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    text = error_log.read_text(encoding="utf-8")
    assert "Traceback" in text and "ValueError: voie C3 introuvable" in text
    assert re.search(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text, re.M)  # horodaté


def test_exception_in_thread_is_logged(error_log):
    import threading

    def boom():
        raise RuntimeError("acquisition interrompue")

    t = threading.Thread(target=boom, name="acquisition")
    t.start()
    t.join()
    text = error_log.read_text(encoding="utf-8")
    assert "acquisition" in text and "RuntimeError: acquisition interrompue" in text


def test_windowed_mode_output_goes_to_log(error_log, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "stdout", None)  # pythonw.exe : pas de console
    monkeypatch.setattr(sys, "stderr", None)
    launcher._redirect_output_for_windowed_mode()
    print("Connexion au scope 10.11.13.220 ...")
    assert "Connexion au scope" in error_log.read_text(encoding="utf-8")


def test_startup_failure_is_logged(error_log, monkeypatch):
    monkeypatch.setattr(launcher, "setup_error_log", lambda *a: error_log)
    monkeypatch.setattr(launcher, "deps_available", lambda *a: True)
    monkeypatch.setattr(launcher, "show_error_qt", lambda msg: None)

    def fail(*a):
        raise RuntimeError("scope injoignable")

    monkeypatch.setattr(launcher, "resolve_ip", fail)
    with pytest.raises(RuntimeError):
        launcher.main([])
    assert "RuntimeError: scope injoignable" in error_log.read_text(encoding="utf-8")
