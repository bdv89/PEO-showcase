"""Affichage temps quasi-réel des waveforms (pyqtgraph, import paresseux).

pyqtgraph est préféré à matplotlib pour le live : rafraîchissement fluide via
un ``QTimer``. Ferme la fenêtre pour quitter.

Le fetch récupère toujours toute la mémoire d'acquisition (``NP`` non plafonné —
voir ``docs/scpi-reference.md``, le sparsing/zoom matériel ne couvre pas toute la
portée temporelle sur ce firmware) ; ``decimate()`` réduit ensuite uniquement ce
qui est **dessiné**, sur toute la fenêtre reçue.
"""

from __future__ import annotations

from . import control
from .gui import DescriptorCache, decimate

DISPLAY_MAX_POINTS = 4000  # points dessinés par courbe, cf. gui.DISPLAY_POINTS_DEFAULT


def run_live(scope, channels: list[str], *, interval_ms: int = 100, autostart: bool = True) -> None:
    """Boucle d'affichage : ré-interroge le scope toutes les ``interval_ms``."""
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets

    if autostart:
        control.run(scope)  # acquisition continue

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = pg.GraphicsLayoutWidget(title="SDS1204X-E — live")
    plot = win.addPlot()
    plot.setLabel("bottom", "Temps", units="s")
    plot.setLabel("left", "Tension", units="V")
    plot.addLegend()
    plot.showGrid(x=True, y=True, alpha=0.3)

    curves = {
        ch: plot.plot(pen=pg.intColor(i, hues=len(channels)), name=ch)
        for i, ch in enumerate(channels)
    }

    # Les réglages (TDIV/VDIV/OFST) sont statiques pendant une session `live`
    # (pas de commandes de contrôle ici, contrairement à la GUI) : le
    # descripteur ne change donc pas frame à frame -> cache pour toute la
    # session (~2x moins de requêtes qu'un fetch() complet à chaque frame).
    cache = DescriptorCache()

    def update() -> None:
        for ch, curve in curves.items():
            try:
                wf = cache.fetch(scope, ch)
            except Exception as exc:  # une lecture ratée ne doit pas tuer la boucle
                print(f"[live] lecture {ch} échouée : {exc}")
                cache.discard(ch)
                continue
            t, v = decimate(wf.time, wf.volts, max_points=DISPLAY_MAX_POINTS)
            curve.setData(t, v)

    timer = QtCore.QTimer()
    timer.timeout.connect(update)
    timer.start(interval_ms)

    win.show()
    app.exec()
