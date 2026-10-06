"""Tracé statique d'une ou plusieurs waveforms (matplotlib, import paresseux)."""

from __future__ import annotations

from .channel_config import ChannelConfig, axis_assignment
from .waveform import Waveform


def plot_static(
    waveforms: list[Waveform],
    *,
    save_path: str | None = None,
    show: bool = True,
    max_points: int = 20_000,
):
    """Trace les courbes ; sauve un PNG si ``save_path``, affiche si ``show``.

    ``max_points`` : nombre de points max tracés par voie (décimation), pour
    rester fluide avec les acquisitions à mémoire profonde (plusieurs Mpts).

    Chaque waveform porte déjà sa conversion (``wf.values``/``wf.unit``, cf.
    ``Waveform``/``gui._do_capture``). Si deux unités distinctes sont présentes,
    la seconde est tracée sur un axe Y secondaire (``ax.twinx()``), même
    répartition que la GUI (:func:`channel_config.axis_assignment`).
    """
    import matplotlib

    if save_path and not show:
        matplotlib.use("Agg")  # backend sans fenêtre pour l'export pur
    import matplotlib.pyplot as plt

    # Réutilise axis_assignment avec des ChannelConfig ad hoc (unité déjà
    # portée par chaque Waveform) -- une seule fonction pure pour la règle
    # gauche/droite, partagée avec la GUI.
    configs = {wf.channel: ChannelConfig(unit=wf.unit) for wf in waveforms}
    mapping, left_unit, right_unit = axis_assignment(configs, [wf.channel for wf in waveforms])

    fig, ax_left = plt.subplots()
    ax_right = ax_left.twinx() if right_unit else None
    lines = []
    for wf in waveforms:
        ax = ax_right if mapping.get(wf.channel) == "right" else ax_left
        # Décimation pour l'affichage : tracer 3,5M points est lent et inutile.
        # `wf.values` est une property recalculée à chaque accès (volts * factor) :
        # on décime `wf.volts` (tableau brut) puis applique le facteur sur le
        # résultat décimé, pas deux fois sur le tableau complet (audit perf
        # 2026-07-14).
        step = max(1, len(wf.volts) // max_points)
        values = wf.volts[::step] * wf.factor
        (line,) = ax.plot(wf.time[::step], values, label=wf.display_name, linewidth=0.8)
        lines.append(line)

    ax_left.set_xlabel("Temps (s)")
    ax_left.set_ylabel(f"Amplitude ({left_unit})" if left_unit else "Amplitude")
    if ax_right is not None:
        ax_right.set_ylabel(f"Amplitude ({right_unit})")
    ax_left.grid(True, alpha=0.3)
    ax_left.legend(lines, [line.get_label() for line in lines])
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=120)
    if show:
        plt.show()
    return fig
