"""Pilotage des réglages du SDS1004X-E via SCPI.

Commandes du dialecte Siglent « historique » (série X-E), documentées dans le
guide de programmation (cf. ``docs/``). Toutes prennent un :class:`scope.Scope`.
"""

from __future__ import annotations

from . import measure as _measure

VALID_COUPLING = {"A1M", "D1M", "A50", "D50", "GND"}
VALID_SLOPE = {"POS", "NEG", "WINDOW"}
VALID_TRMD = {"AUTO", "NORM", "SINGLE", "STOP"}


def set_timebase(scope, value: str) -> None:
    """Règle la base de temps, ex. ``"1MS"``, ``"500US"``, ``"2NS"``."""
    scope.write(f"TDIV {value}")


def set_vdiv(scope, channel: str, value: str) -> None:
    """Règle les volts/division d'une voie, ex. ``"1V"``, ``"50MV"``."""
    scope.write(f"{channel}:VDIV {value}")


def set_offset(scope, channel: str, value: str) -> None:
    """Règle l'offset vertical d'une voie, ex. ``"0V"``, ``"-1.5V"``."""
    scope.write(f"{channel}:OFST {value}")


def set_coupling(scope, channel: str, value: str) -> None:
    """Règle le couplage : A1M, D1M, A50, D50, GND."""
    value = value.upper()
    if value not in VALID_COUPLING:
        raise ValueError(f"couplage invalide {value!r}, attendu {sorted(VALID_COUPLING)}")
    scope.write(f"{channel}:CPL {value}")


def enable_channel(scope, channel: str, on: bool = True) -> None:
    """Affiche (ON) ou masque (OFF) la trace d'une voie."""
    scope.write(f"{channel}:TRA {'ON' if on else 'OFF'}")


def set_trigger_source(scope, channel: str) -> None:
    """Sélectionne la source du trigger en mode edge, ex. ``"C1"``."""
    scope.write(f"TRSE EDGE,SR,{channel}")


def set_trigger_level(scope, channel: str, level: str) -> None:
    """Règle le niveau de déclenchement, ex. ``"1.0V"``."""
    scope.write(f"{channel}:TRLV {level}")


def set_trigger_slope(scope, channel: str, slope: str) -> None:
    """Règle le front du trigger : POS, NEG ou WINDOW."""
    slope = slope.upper()
    if slope not in VALID_SLOPE:
        raise ValueError(f"front invalide {slope!r}, attendu {sorted(VALID_SLOPE)}")
    scope.write(f"{channel}:TRSL {slope}")


def set_waveform_points(scope, count: int) -> None:
    """Plafonne le nombre de points renvoyés par ``WF? DAT2`` (SCPI :
    ``WFSU SP,1,NP,<count>,FP,0``) — envoie aussi ``SP,1``/``FP,0`` pour
    repartir d'un état propre (pas de sparsing résiduel).

    **Important : c'est un zoom, pas une décimation.** Avec ``FP=0``, le scope
    renvoie les ``count`` *premiers* points de la mémoire d'acquisition, à
    résolution native — la fenêtre temporelle affichée se **raccourcit**
    d'autant (elle ne montre plus tout le balayage écran, juste son début).
    C'est le compromis à connaître, différent de ce que visait ``WFSU SP``
    seul (même fenêtre, décimée) — qui s'est révélé sans effet réel.

    Seul levier **confirmé sur matériel** (`NP,1400` -> ~1400 pts affichés) :
    ``MSIZ`` a bloqué le SDS1204X-E puis cassé la liaison SCPI/LAN (ou a été
    silencieusement ignorée à l'arrêt), et ``WFSU TYPE``/``WFSU SP`` seuls
    étaient acceptés/confirmés par ``WFSU?`` sans jamais réduire le volume
    réellement transféré. Voir ``docs/scpi-reference.md`` pour l'historique.
    """
    if count < 1:
        raise ValueError(f"nombre de points invalide {count!r}, attendu >= 1")
    scope.write(f"WFSU SP,1,NP,{count},FP,0")


def set_trigger_mode(scope, mode: str) -> None:
    """Règle le mode de trigger : AUTO, NORM, SINGLE ou STOP (SCPI : TRMD).

    ``SINGLE`` arme une acquisition unique — combiné à ``run()`` (ARM) et
    ``acquisition.wait_for_trigger()``, c'est la base d'une capture déclenchée.
    """
    mode = mode.upper()
    if mode not in VALID_TRMD:
        raise ValueError(f"mode de trigger invalide {mode!r}, attendu {sorted(VALID_TRMD)}")
    scope.write(f"TRMD {mode}")


def autoset(scope) -> None:
    """Lance l'auto-configuration (équivalent du bouton Auto Setup)."""
    scope.write("ASET")


def run(scope) -> None:
    """Démarre l'acquisition continue."""
    scope.write("ARM")


def stop(scope) -> None:
    """Arrête l'acquisition."""
    scope.write("STOP")


def active_channels(scope) -> list[str]:
    """Liste les voies affichées (SCPI ``C<n>:TRA?``), parmi C1..C4."""
    channels = []
    for ch in ("C1", "C2", "C3", "C4"):
        if scope.query(f"{ch}:TRA?").strip().endswith("ON"):
            channels.append(ch)
    return channels


def autoscale(scope, channel: str, *, target_divs: float = 7.5, iterations: int = 2) -> None:
    """Cale automatiquement volts/div et offset d'une voie (autoscale logiciel).

    Mesure min/max du signal (``PAVA? MIN``/``MAX``) et ajuste ``OFST``/``VDIV``
    pour que le signal occupe ``target_divs`` divisions, centré à l'écran.
    Répété ``iterations`` fois (le réglage affine la mesure suivante).

    **Différent de** :func:`autoset` (bouton *Auto Setup* du firmware, commande
    ``ASET``) : celui-ci recalcule côté client à partir des mesures ``PAVA?``,
    ce qui permet de contourner les cas où l'auto-setup firmware ne converge
    pas bien (cf. ``eelab/vautoscale`` dans ``inspiration/``).

    Lève ``ValueError`` si le signal est indisponible (pas de signal branché,
    hors écran) — plutôt que d'appliquer un réglage aberrant.
    """
    for _ in range(iterations):
        vmin = _measure.measure(scope, channel, "MIN")
        vmax = _measure.measure(scope, channel, "MAX")
        if vmin is None or vmax is None:
            raise ValueError(
                f"{channel} : signal indisponible pour l'autoscale (pas de signal "
                "branché ou hors écran) — essayer un autoset (ASET) d'abord."
            )
        vpp = vmax - vmin
        v0 = vmin + vpp / 2
        set_offset(scope, channel, f"{-v0:.5f}V")
        set_vdiv(scope, channel, f"{vpp / target_divs:.5f}V")
