"""Mesures automatiques du SDS1004X-E via SCPI ``PAVA?``.

Le scope calcule lui-même les mesures usuelles (amplitude, fréquence, rise
time...) ; on se contente de les demander et de parser la réponse. Format ::

    C1:PAVA PKPK,1.23E+00V
    C1:PAVA ALL,PKPK,1.23E+00V,FREQ,1.00E+03Hz,MEAN,****V

``****`` (ou toute valeur commençant par ``*``) signifie mesure indisponible
(pas de signal, hors écran, etc.) : on le traduit en ``None`` plutôt que de
lever, pour laisser l'appelant décider (cf. ``control.autoscale``).
"""

from __future__ import annotations

import re

from .waveform import parse_float

VALID_PARAMS = frozenset(
    {
        "PKPK",
        "MAX",
        "MIN",
        "AMPL",
        "TOP",
        "BASE",
        "MEAN",
        "CMEAN",
        "RMS",
        "CRMS",
        "OVSN",
        "FPRE",
        "OVSP",
        "RPRE",
        "PER",
        "FREQ",
        "PWID",
        "NWID",
        "RISE",
        "FALL",
        "WID",
        "DUTY",
        "NDUTY",
        "ALL",
    }
)


def parse_pava(response: str, param: str) -> float | None:
    """Extrait la valeur d'une réponse ``C<n>:PAVA <param>,<valeur><unité>``.

    Renvoie ``None`` si la valeur est indisponible (``****...``).
    """
    prefix = f"{param},"
    idx = response.find(prefix)
    if idx < 0:
        raise ValueError(f"paramètre {param!r} absent de la réponse {response!r}")
    value_str = response[idx + len(prefix) :].split(",")[0]
    if value_str.strip().startswith("*"):
        return None
    return parse_float(value_str)


def parse_pava_all(response: str) -> dict[str, float | None]:
    """Parse une réponse ``PAVA? ALL`` : paires ``PARAM,valeur`` en alternance.

    Cherche chaque paramètre connu individuellement (plutôt que de découper la
    chaîne entière en supposant un ordre/préfixe fixe) : le préfixe exact
    renvoyé par le firmware (avec ou sans ``ALL,`` littéral avant la première
    paire, ordre des paramètres) n'est pas garanti d'un firmware à l'autre,
    et cette recherche ciblée reste correcte quel que soit ce préfixe.

    ``(?<![A-Z])`` évite qu'un paramètre soit confondu avec la fin d'un autre
    qui le contient (ex. ``WID`` ne doit pas matcher dans ``PWID,``/``NWID,``,
    ``DUTY`` ne doit pas matcher dans ``NDUTY,``) : on exige que le caractère
    précédent ne soit pas une lettre majuscule.
    """
    result: dict[str, float | None] = {}
    for param in VALID_PARAMS - {"ALL"}:
        match = re.search(rf"(?<![A-Z]){param},([^,]*)", response)
        if match is None:
            continue
        value_str = match.group(1)
        result[param] = None if value_str.strip().startswith("*") else parse_float(value_str)
    return result


def measure(scope, channel: str, param: str) -> float | None:
    """Lit une mesure sur une voie (ex. ``measure(scope, "C1", "PKPK")``).

    Lève ``ValueError`` si ``param`` n'est pas un paramètre PAVA reconnu.
    Renvoie ``None`` si la mesure est indisponible sur le scope.
    """
    param = param.upper()
    if param not in VALID_PARAMS:
        raise ValueError(f"paramètre de mesure invalide {param!r}, attendu {sorted(VALID_PARAMS)}")
    response = scope.query(f"{channel}:PAVA? {param}")
    return parse_pava(response, param)


def measure_all(scope, channel: str) -> dict[str, float | None]:
    """Lit toutes les mesures d'une voie en une requête (``PAVA? ALL``)."""
    response = scope.query(f"{channel}:PAVA? ALL")
    return parse_pava_all(response)
