"""Configuration par voie : nom lisible, unité, facteur de conversion.

L'oscilloscope lit toujours des **volts** (formule Siglent dans ``waveform.py``).
Mesurer un courant (ou toute autre grandeur) suppose une sonde/shunt externe, donc
une conversion ``valeur = volts * factor`` (ex. shunt 0,1 Ω -> facteur 10 A/V).

Module entièrement Qt-free et testable : dataclass + persistance JSON + la
fonction pure :func:`axis_assignment` qui décide quelle voie va sur quel axe
d'affichage (même esprit que ``gui.decimate``/``gui.execute_command``).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

CHANNELS = ("C1", "C2", "C3", "C4")

DEFAULT_UNITS = ["V", "mV", "A", "mA", "W", "mW"]

# Racine du repo (scope/ est un sous-dossier), à côté de launcher_config.json.
CONFIG_PATH = Path(__file__).resolve().parent.parent / "channels_config.json"


@dataclass
class ChannelConfig:
    """Réglage d'affichage/export d'une voie : nom, unité, facteur de conversion."""

    label: str = ""
    unit: str = "V"
    factor: float = 1.0

    def display_name(self, channel: str) -> str:
        """Nom affiché : le label choisi, ou l'identifiant SCPI (« C1 »…) à défaut."""
        return self.label or channel


def load_channel_configs(path: Path = CONFIG_PATH) -> dict[str, ChannelConfig]:
    """Charge la config par voie depuis ``path``. Défauts si absent/illisible.

    Toujours une entrée pour chacune de :data:`CHANNELS`, même si le fichier ne
    les couvre pas toutes (ou pas du tout).
    """
    data = {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = raw
    except (OSError, json.JSONDecodeError):
        pass  # fichier absent ou corrompu : on repart de défauts propres

    configs = {}
    for ch in CHANNELS:
        entry = data.get(ch) if isinstance(data.get(ch), dict) else {}
        configs[ch] = ChannelConfig(
            label=str(entry.get("label", "")),
            unit=str(entry.get("unit", "V")),
            factor=float(entry.get("factor", 1.0)),
        )
    return configs


def save_channel_configs(configs: dict[str, ChannelConfig], path: Path = CONFIG_PATH) -> None:
    """Écrit la config par voie en JSON (une entrée par voie de ``configs``)."""
    data = {ch: asdict(cfg) for ch, cfg in configs.items()}
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def axis_assignment(
    configs: dict[str, ChannelConfig], active_channels
) -> tuple[dict[str, str], str | None, str | None]:
    """Répartit les voies actives sur l'axe gauche/droit selon leur unité.

    Règle simple (KISS) : la première unité rencontrée (voies actives triées)
    va à gauche, la deuxième unité distincte va à droite. Une éventuelle
    troisième unité (et au-delà) retombe sur l'axe droit (graduation
    approximative dans ce cas limite, pas de 3e axe -- cf. plan).

    Retourne ``(mapping, left_unit, right_unit)`` :
    - ``mapping[ch]`` vaut ``"left"`` ou ``"right"`` pour chaque voie active ;
    - ``left_unit``/``right_unit`` : unité affichée sur chaque axe, ou ``None``
      si l'axe est inutilisé (aucune voie active, ou une seule unité active).
    """
    mapping: dict[str, str] = {}
    units_seen: list[str] = []

    for ch in sorted(active_channels):
        unit = configs[ch].unit if ch in configs else "V"
        if unit not in units_seen:
            units_seen.append(unit)
        side = "left" if units_seen.index(unit) == 0 else "right"
        mapping[ch] = side

    left_unit = units_seen[0] if len(units_seen) >= 1 else None
    right_unit = units_seen[1] if len(units_seen) >= 2 else None
    return mapping, left_unit, right_unit


# --- réglages de l'onglet « Mesure » mémorisés entre deux lancements --------------
GUI_SETTINGS_PATH = CONFIG_PATH.with_name("gui_settings.json")

# Valeur par défaut de chaque réglage mémorisé ; son type sert aussi de contrôle
# au rechargement. Chaîne vide pour un combo = garder l'élément par défaut du widget.
GUI_SETTINGS_DEFAULTS = {
    "tab": 0,
    "active_channels": ["C2", "C3"],  # installation neuve : voies d'analyse cochées
    "vdiv": {},
    "coupling": {},
    "tdiv": "1MS",
    "points": "4000",
    "trig_src": "",
    "trig_slope": "",
    "trig_level": "1.0V",
    "outdir": "captures",
    "png": False,
    "id_prefix": "PEO",
    "fiche": {},          # dernière fiche d'expérience (pré-remplissage, cf. experiment.prefill)
    "theme": "clair",
    "series_rate": "1",
    "series_per": "minute",
    "series_duration": "60s",
    # Nouveaux noms de clés (2026-10-06) : les anciennes (series_mode « now »,
    # u_channel/i_channel C1/C2, thr_* du seuil séparé) sont ignorées au rechargement,
    # ce qui applique une fois ces défauts ; le dernier choix est ensuite mémorisé.
    "start_mode": "threshold",   # départ au seuil (réglages de la section Déclenchement)
    "series_delay": "5",
    "start_timeout": "30",
    "analysis_u": "C2",          # montage PEO : C2 = sonde HT
    "analysis_i": "C3",          #               C3 = courant
}


def load_gui_settings(path: Path = GUI_SETTINGS_PATH) -> dict:
    """Charge les réglages GUI mémorisés. Toujours toutes les clés de
    :data:`GUI_SETTINGS_DEFAULTS` : une clé absente ou d'un type inattendu
    reprend sa valeur par défaut, une clé inconnue (obsolète) est ignorée."""
    raw = {}
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    except (OSError, json.JSONDecodeError):
        pass  # fichier absent ou corrompu : on repart des défauts
    return {
        key: raw[key] if key in raw and type(raw[key]) is type(default) else default
        for key, default in GUI_SETTINGS_DEFAULTS.items()
    }


def save_gui_settings(settings: dict, path: Path = GUI_SETTINGS_PATH) -> None:
    """Écrit les réglages GUI en JSON."""
    Path(path).write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
