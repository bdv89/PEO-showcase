"""Pilotage SCPI multiplateforme du Siglent SDS1204X-E (série SDS1004X-E).

Connexion LAN via PyVISA (backend ``pyvisa-py``, Python pur — pas de NI-VISA).
Modules :
  - ``connection``  : ouverture/fermeture de la ressource VISA, write/query bruts,
                      dump d'écran (``screen_dump``).
  - ``waveform``    : récupération + décodage des courbes en numpy, export CSV/npy.
  - ``control``     : réglages (timebase, vdiv, offset, couplage, trigger, run/stop).
  - ``acquisition`` : statut d'acquisition et attente de déclenchement (fondation
                      de la capture conditionnelle).
  - ``cli``         : point d'entrée ligne de commande.
  - ``live``        : affichage temps quasi-réel (pyqtgraph, import paresseux).
  - ``series``      : série de captures time-lapse (expérience datée, ID + cadence).
"""

from .acquisition import (
    parse_inr,
    parse_sample_status,
    read_inr,
    sample_status,
    triggered,
    wait_for_trigger,
)
from .connection import Scope, resource_string
from .series import RunResult, SeriesConfig, run_series, start_series
from .waveform import (
    Waveform,
    decimate,
    decode,
    fetch,
    parse_block,
    parse_descriptor,
    parse_float,
    save,
)

__all__ = [
    "Scope",
    "resource_string",
    "Waveform",
    "decimate",
    "decode",
    "fetch",
    "parse_block",
    "parse_descriptor",
    "parse_float",
    "save",
    "parse_inr",
    "parse_sample_status",
    "read_inr",
    "sample_status",
    "triggered",
    "wait_for_trigger",
    "RunResult",
    "SeriesConfig",
    "run_series",
    "start_series",
]
