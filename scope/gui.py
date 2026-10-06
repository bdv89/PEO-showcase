"""Panneau de contrôle graphique interactif pour le SDS1204X-E (PyQt5/pyqtgraph).

Contrairement à ``live.py`` (affichage seul), cette fenêtre pilote aussi le scope
(run/stop, voies, VDIV/couplage, timebase, trigger, capture). Trois niveaux :

- fonctions Qt-free (``decimate``, ``execute_command``) : testables sans display,
  aucun import PyQt/pyqtgraph au chargement du module ;
- :class:`AcquisitionWorker` (``QThread``) : seul propriétaire de l'objet
  :class:`~scope.connection.Scope` (la ressource VISA n'est pas thread-safe et
  ``fetch`` peut bloquer plusieurs secondes sur mémoire profonde) ; exécute les
  commandes postées par l'UI et émet les trames par signaux Qt ;
- :class:`MainWindow` : widgets, poste des commandes dans la file, ne touche
  jamais le scope directement.
"""

from __future__ import annotations

import dataclasses
import os
import queue
import threading
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import control, experiment, gui_experiment, plateaux, series, theme
from .channel_config import (
    CONFIG_PATH,
    DEFAULT_UNITS,
    ChannelConfig,
    axis_assignment,
    load_channel_configs,
    load_gui_settings,
    save_channel_configs,
    save_gui_settings,
)

VDIV_VALUES = [
    "2MV", "5MV", "10MV", "20MV", "50MV", "100MV",
    "200MV", "500MV", "1V", "2V", "5V", "10V",
]
TDIV_VALUES = [
    "2NS", "5NS", "10NS", "20NS", "50NS", "100NS", "200NS", "500NS",
    "1US", "2US", "5US", "10US", "20US", "50US", "100US", "200US", "500US",
    "1MS", "2MS", "5MS", "10MS", "20MS", "50MS", "100MS", "200MS", "500MS",
    "1S", "2S", "5S", "10S", "20S", "50S",
]
# Décimation d'affichage (post-fetch, cf. decimate()) — PAS WFSU NP. Le fetch récupère
# toujours toute la mémoire (NP=0) ; ce réglage ne fait que réduire le nombre de points
# DESSINÉS, sur toute la portée temporelle reçue. Voir docs/scpi-reference.md et
# docs/architecture.md pour l'historique (WFSU NP est un zoom sur le début du buffer,
# pas une décimation — piège identifié le 2026-07-08).
DISPLAY_POINTS_VALUES = ["500", "1000", "2000", "4000", "10000", "20000", "50000"]
DISPLAY_POINTS_DEFAULT = "4000"
CHANNELS = ["C1", "C2", "C3", "C4"]

# Libellés affichés ; les combos portent le code SCPI en donnée (itemData), seul
# utilisé pour piloter le scope et mémoriser les réglages (gui_settings.json).
COUPLING_LABELS = {"D1M": "DC 1 MΩ", "A1M": "AC 1 MΩ", "D50": "DC 50 Ω", "A50": "AC 50 Ω",
                   "GND": "Masse"}
SLOPE_LABELS = {"POS": "Front montant", "NEG": "Front descendant", "WINDOW": "Fenêtre"}
START_MODE_LABELS = {"threshold": "Au seuil", "now": "Immédiat", "countdown": "Après un délai"}
PER_UNIT_LABELS = {"second": "seconde", "minute": "minute", "hour": "heure"}
_SCPI_PREFIXES = {"N": "n", "U": "µ", "M": "m"}


def _per_div_label(code: str, unit: str) -> str:
    """``"500US"`` -> ``"500 µs/div"`` ; ``"2MV"`` -> ``"2 mV/div"`` (M = milli ici)."""
    number = code.rstrip("NUMSV")
    prefix = code[len(number):-1]
    return f"{number} {_SCPI_PREFIXES.get(prefix, '')}{unit}/div"


def vdiv_label(code: str) -> str:
    return _per_div_label(code, "V")


def tdiv_label(code: str) -> str:
    return _per_div_label(code, "s")


def trigger_level_scpi(text: str) -> str:
    """Niveau saisi en volts à l'entrée du scope (« 1 », « 0,5 », « 1.0V ») -> ``"1V"``.
    ``ValueError`` si ce n'est pas un nombre."""
    value = float(text.strip().rstrip("Vv").strip().replace(",", "."))
    return f"{value:g}V"

# Anti-rebond (cf. MainWindow._debounced_put) : délai d'inactivité avant d'envoyer
# un réglage au scope. Valeur empirique -- assez court pour rester réactif, assez
# long pour absorber une molette/glissade rapide sur un combo (cause identifiée
# sur matériel d'une désynchronisation, cf. docs/usage.md § Dépannage).
DEBOUNCE_MS = 200


# --- couche Qt-free : décimation, dispatch SCPI ---------------------------------
# decimate() vit maintenant dans waveform.py (fonction pure, réutilisée par
# series.py sans dépendance PyQt) ; ré-exportée ici pour ne pas casser les
# imports existants (`from scope.gui import decimate`, tests/test_gui.py, live.py).
from .waveform import decimate  # noqa: F401


# Commandes qui peuvent changer les échelles/la portée d'une voie -> invalident
# le cache de descripteur (cf. DescriptorCache). "run"/"stop" en sont exclues :
# elles ne changent ni vdiv/offset/interval, juste si on acquiert ou non.
SETTINGS_COMMANDS = frozenset(
    {"timebase", "vdiv", "offset", "coupling", "enable", "points"}
)


class DescriptorCache:
    """Cache le descripteur WAVEDESC (vdiv/offset/interval) par voie entre frames.

    ``WF? DESC`` coûte à peu près aussi cher que ``WF? DAT2`` pour un petit
    payload (mesuré, ``tools/profile_capture.py``) : en régime stable (aucun
    réglage changé entre deux frames), le relire à chaque frame double le
    nombre de requêtes pour rien. Qt-free et testable sans matériel (via un
    faux ``scope``), comme ``decimate``/``execute_command``.

    Met aussi en cache l'**axe temps** décodé (``wf.time``) par voie : tant que
    le descripteur (donc ``count``/``interval``) n'a pas changé, cet axe est
    identique d'une frame à l'autre -- ``decode()`` le recevrait sinon en
    paramètre et le reconstruirait (``arange`` + 2 opérations) sur toute la
    mémoire native à chaque frame, pour rien (audit perf 2026-07-14). Vidé aux
    mêmes points que ``_cache`` (même durée de vie, un descripteur valide
    implique un axe temps valide).
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._time_cache: dict[str, np.ndarray] = {}

    def invalidate_if_setting(self, cmd_name: str) -> None:
        """Vide tout le cache si ``cmd_name`` peut changer une échelle/portée."""
        if cmd_name in SETTINGS_COMMANDS:
            self._cache.clear()
            self._time_cache.clear()

    def discard(self, channel: str) -> None:
        """Retire le descripteur en cache d'une voie (ex. après une erreur de lecture)."""
        self._cache.pop(channel, None)
        self._time_cache.pop(channel, None)

    def fetch(self, scope, channel: str, *, _resynced: bool = False):
        """Lit une trame, en réutilisant le descripteur (et l'axe temps) en cache
        quand possible.

        **Auto-guérison sur flux désynchronisé** : un changement de réglage
        (typiquement ``TDIV``, cf. bug observé sur matériel -- "WAVEDESC
        introuvable dans le descripteur") peut laisser le scope répondre par un
        bloc mal formé pendant qu'il se reconfigure en interne, désalignant
        durablement le flux binaire (même famille que la désync gérée à
        l'ouverture par ``Scope.flush_input()``). Sur toute exception ici, on
        appelle ``scope.resync()`` (répète ``*IDN?`` jusqu'à recalage, cf.
        ``connection.py``) puis on retente **une seule fois** -- au-delà,
        l'erreur remonte à l'appelant (``_acquire_frame``, qui l'affiche sans
        tuer la boucle live).
        """
        from .waveform import fetch_data, fetch_descriptor

        try:
            desc = self._cache.get(channel)
            if desc is None:
                desc = fetch_descriptor(scope, channel)
                self._cache[channel] = desc
            wf = fetch_data(scope, channel, desc, time=self._time_cache.get(channel))
            if len(wf.volts) != desc["count"]:
                # La mémoire a changé sans passer par une commande connue (rare) :
                # descripteur périmé -- on invalide et retente une fois à neuf
                # (axe temps aussi, sa longueur dépendait de l'ancien count).
                desc = fetch_descriptor(scope, channel)
                self._cache[channel] = desc
                self._time_cache.pop(channel, None)
                wf = fetch_data(scope, channel, desc)
            if channel not in self._time_cache:
                self._time_cache[channel] = wf.time
            return wf
        except Exception:
            if _resynced:
                raise
            self.discard(channel)
            scope.resync()
            return self.fetch(scope, channel, _resynced=True)


def _do_capture(scope, channels, outdir, png, configs: dict[str, ChannelConfig] | None = None) -> dict:
    """Lit les voies demandées, sauve un CSV combiné + un .npy par voie (+ PNG
    optionnel). Réutilise ``fetch``/``save_capture``.

    ``configs`` : réglage (nom/unité/facteur) par voie, appliqué à chaque
    waveform lue (:func:`dataclasses.replace`) avant export -- ``fetch`` reste
    en volts bruts, la conversion n'est attachée qu'ici. Défaut neutre
    (``ChannelConfig()``) pour une voie absente de ``configs``.

    Le CSV est **multi-colonnes** (une colonne par voie cochée, nommée par le
    label configuré) : un seul fichier `{stamp}.csv`, pas un par voie -- cf.
    :func:`scope.waveform.save_capture`. Les `.npy` restent un fichier par
    voie (`{stamp}_{ch}.npy`).
    """
    from datetime import datetime

    from .waveform import fetch, save_capture

    configs = configs or {}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    waveforms = []
    for ch in channels:
        wf = fetch(scope, ch)
        cfg = configs.get(ch, ChannelConfig())
        wf = dataclasses.replace(wf, label=cfg.label, unit=cfg.unit, factor=cfg.factor)
        waveforms.append(wf)

    paths = save_capture(waveforms, f"{outdir}/{stamp}")

    png_path = None
    if png:
        from .plot import plot_static

        png_path = f"{outdir}/{stamp}.png"
        plot_static(waveforms, save_path=png_path, show=False)

    return {"paths": paths, "channels": len(waveforms), "png": png_path}


def execute_command(scope, cmd: tuple):
    """Dispatch central tuple -> appel ``control``/capture. Point testable clé.

    Ne réimplémente aucun SCPI : délègue entièrement à ``control.py`` (réglages)
    et ``waveform.py``/``plot.py`` (capture), déjà testés indépendamment.
    """
    name, *rest = cmd
    if name == "timebase":
        (value,) = rest
        control.set_timebase(scope, value)
    elif name == "vdiv":
        ch, value = rest
        control.set_vdiv(scope, ch, value)
    elif name == "offset":
        ch, value = rest
        control.set_offset(scope, ch, value)
    elif name == "coupling":
        ch, value = rest
        control.set_coupling(scope, ch, value)
    elif name == "enable":
        ch, on = rest
        control.enable_channel(scope, ch, on)
    elif name == "run":
        control.run(scope)
    elif name == "stop":
        control.stop(scope)
    elif name == "autoset":
        control.autoset(scope)
    elif name == "trigger_source":
        (ch,) = rest
        control.set_trigger_source(scope, ch)
    elif name == "trigger_slope":
        ch, slope = rest
        control.set_trigger_slope(scope, ch, slope)
    elif name == "trigger_level":
        ch, level = rest
        control.set_trigger_level(scope, ch, level)
    elif name == "points":
        # Primitive SCPI brute (WFSU NP, zoom sur le début du buffer — cf.
        # control.set_waveform_points). N'est plus envoyée par le combo « Points
        # affichés » de la GUI (décimation d'affichage pure, côté client depuis le
        # 2026-07-08) ; conservée ici comme point d'entrée bas niveau testable.
        (n,) = rest
        control.set_waveform_points(scope, n)
    elif name == "capture":
        channels, outdir, png, *maybe_configs = rest
        configs = maybe_configs[0] if maybe_configs else None
        return _do_capture(scope, channels, outdir, png, configs)
    else:
        raise ValueError(f"commande gui inconnue : {cmd!r}")
    return None


# --- worker d'acquisition (thread dédié, seul propriétaire du Scope) -----------
class AcquisitionWorker:
    """Construit la vraie classe QThread au premier besoin (import Qt paresseux)."""

    def __new__(cls, *args, **kwargs):
        from pyqtgraph.Qt import QtCore

        class _AcquisitionWorker(QtCore.QThread):
            connected = QtCore.Signal(str)
            connection_failed = QtCore.Signal(str)
            waveform_ready = QtCore.Signal(str, object)
            acq_error = QtCore.Signal(str, str)
            capture_done = QtCore.Signal(object)
            command_error = QtCore.Signal(str)
            series_progress = QtCore.Signal(object)  # SeriesEvent (phase/index/total/...)
            series_done = QtCore.Signal(object)      # RunResult
            plateau_ready = QtCore.Signal(object)    # LiveAnalysis.add() : {row, traces, png}
            plateau_error = QtCore.Signal(str)       # analyse d'une capture impossible
            plateau_summary = QtCore.Signal(object)  # synthèse de fin de série (dict)

            def __init__(self, ip, *, socket, usb=False, timeout_ms, cmd_queue, interval_ms=100):
                super().__init__()
                self.ip = ip
                self.socket = socket
                self.usb = usb
                self.timeout_ms = timeout_ms
                self.cmd_queue = cmd_queue
                self.interval_ms = interval_ms
                self.scope = None
                self.acquiring = False
                self.active_channels: frozenset[str] = frozenset()
                self._running = False
                self._desc_cache = DescriptorCache()
                self.series: series.SeriesRunner | None = None
                self.analysis: plateaux.LiveAnalysis | None = None

            def run(self) -> None:
                from .connection import Scope

                try:
                    self.scope = Scope(
                        self.ip, socket=self.socket, usb=self.usb, timeout_ms=self.timeout_ms
                    )
                except Exception as exc:  # noqa: BLE001 — remonté à l'UI, pas fatal
                    self.connection_failed.emit(str(exc))
                    return

                self.connected.emit(self.scope.idn())
                self._running = True
                while self._running:
                    self._drain_commands()
                    if not self._running:
                        break
                    if self.series is not None:
                        # Prioritaire sur le live : suspend gratuitement l'acquisition
                        # continue (branche ci-dessous jamais atteinte tant qu'une
                        # série est active) -- reprend automatiquement à la fin si
                        # l'utilisateur avait laissé le live en Run. step() ne bloque
                        # jamais longtemps (une capture au plus par tour) donc la
                        # file de commandes reste drainée -- un "series_stop" posté
                        # est honoré au tour suivant.
                        for ev in self.series.step(self.scope, time.monotonic()):
                            self.series_progress.emit(ev)
                            if ev.kind == "capture":
                                for ch, wf in ev.waveforms.items():
                                    self.waveform_ready.emit(ch, wf)
                                self._analyse_capture(ev)
                        if self.series.finished:
                            self._finish_series()
                        time.sleep(self.interval_ms / 1000)
                        continue
                    if self.acquiring:
                        # Sleep adaptatif : ne pas ajouter interval_ms plein après
                        # un fetch qui a déjà pris du temps (mémoire profonde) --
                        # seul le temps RESTANT jusqu'à l'échéance est attendu.
                        t0 = time.monotonic()
                        self._acquire_frame()
                        remaining = self.interval_ms / 1000 - (time.monotonic() - t0)
                        if remaining > 0:
                            time.sleep(remaining)
                    else:
                        time.sleep(self.interval_ms / 1000)
                self.scope.close()

            def _drain_commands(self) -> None:
                while True:
                    try:
                        cmd = self.cmd_queue.get_nowait()
                    except queue.Empty:
                        return
                    self._handle(cmd)

            def _handle(self, cmd: tuple) -> None:
                name = cmd[0]
                if name == "quit":
                    if self.series is not None:
                        # Honore l'arrêt propre (meta écrit avec les captures déjà
                        # obtenues) avant de couper la boucle -- sinon une série
                        # interrompue en fermant la fenêtre perd son sidecar.
                        self.series.request_stop()
                        for ev in self.series.step(self.scope, time.monotonic()):
                            self.series_progress.emit(ev)
                        if self.series.finished:
                            self._finish_series()
                        self.series = None
                    self._running = False
                    return
                if name == "channels":
                    self.active_channels = cmd[1]
                    return
                if name == "series_start":
                    (config,) = cmd[1:]
                    self.series = series.SeriesRunner(config, clock=time.monotonic)
                    self.analysis = None
                    if config.u_channel and config.i_channel:
                        self.analysis = plateaux.LiveAnalysis(
                            os.path.join(config.outdir, config.experiment_id),
                            config.experiment_id, config.u_channel, config.i_channel,
                        )
                    return
                if name == "series_stop":
                    if self.series is not None:
                        self.series.request_stop()
                    return
                if name == "run":
                    self.acquiring = True
                elif name == "stop":
                    self.acquiring = False
                self._desc_cache.invalidate_if_setting(name)
                try:
                    result = execute_command(self.scope, cmd)
                except Exception as exc:  # noqa: BLE001 — feedback UI, boucle continue
                    self.command_error.emit(str(exc))
                    return
                if name == "capture":
                    self.capture_done.emit(result)

            def _analyse_capture(self, ev) -> None:
                """Extraction des plateaux d'une capture de série (+ PNG de
                vérification). Ici, dans le thread d'acquisition, pour ne pas
                figer l'UI ; une erreur d'analyse n'interrompt jamais la série."""
                if self.analysis is None:
                    return
                try:
                    rec = self.analysis.add(
                        ev.index, self.series.captures[-1]["timestamp"], ev.waveforms
                    )
                except Exception as exc:  # noqa: BLE001 — remonté à l'UI, série continue
                    self.plateau_error.emit(f"capture {ev.index} : {exc}")
                    return
                self.plateau_ready.emit(rec)

            def _finish_series(self) -> None:
                """Synthèse des plateaux (mode de pilotage, CSV, UI_vs_t.png) puis
                ``series_done``. La synthèse est calculée avant le signal (les
                fichiers existent à sa réception) mais émise après, pour que son
                message ne soit pas écrasé par celui de fin de série."""
                summary, error = None, None
                if self.analysis is not None:
                    try:
                        summary = self.analysis.finish()
                        if summary is not None:  # passe d'analyse tracée (version d'algo, paramètres)
                            experiment.update_meta(self.analysis.series_dir, lambda m: experiment.record_analysis(
                                m, summary, origine="série", user=experiment.current_user(),
                                when=experiment.now_iso()))
                    except Exception as exc:  # noqa: BLE001 — remonté à l'UI
                        error = f"synthèse : {exc}"
                    self.analysis = None
                self.series_done.emit(self.series.result)
                self.series = None
                if error:
                    self.plateau_error.emit(error)
                elif summary is not None:
                    self.plateau_summary.emit(summary)

            def _acquire_frame(self) -> None:
                for ch in sorted(self.active_channels):
                    try:
                        wf = self._desc_cache.fetch(self.scope, ch)
                    except Exception as exc:  # noqa: BLE001 — voie muette, pas fatal
                        self._desc_cache.discard(ch)
                        self.acq_error.emit(ch, str(exc))
                        continue
                    self.waveform_ready.emit(ch, wf)

        cls._impl = _AcquisitionWorker
        return _AcquisitionWorker(*args, **kwargs)


# --- fenêtre principale -----------------------------------------------------------
def _build_main_window(
    ip: str, *, socket: bool, usb: bool = False, timeout_ms: int, config_path=CONFIG_PATH
):
    """Construit la classe MainWindow (import Qt paresseux) et l'instancie."""
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

    class _Bridge(QtCore.QObject):
        done = QtCore.Signal(object)       # (dossier, synthèse)
        integrity = QtCore.Signal(object)  # (dossier, message)
        failed = QtCore.Signal(str)

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("SDS1204X-E — panneau de contrôle")
            self.cmd_queue: queue.Queue = queue.Queue()
            self.active_channels: set[str] = set()
            self.curves: dict[str, object] = {}
            self.config_path = config_path
            self.configs: dict[str, ChannelConfig] = load_channel_configs(config_path)
            self._pending_cmds: dict = {}
            self._debounce_timers: dict = {}
            # Réglages de l'onglet « Mesure » mémorisés à côté de channels_config.json.
            self.settings_path = Path(config_path).with_name("gui_settings.json")

            # État d'une série : armée (attend le signal) -> enregistrement -> terminée.
            self._armed = False
            self._recording = False
            self._config: series.SeriesConfig | None = None
            self._series_dir: Path | None = None      # série en cours d'enregistrement
            self._current_series: Path | None = None  # série affichée dans l'onglet Analyse
            self._opened: dict | None = None          # série ouverte depuis le disque
            self.theme_name = "clair"
            self._bridge = _Bridge()  # résultats du re-traitement (thread) -> thread UI
            self._bridge.done.connect(self._on_reprocess_done)
            self._bridge.integrity.connect(self._on_reprocess_integrity)
            self._bridge.failed.connect(self._on_reprocess_failed)

            self._build_plot()
            self._build_controls()
            self._build_experiment_panel()
            self._refresh_channel_names()
            self._build_analysis()
            self._build_tabs()
            self._build_status_bar()

            self.worker = AcquisitionWorker(
                ip, socket=socket, usb=usb, timeout_ms=timeout_ms, cmd_queue=self.cmd_queue
            )
            self.worker.connected.connect(self.on_connected)
            self.worker.connection_failed.connect(self.on_connection_failed)
            self.worker.waveform_ready.connect(self.on_waveform_ready)
            self.worker.acq_error.connect(self.on_acq_error)
            self.worker.capture_done.connect(self.on_capture_done)
            self.worker.command_error.connect(self.on_command_error)
            self.worker.series_progress.connect(self.on_series_progress)
            self.worker.series_done.connect(self.on_series_done)
            self.worker.plateau_ready.connect(self.on_plateau_ready)
            self.worker.plateau_error.connect(self.on_plateau_error)
            self.worker.plateau_summary.connect(self.on_plateau_summary)
            # Après la connexion des signaux du worker mais avant son démarrage :
            # les voies actives restaurées sont postées dans la file de commandes
            # comme un clic utilisateur.
            self._apply_settings(load_gui_settings(self.settings_path))
            self.worker.start()

        # -- construction UI ---------------------------------------------------
        def _build_plot(self) -> None:
            self.plot = pg.PlotWidget()
            plot_item = self.plot.getPlotItem()
            self.plot_item = plot_item
            plot_item.setLabel("bottom", "Temps", units="s")
            plot_item.setLabel("left", "Amplitude")
            self.legend = plot_item.addLegend()
            plot_item.showGrid(x=True, y=True, alpha=0.3)
            plot_item.enableAutoRange()
            self.plot.setToolTip(
                "Zoom molette, déplacement clic-gauche glissé.\n"
                "Clic droit > View All pour revenir à l'échelle automatique."
            )

            # Second axe Y (droite), utilisé quand deux unités distinctes sont
            # actives (ex. V à gauche, A à droite) -- cf. channel_config.axis_assignment.
            # Masqué par défaut ; _reassign_axes() l'affiche/masque selon les voies.
            self.vb_right = pg.ViewBox()
            plot_item.showAxis("right")
            plot_item.getAxis("right").linkToView(self.vb_right)
            self.vb_right.setXLink(plot_item)
            plot_item.scene().addItem(self.vb_right)

            def _sync_right_view():
                self.vb_right.setGeometry(plot_item.vb.sceneBoundingRect())
                self.vb_right.linkedViewChanged(plot_item.vb, self.vb_right.XAxis)

            plot_item.vb.sigResized.connect(_sync_right_view)
            _sync_right_view()
            plot_item.showAxis("right", False)

        def _reassign_axes(self) -> None:
            """Replace chaque courbe active dans le bon axe (V/A…) et rebâtit la légende.

            Appelé après tout changement d'unité ou de voie active
            (:func:`channel_config.axis_assignment`, même règle que le PNG
            statique dans ``plot.py``).
            """
            mapping, left_unit, right_unit = axis_assignment(self.configs, self.active_channels)

            self.plot_item.setLabel("left", "Amplitude", units=left_unit or "")
            if right_unit:
                self.plot_item.showAxis("right")
                self.plot_item.getAxis("right").setLabel("Amplitude", units=right_unit)
            else:
                self.plot_item.showAxis("right", False)

            self.legend.clear()
            for ch, curve in self.curves.items():
                target_vb = self.vb_right if mapping.get(ch) == "right" else self.plot_item.vb
                current_vb = curve.getViewBox()
                if current_vb is not target_vb:
                    if current_vb is not None:
                        current_vb.removeItem(curve)
                    target_vb.addItem(curve)
                self.legend.addItem(curve, self.configs[ch].display_name(ch))

        # -- listes déroulantes « libellé lisible / code SCPI » ------------------------
        @staticmethod
        def _coded_combo(items) -> "QtWidgets.QComboBox":
            """Combo affichant des libellés, portant les codes (``items`` : ``[(code, libellé)]``)."""
            combo = QtWidgets.QComboBox()
            for code, label in items:
                combo.addItem(label, code)
            # largeur raisonnable plutôt que celle du plus long libellé (colonnes étroites)
            combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(6)
            return combo

        @staticmethod
        def _select_code(combo, code, *, silent=False) -> None:
            """Sélectionne l'élément de code ``code`` (ignoré si vide ou inconnu)."""
            index = combo.findData(code) if code else -1
            if index < 0:
                return
            combo.blockSignals(silent)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)

        def _channel_text(self, ch: str) -> str:
            label = self.configs[ch].label
            return f"{ch} · {label}" if label else ch

        def _refresh_channel_names(self) -> None:
            """Noms de voies dans les listes (déclenchement, analyse U/I)."""
            for combo in (self.trig_src, self.u_combo, self.i_combo):
                for k in range(combo.count()):
                    combo.setItemText(k, self._channel_text(combo.itemData(k)))
            self._refresh_start_summary()

        def _build_controls(self) -> None:
            """Colonne « Scope » : pilotage de l'oscilloscope seulement (l'enregistrement
            est dans la colonne Expérience)."""
            panel = QtWidgets.QWidget()
            form = QtWidgets.QVBoxLayout(panel)

            # Acquisition
            acq_box = QtWidgets.QGroupBox("Acquisition")
            acq_row = QtWidgets.QHBoxLayout(acq_box)
            btn_run = QtWidgets.QPushButton("Lancer")
            btn_stop = QtWidgets.QPushButton("Figer")
            btn_autoset = QtWidgets.QPushButton("Réglage auto")
            btn_run.setToolTip("Acquisition continue : la courbe se rafraîchit en direct (SCPI : ARM).")
            btn_stop.setToolTip("Arrête l'acquisition et fige la dernière trame (SCPI : STOP).")
            btn_autoset.setToolTip(
                "Réglage automatique du scope (bouton « Auto Setup », SCPI : ASET) :\n"
                "calibres, base de temps et déclenchement. Utile si rien ne s'affiche."
            )
            btn_run.clicked.connect(lambda: self.cmd_queue.put(("run",)))
            btn_stop.clicked.connect(lambda: self.cmd_queue.put(("stop",)))
            btn_autoset.clicked.connect(lambda: self.cmd_queue.put(("autoset",)))
            for b in (btn_run, btn_stop, btn_autoset):
                acq_row.addWidget(b)
            form.addWidget(acq_box)

            # Voies : un tableau, une ligne par voie
            voies_box = QtWidgets.QGroupBox("Voies")
            grid = QtWidgets.QGridLayout(voies_box)
            headers = (("Afficher", "Coche pour lire la voie et afficher sa courbe (et sa trace sur le scope)."),
                       ("Nom", "Nom affiché (légende, exports CSV/PNG). Vide = nom de la voie."),
                       ("Calibre", "Volts par division à l'entrée du scope (SCPI : VDIV).\n"
                                   "Plus petit = zoom sur un petit signal ; plus grand si la courbe sort."),
                       ("Couplage", "DC = signal complet · AC = bloque le continu · 1 MΩ : sondes\n"
                                    "usuelles · 50 Ω : charges RF · Masse = entrée à la masse."),
                       ("Unité", "Unité de la grandeur mesurée (ex. A pour un courant via un shunt).\n"
                                 "Ne change pas la mesure du scope (toujours en V)."),
                       ("× Facteur", "Valeur affichée = volts lus × facteur.\n"
                                     "Ex. sonde de courant 100 mV/A -> 10. Laisser 1 pour du direct."))
            for col, (title, tip) in enumerate(headers):
                head = QtWidgets.QLabel(title)
                head.setProperty("role", "muted")
                head.setToolTip(tip)
                grid.addWidget(head, 0, col)
            self.channel_checks, self.vdiv_combos, self.coupling_combos = {}, {}, {}
            for row, ch in enumerate(CHANNELS, start=1):
                cfg = self.configs[ch]
                check = QtWidgets.QCheckBox(ch)
                name_edit = QtWidgets.QLineEdit(cfg.label)
                name_edit.setPlaceholderText(ch)
                vdiv = self._coded_combo((v, vdiv_label(v)) for v in VDIV_VALUES)
                vdiv.setMinimumContentsLength(9)  # « 500 mV/div » entier
                coupling = self._coded_combo(COUPLING_LABELS.items())
                unit_combo = QtWidgets.QComboBox()
                unit_combo.setEditable(True)
                unit_combo.addItems(DEFAULT_UNITS)
                unit_combo.setCurrentText(cfg.unit)
                factor_edit = QtWidgets.QLineEdit(str(cfg.factor))
                factor_edit.setValidator(QtGui.QDoubleValidator(-1e12, 1e12, 6, factor_edit))
                factor_edit.setMaximumWidth(60)
                name_edit.setMinimumWidth(80)
                unit_combo.setMaximumWidth(70)
                for col, w in enumerate((check, name_edit, vdiv, coupling, unit_combo, factor_edit)):
                    w.setToolTip(headers[col][1])
                    grid.addWidget(w, row, col)

                self.channel_checks[ch] = check
                self.vdiv_combos[ch] = vdiv
                self.coupling_combos[ch] = coupling
                check.toggled.connect(lambda on, c=ch: self._on_channel_toggled(c, on))
                name_edit.editingFinished.connect(
                    lambda c=ch, w=name_edit: self._on_name_changed(c, w.text())
                )
                vdiv.currentIndexChanged.connect(
                    lambda _i, c=ch, w=vdiv: self._debounced_put(("vdiv", c), ("vdiv", c, w.currentData()))
                )
                coupling.currentIndexChanged.connect(
                    lambda _i, c=ch, w=coupling: self._debounced_put(
                        ("coupling", c), ("coupling", c, w.currentData()))
                )
                unit_combo.currentTextChanged.connect(lambda v, c=ch: self._on_unit_changed(c, v))
                factor_edit.editingFinished.connect(
                    lambda c=ch, w=factor_edit: self._on_factor_changed(c, w.text())
                )
            grid.setColumnStretch(1, 1)
            form.addWidget(voies_box)

            # Base de temps et affichage
            time_box = QtWidgets.QGroupBox("Base de temps et affichage")
            tf = QtWidgets.QFormLayout(time_box)
            tdiv = self._coded_combo((v, tdiv_label(v)) for v in TDIV_VALUES)
            self._select_code(tdiv, "1MS")
            tdiv.setToolTip(
                "Durée par division horizontale (SCPI : TDIV) : plus petite pour un\n"
                "phénomène rapide, plus grande pour voir plusieurs périodes."
            )
            tdiv.currentIndexChanged.connect(
                lambda _i: self._debounced_put("timebase", ("timebase", tdiv.currentData()))
            )
            self.tdiv_combo = tdiv
            # Points dessinés : décimation d'affichage côté client, PAS WFSU NP — le fetch
            # récupère toujours toute la mémoire (NP=0) ; voir docs/scpi-reference.md et
            # docs/architecture.md (WFSU NP = zoom sur le début du buffer, abandonné le
            # 2026-07-08).
            self.points_combo = QtWidgets.QComboBox()
            self.points_combo.setEditable(True)
            self.points_combo.addItems(DISPLAY_POINTS_VALUES)
            self.points_combo.setCurrentText(DISPLAY_POINTS_DEFAULT)
            self.points_combo.setToolTip(
                "Nombre max de points dessinés par courbe (et par capture de série).\n"
                "Ne change que le rendu, jamais la durée affichée ; la capture\n"
                "ponctuelle exporte toujours toutes les données brutes."
            )
            self.points_combo.setValidator(QtGui.QIntValidator(1, 100_000_000, self.points_combo))
            self.display_max_points = int(DISPLAY_POINTS_DEFAULT)
            self.points_combo.lineEdit().editingFinished.connect(self._on_points_entered)
            self.points_combo.activated.connect(self._on_points_entered)
            tf.addRow("Base de temps", tdiv)
            tf.addRow("Points dessinés", self.points_combo)
            form.addWidget(time_box)

            # Déclenchement (aussi utilisé par le départ « Au seuil » d'une série)
            trig_box = QtWidgets.QGroupBox("Déclenchement")
            trig_box.setToolTip(
                "Le scope n'acquiert que lorsque la voie choisie franchit le niveau dans le\n"
                "sens choisi. Aussi utilisé par le départ « Au seuil » d'une série."
            )
            gf = QtWidgets.QFormLayout(trig_box)
            trig_src = self._coded_combo((ch, ch) for ch in CHANNELS)
            trig_src.setToolTip("Voie surveillée : elle doit recevoir un signal (SCPI : TRSE EDGE,SR).")
            trig_slope = self._coded_combo(SLOPE_LABELS.items())
            trig_slope.setToolTip("Sens du franchissement du niveau (SCPI : TRSL).")
            trig_level = QtWidgets.QLineEdit("1")
            trig_level.setValidator(QtGui.QRegularExpressionValidator(
                QtCore.QRegularExpression(r"\s*-?\d*[.,]?\d*\s*[Vv]?\s*"), trig_level))
            trig_level.setToolTip(
                "Niveau en volts À L'ENTRÉE DU SCOPE (avant le facteur de la voie),\n"
                "ex. 1 ou 0,5. Valider avec Entrée (SCPI : TRLV)."
            )
            level_row = QtWidgets.QHBoxLayout()
            level_row.addWidget(trig_level)
            level_row.addWidget(QtWidgets.QLabel("V (entrée scope)"))
            trig_src.currentIndexChanged.connect(
                lambda _i: self._debounced_put("trigger_source", ("trigger_source", trig_src.currentData()))
            )
            trig_slope.currentIndexChanged.connect(
                lambda _i: self._debounced_put(
                    "trigger_slope", ("trigger_slope", trig_src.currentData(), trig_slope.currentData()))
            )
            trig_level.returnPressed.connect(self._on_trigger_level_entered)
            for w in (trig_src, trig_slope):
                w.currentIndexChanged.connect(lambda _i: self._refresh_start_summary())
            trig_level.textChanged.connect(lambda _t: self._refresh_start_summary())
            gf.addRow("Voie", trig_src)
            gf.addRow("Front", trig_slope)
            gf.addRow("Niveau", level_row)
            self.trig_src, self.trig_slope, self.trig_level = trig_src, trig_slope, trig_level
            form.addWidget(trig_box)

            # Capture ponctuelle
            cap_box = QtWidgets.QGroupBox("Capture ponctuelle")
            cap_row = QtWidgets.QHBoxLayout(cap_box)
            self.png_check = QtWidgets.QCheckBox("avec image PNG")
            self.png_check.setToolTip("Génère en plus une image PNG des courbes.")
            btn_capture = QtWidgets.QPushButton("Capturer maintenant")
            btn_capture.setToolTip(
                "Lit une fois les voies cochées (toutes les données brutes) et écrit\n"
                "CSV + .npy horodatés dans le dossier des séries (colonne Expérience).\n"
                "Si aucune voie n'est cochée, capture C1."
            )
            btn_capture.clicked.connect(self._on_capture_clicked)
            cap_row.addWidget(self.png_check)
            cap_row.addStretch(1)
            cap_row.addWidget(btn_capture)
            form.addWidget(cap_box)

            # Gelés pendant une série active : conflit avec la série (déclenchement
            # reconfiguré au départ au seuil, capture concurrente au fetch de la série).
            # Réactivés dans on_series_done.
            self._series_lockable = [btn_run, btn_stop, btn_autoset, trig_src, trig_slope, trig_level, btn_capture]

            form.addStretch(1)
            # Défilable : le panneau partage l'onglet avec le live.
            self.controls_panel = QtWidgets.QScrollArea()
            self.controls_panel.setWidgetResizable(True)
            self.controls_panel.setWidget(panel)

        def _on_trigger_level_entered(self) -> None:
            try:
                level = trigger_level_scpi(self.trig_level.text())
            except ValueError:
                self.status.showMessage("Déclenchement : niveau invalide (un nombre en volts, ex. 1 ou 0,5)")
                return
            self._debounced_put("trigger_level", ("trigger_level", self.trig_src.currentData(), level))

        def _build_recording_box(self) -> "QtWidgets.QGroupBox":
            """Cadre « Enregistrement » (colonne Expérience) : cadence, durée, départ,
            voies analysées. Même logique que ``scope series`` en CLI (scope/series.py) :
            une capture = instantané décimé (« Points dessinés »), pas la mémoire brute."""
            box = QtWidgets.QGroupBox("Enregistrement")
            f = QtWidgets.QFormLayout(box)

            self.series_rate_edit = QtWidgets.QLineEdit("1")
            self.series_rate_edit.setMaximumWidth(60)
            self.series_rate_edit.setToolTip("Nombre de captures par unité de temps.")
            self.series_per_combo = self._coded_combo(PER_UNIT_LABELS.items())
            self._select_code(self.series_per_combo, "minute")
            rate_row = QtWidgets.QHBoxLayout()
            rate_row.addWidget(self.series_rate_edit)
            rate_row.addWidget(QtWidgets.QLabel("capture(s) par"))
            rate_row.addWidget(self.series_per_combo)
            rate_row.addStretch(1)
            f.addRow("Cadence", rate_row)

            self.series_dur_edit = QtWidgets.QLineEdit("60s")
            self.series_dur_edit.setPlaceholderText("ex. 30m, 2h, 90s")
            self.series_dur_edit.setToolTip("Durée maximale : 30m, 2h, 90s (un nombre seul = secondes).")
            f.addRow("Durée max", self.series_dur_edit)

            # Départ : boutons radio, seuls les champs du mode choisi sont visibles
            start_col = QtWidgets.QVBoxLayout()
            self.start_mode_group = QtWidgets.QButtonGroup(box)
            self.start_mode_buttons = {}
            tips = {"threshold": "L'enregistrement démarre quand le signal franchit le seuil de la\n"
                                 "section Scope › Déclenchement (rien n'est enregistré avant).",
                    "now": "L'enregistrement démarre dès l'armement.",
                    "countdown": "L'enregistrement démarre après le délai (temps de préparer le montage)."}
            for code, label in START_MODE_LABELS.items():
                radio = QtWidgets.QRadioButton(label)
                radio.setToolTip(tips[code])
                self.start_mode_group.addButton(radio)
                self.start_mode_buttons[code] = radio
                start_col.addWidget(radio)
                radio.toggled.connect(lambda on, c=code: on and self._on_start_mode_changed(c))

            self.start_thr_box = QtWidgets.QWidget()
            tl = QtWidgets.QFormLayout(self.start_thr_box)
            tl.setContentsMargins(22, 0, 0, 0)
            self.start_thr_summary = QtWidgets.QLabel()
            self.start_thr_summary.setProperty("role", "muted")
            self.start_thr_summary.setWordWrap(True)
            self.start_timeout_edit = QtWidgets.QLineEdit("30")
            self.start_timeout_edit.setMaximumWidth(60)
            self.start_timeout_edit.setToolTip("Sans franchissement du seuil dans ce délai, rien n'est enregistré.")
            tl.addRow(self.start_thr_summary)
            tl.addRow("Attente max (s)", self.start_timeout_edit)
            start_col.addWidget(self.start_thr_box)

            self.start_delay_box = QtWidgets.QWidget()
            dl = QtWidgets.QFormLayout(self.start_delay_box)
            dl.setContentsMargins(22, 0, 0, 0)
            self.series_delay_edit = QtWidgets.QLineEdit("5")
            self.series_delay_edit.setMaximumWidth(60)
            dl.addRow("Délai (s)", self.series_delay_edit)
            start_col.addWidget(self.start_delay_box)
            f.addRow("Départ", start_col)

            # Voies analysées (extraction des plateaux, onglet Analyse)
            self.u_combo = self._coded_combo((ch, ch) for ch in CHANNELS)
            self.i_combo = self._coded_combo((ch, ch) for ch in CHANNELS)
            ui_tip = ("Voies tension (U) et courant (I) de l'extraction des plateaux à chaque\n"
                      "capture (onglet Analyse). Elles doivent être cochées dans Scope › Voies ;\n"
                      "unités converties en V/A (mA -> A…). Sinon la série tourne sans analyse.")
            ui_row = QtWidgets.QHBoxLayout()
            for title, combo in (("U", self.u_combo), ("I", self.i_combo)):
                combo.setToolTip(ui_tip)
                ui_row.addWidget(QtWidgets.QLabel(title))
                ui_row.addWidget(combo, 1)
            f.addRow("Analyse", ui_row)

            self._recording_lockable = [self.series_rate_edit, self.series_per_combo, self.series_dur_edit,
                                        *self.start_mode_buttons.values(), self.start_timeout_edit,
                                        self.series_delay_edit, self.u_combo, self.i_combo]
            self.start_mode_buttons["threshold"].setChecked(True)
            return box

        def _start_mode(self) -> str:
            return next(code for code, radio in self.start_mode_buttons.items() if radio.isChecked())

        def _on_start_mode_changed(self, code: str) -> None:
            self.start_thr_box.setVisible(code == "threshold")
            self.start_delay_box.setVisible(code == "countdown")
            self._refresh_start_summary()

        def _refresh_start_summary(self) -> None:
            if not hasattr(self, "start_thr_summary"):
                return  # colonne Expérience pas encore construite
            try:
                level = trigger_level_scpi(self.trig_level.text())[:-1] + " V"
            except ValueError:
                level = "niveau invalide"
            self.start_thr_summary.setText(
                f"Seuil : {self.trig_src.currentText()} · {self.trig_slope.currentText().lower()} · "
                f"{level} (entrée scope) — réglé dans Scope › Déclenchement"
            )

        def _build_experiment_panel(self) -> None:
            """Colonne « Expérience » : identifiant, fiche, armement de la série."""
            FicheForm, _ = gui_experiment.widgets()
            panel = QtWidgets.QWidget()
            v = QtWidgets.QVBoxLayout(panel)

            id_box = QtWidgets.QGroupBox("Identifiant de l'essai")
            f = QtWidgets.QFormLayout(id_box)
            self.prefix_edit = QtWidgets.QLineEdit("PEO")
            self.prefix_edit.setToolTip("Préfixe de l'ID : lettres, chiffres, tirets (ex. PEO, PEO-Ti).")
            self.outdir_edit = QtWidgets.QLineEdit("captures")
            self.outdir_edit.setToolTip("Dossier des séries (et des captures ponctuelles).")
            btn_browse = QtWidgets.QPushButton("…")
            btn_browse.setProperty("kind", "ghost")
            btn_browse.setObjectName("browse")
            btn_browse.setFixedWidth(40)
            btn_browse.clicked.connect(self._on_browse_outdir)
            out_row = QtWidgets.QHBoxLayout()
            out_row.addWidget(self.outdir_edit)
            out_row.addWidget(btn_browse)
            self.id_label = QtWidgets.QLabel("—")
            self.id_label.setObjectName("seriesId")
            self.id_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            self.id_state = QtWidgets.QLabel("")
            self.id_state.setProperty("role", "muted")
            self.id_state.setWordWrap(True)
            f.addRow("Préfixe", self.prefix_edit)
            f.addRow("Dossier", out_row)
            f.addRow("ID", self.id_label)
            f.addRow("", self.id_state)
            v.addWidget(id_box)
            self._id_lockable = [self.prefix_edit, self.outdir_edit, btn_browse]
            self.prefix_edit.textChanged.connect(lambda _t: self._refresh_next_id())
            self.outdir_edit.textChanged.connect(lambda _t: self._refresh_next_id())

            self.fiche_form = FicheForm()
            self.fiche_form.edited.connect(self._on_fiche_edited)
            v.addWidget(self.fiche_form)
            v.addWidget(self._build_recording_box())

            btn_row = QtWidgets.QHBoxLayout()
            self.btn_series_start = QtWidgets.QPushButton("Armer la série")
            self.btn_series_start.setProperty("kind", "primary")
            self.btn_series_start.setToolTip(
                "Attribue l'ID et prépare la série (cadre Enregistrement ci-dessus).\n"
                "En départ « Au seuil », l'enregistrement démarre à la détection\n"
                "du signal de l'alimentation. La fiche reste modifiable pendant l'essai."
            )
            self.btn_series_stop = QtWidgets.QPushButton("Arrêter")
            self.btn_series_stop.setProperty("kind", "danger")
            self.btn_series_stop.setEnabled(False)
            self.btn_series_start.clicked.connect(self._on_series_start)
            self.btn_series_stop.clicked.connect(lambda: self.cmd_queue.put(("series_stop",)))
            btn_row.addWidget(self.btn_series_start, 2)
            btn_row.addWidget(self.btn_series_stop, 1)
            v.addLayout(btn_row)
            v.addStretch(1)

            self.experiment_panel = QtWidgets.QScrollArea()
            self.experiment_panel.setWidgetResizable(True)
            self.experiment_panel.setWidget(panel)
            # Modifications de fiche pendant l'enregistrement : écrites (journalisées)
            # 1,5 s après la dernière frappe, pas à chaque caractère.
            self._fiche_push_timer = QtCore.QTimer(self)
            self._fiche_push_timer.setSingleShot(True)
            self._fiche_push_timer.timeout.connect(self._push_fiche)

        def _build_analysis(self) -> None:
            """Onglet « Analyse » : dernière capture de série avec ses plateaux
            surlignés (gauche) | U, I, f des plateaux en fonction de t (droite)."""
            # Gauche : U (axe gauche) et I (axe droit), même schéma que _build_plot.
            self.an_plot = pg.PlotWidget(title="Dernière capture de la série")
            an_item = self.an_plot.getPlotItem()
            an_item.setLabel("bottom", "Temps", units="s")
            an_item.setLabel("left", "U", units="V")
            an_item.showGrid(x=True, y=True, alpha=0.3)
            self.an_u_curve = an_item.plot(pen=pg.mkPen("#1f77b4"))
            self.an_vb_right = pg.ViewBox()
            an_item.showAxis("right")
            an_item.getAxis("right").linkToView(self.an_vb_right)
            an_item.getAxis("right").setLabel("I", units="A")
            self.an_vb_right.setXLink(an_item)
            an_item.scene().addItem(self.an_vb_right)
            self.an_i_curve = pg.PlotDataItem(pen=pg.mkPen("#ff7f0e"))
            self.an_vb_right.addItem(self.an_i_curve)

            def _sync_an_right():
                self.an_vb_right.setGeometry(an_item.vb.sceneBoundingRect())
                self.an_vb_right.linkedViewChanged(an_item.vb, self.an_vb_right.XAxis)

            an_item.vb.sigResized.connect(_sync_an_right)
            self.an_item = an_item
            self.an_regions: list = []

            # Droite : U, I, f vs t (un point par capture, médiane ± σ des plateaux).
            self.evo_widget = pg.GraphicsLayoutWidget()
            self.evo_plots = {}
            self.evo_items = {}
            for row_idx, (q, unit) in enumerate((("U", "V"), ("I", "A"), ("f", "Hz"))):
                p = self.evo_widget.addPlot(row=row_idx, col=0)
                p.setLabel("left", q, units=unit)
                p.showGrid(x=True, y=True, alpha=0.3)
                p.addLegend()
                if row_idx:
                    p.setXLink(self.evo_plots["U"])
                self.evo_plots[q] = p
            self.evo_plots["f"].setLabel("bottom", "t", units="s")
            for q in ("U", "I"):
                for pol, color, symbol, name in (("pos", "#2ca02c", "o", "plateau +"),
                                                 ("neg", "#d62728", "s", "plateau −")):
                    curve = self.evo_plots[q].plot(
                        pen=pg.mkPen(color), symbol=symbol, symbolSize=6,
                        symbolBrush=color, connect="finite", name=name,
                    )
                    err = pg.ErrorBarItem(pen=pg.mkPen(color), beam=0)
                    self.evo_plots[q].addItem(err)
                    self.evo_items[(q, pol)] = (curve, err)
            self.evo_items[("f", "fronts")] = (self.evo_plots["f"].plot(
                pen=pg.mkPen("#1f77b4"), symbol="o", symbolSize=6, connect="finite", name="fronts"), None)
            self.evo_items[("f", "fft")] = (self.evo_plots["f"].plot(
                pen=None, symbol="x", symbolSize=8, symbolBrush="#ff7f0e", name="FFT"), None)

            # En-tête : série affichée + actions (ouvrir, fiche, re-traiter).
            self.analysis_bar = QtWidgets.QWidget()
            bar = QtWidgets.QHBoxLayout(self.analysis_bar)
            bar.setContentsMargins(8, 6, 8, 6)
            self.series_label = QtWidgets.QLabel("Aucune série — « Ouvrir une série… » ou armer une série")
            self.series_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            self.capture_spin = QtWidgets.QSpinBox()
            self.capture_spin.setPrefix("capture ")
            self.capture_spin.setToolTip("Parcourir les captures de la série ouverte (avec leurs plateaux).")
            self.capture_spin.valueChanged.connect(self._on_capture_selected)
            self.capture_spin.hide()
            self.btn_open = QtWidgets.QPushButton("Ouvrir une série…")
            self.btn_open.setProperty("kind", "ghost")
            self.btn_open.clicked.connect(self._on_open_series)
            self.btn_fiche = QtWidgets.QPushButton("Fiche…")
            self.btn_fiche.setProperty("kind", "ghost")
            self.btn_fiche.setToolTip("Fiche, résultats post-essai, pièces jointes, historique, traçabilité.")
            self.btn_fiche.clicked.connect(self._on_fiche_dialog)
            self.btn_reprocess = QtWidgets.QPushButton("Re-traiter")
            self.btn_reprocess.setProperty("kind", "primary")
            self.btn_reprocess.setToolTip(
                "Vérifie les empreintes des données brutes puis relance l'extraction des\n"
                "plateaux avec l'algorithme actuel. Régénère CSV/PNG d'analyse dans le\n"
                "dossier de la série ; les données brutes ne sont jamais modifiées."
            )
            self.btn_reprocess.clicked.connect(lambda: self._on_reprocess(False))
            for b in (self.btn_fiche, self.btn_reprocess):
                b.setEnabled(False)
            bar.addWidget(self.series_label, 1)
            bar.addWidget(self.capture_spin)
            bar.addWidget(self.btn_open)
            bar.addWidget(self.btn_fiche)
            bar.addWidget(self.btn_reprocess)
            self._reset_analysis()

        def _build_tabs(self) -> None:
            central = QtWidgets.QWidget()
            v = QtWidgets.QVBoxLayout(central)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)

            header = QtWidgets.QFrame()
            header.setObjectName("header")
            h = QtWidgets.QHBoxLayout(header)
            h.setContentsMargins(16, 8, 16, 8)
            self.logo = QtWidgets.QLabel()
            title = QtWidgets.QLabel("Oscilloscope PEO — acquisition et traçabilité")
            title.setObjectName("appTitle")
            subtitle = QtWidgets.QLabel(f"SDS1204X-E · {ip}")
            subtitle.setProperty("role", "muted")
            self.btn_theme = QtWidgets.QPushButton()
            self.btn_theme.setProperty("kind", "ghost")
            self.btn_theme.setToolTip("Basculer thème clair / sombre (mémorisé)")
            self.btn_theme.clicked.connect(lambda: self.apply_theme(theme.other_theme(self.theme_name)))
            h.addWidget(self.logo)
            h.addSpacing(16)
            h.addWidget(title)
            h.addSpacing(12)
            h.addWidget(subtitle)
            h.addStretch(1)
            h.addWidget(self.btn_theme)
            v.addWidget(header)

            self.banner = QtWidgets.QLabel()
            self.banner.setObjectName("banner")
            self.banner.setWordWrap(True)
            self.banner.hide()
            banner_box = QtWidgets.QWidget()
            bl = QtWidgets.QVBoxLayout(banner_box)
            bl.setContentsMargins(12, 8, 12, 0)
            bl.addWidget(self.banner)
            v.addWidget(banner_box)

            self.tabs = QtWidgets.QTabWidget()
            mesure = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            mesure.addWidget(self.experiment_panel)
            mesure.addWidget(self.controls_panel)
            mesure.addWidget(self.plot)
            mesure.setStretchFactor(2, 1)
            mesure.setSizes([390, 560, 550])
            analyse_page = QtWidgets.QWidget()
            al = QtWidgets.QVBoxLayout(analyse_page)
            al.setContentsMargins(0, 0, 0, 0)
            al.addWidget(self.analysis_bar)
            analyse = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            analyse.addWidget(self.an_plot)
            analyse.addWidget(self.evo_widget)
            al.addWidget(analyse, 1)
            self.tabs.addTab(mesure, "Mesure")
            self.tabs.addTab(analyse_page, "Analyse")
            tabs_box = QtWidgets.QWidget()
            tl = QtWidgets.QVBoxLayout(tabs_box)
            tl.setContentsMargins(12, 8, 12, 8)
            tl.addWidget(self.tabs)
            v.addWidget(tabs_box, 1)
            self.setCentralWidget(central)

        # -- thème -------------------------------------------------------------------
        def apply_theme(self, name: str) -> None:
            """Charte Materianova : QSS de l'application + fonds/axes des graphes + logo."""
            name = name if name in theme.THEMES else "clair"
            self.theme_name = name
            pal = theme.PALETTES[name]
            QtWidgets.QApplication.instance().setStyleSheet(theme.qss(name))
            self._plot_fg = pal["plot_fg"]
            for widget in (self.plot, self.an_plot, self.evo_widget):
                widget.setBackground(pal["plot_bg"])
            for item in (self.plot_item, self.an_item, *self.evo_plots.values()):
                for side in ("left", "bottom", "right"):
                    axis = item.getAxis(side)
                    axis.setPen(pal["plot_fg"])
                    axis.setTextPen(pal["plot_fg"])
            self.btn_theme.setText("☾  Sombre" if name == "clair" else "☀  Clair")
            self._load_logo(name)

        def _load_logo(self, name: str) -> None:
            data = theme.logo_svg(name)
            try:
                from pyqtgraph.Qt import QtSvg

                renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(data))
                size = renderer.defaultSize()
                height = 36
                width = int(size.width() * height / max(size.height(), 1))
                ratio = self.devicePixelRatioF()
                pix = QtGui.QPixmap(int(width * ratio), int(height * ratio))
                pix.setDevicePixelRatio(ratio)
                pix.fill(QtCore.Qt.GlobalColor.transparent)
                painter = QtGui.QPainter(pix)
                renderer.render(painter, QtCore.QRectF(0, 0, width, height))
                painter.end()
                self.logo.setPixmap(pix)
            except Exception:  # noqa: BLE001 — logo absent / QtSvg indisponible : texte
                self.logo.setText("materianova")

        def _build_status_bar(self) -> None:
            self.status = self.statusBar()
            self.status.showMessage(f"Connexion à {ip}…")

        # -- actions utilisateur -------------------------------------------------
        def _debounced_put(self, key, cmd: tuple) -> None:
            """Envoie ``cmd`` au scope après ``DEBOUNCE_MS`` d'inactivité sur ``key``.

            Anti-rebond : plusieurs changements coup sur coup sur un même réglage
            (molette sur un combo, glissade rapide) ne doivent envoyer que le
            **dernier** au scope, pas chacun. Cause identifiée sur matériel d'une
            désynchronisation, voire d'un blocage réseau du scope, quand des
            réglages (notamment ``TDIV``) sont envoyés trop vite d'affilée (cf.
            ``docs/usage.md`` § Dépannage). ``key`` isole le rebond par réglage
            (ex. ``("vdiv", "C1")``) : changer C1 ne repousse pas l'envoi de C2.
            """
            self._pending_cmds[key] = cmd
            timer = self._debounce_timers.get(key)
            if timer is None:
                timer = QtCore.QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda k=key: self._flush_debounced(k))
                self._debounce_timers[key] = timer
            timer.start(DEBOUNCE_MS)

        def _flush_debounced(self, key) -> None:
            cmd = self._pending_cmds.pop(key, None)
            if cmd is not None:
                self.cmd_queue.put(cmd)

        def _on_channel_toggled(self, ch: str, on: bool) -> None:
            if on:
                self.active_channels.add(ch)
                pen = pg.intColor(CHANNELS.index(ch), hues=len(CHANNELS))
                self.curves[ch] = pg.PlotDataItem(pen=pen)
            else:
                self.active_channels.discard(ch)
                curve = self.curves.pop(ch, None)
                if curve is not None:
                    vb = curve.getViewBox()
                    if vb is not None:
                        vb.removeItem(curve)
            self._reassign_axes()
            self.cmd_queue.put(("channels", frozenset(self.active_channels)))
            self.cmd_queue.put(("enable", ch, on))

        def _on_name_changed(self, ch: str, text: str) -> None:
            self.configs[ch].label = text.strip()
            self._after_config_change()
            self._refresh_channel_names()

        def _on_unit_changed(self, ch: str, text: str) -> None:
            self.configs[ch].unit = text.strip() or "V"
            self._after_config_change()

        def _on_factor_changed(self, ch: str, text: str) -> None:
            try:
                factor = float(text)
            except ValueError:
                return  # champ invalide (vide, en cours de saisie…) : on ignore
            self.configs[ch].factor = factor
            self._after_config_change()

        def _after_config_change(self) -> None:
            save_channel_configs(self.configs, self.config_path)
            self._reassign_axes()

        def _on_capture_clicked(self) -> None:
            channels = sorted(self.active_channels) or ["C1"]
            outdir = self.outdir_edit.text() or "captures"
            configs_snapshot = {
                ch: dataclasses.replace(cfg) for ch, cfg in self.configs.items()
            }
            self.cmd_queue.put(
                ("capture", channels, outdir, self.png_check.isChecked(), configs_snapshot)
            )

        def _on_browse_outdir(self) -> None:
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Dossier des séries", self.outdir_edit.text())
            if path:
                self.outdir_edit.setText(path)

        def _refresh_next_id(self) -> None:
            """ID proposé pour le prochain armement (figé seulement à l'armement)."""
            if self._armed or self._recording:
                return
            try:
                prefix = experiment.validate_prefix(self.prefix_edit.text())
            except ValueError as exc:
                self.id_label.setText("—")
                self.id_state.setText(str(exc))
                return
            outdir = self.outdir_edit.text().strip() or "captures"
            self.id_label.setText(experiment.next_id(outdir, prefix, date.today()))
            self.id_state.setText("prochain identifiant — attribué et figé à l'armement")

        def _on_series_start(self) -> None:
            try:
                prefix = experiment.validate_prefix(self.prefix_edit.text())
            except ValueError as exc:
                QtWidgets.QMessageBox.warning(self, "Préfixe invalide", str(exc))
                return
            outdir = self.outdir_edit.text().strip() or "captures"
            exp_id = experiment.next_id(outdir, prefix, date.today())
            mode = self._start_mode()
            threshold = None
            if mode == "threshold":
                try:
                    threshold = {
                        "channel": self.trig_src.currentData(),
                        "level": trigger_level_scpi(self.trig_level.text()),
                        "slope": self.trig_slope.currentData(),
                        "timeout_s": float(self.start_timeout_edit.text()),
                    }
                except ValueError:
                    self.status.showMessage(
                        "Série : niveau de déclenchement ou attente max invalide (Scope › Déclenchement)")
                    return
            try:
                configs_snapshot = {
                    ch: dataclasses.replace(cfg) for ch, cfg in self.configs.items()
                }
                config = series.SeriesConfig(
                    experiment_id=exp_id,
                    channels=sorted(self.active_channels) or ["C1"],
                    outdir=outdir,
                    rate=float(self.series_rate_edit.text()),
                    per_seconds=series.PER_UNIT_SECONDS[self.series_per_combo.currentData()],
                    duration_max=series.parse_duration(self.series_dur_edit.text()),
                    start_mode=mode,
                    delay_s=float(self.series_delay_edit.text() or 0),
                    threshold=threshold,
                    points=self.display_max_points,
                    configs=configs_snapshot,
                    fiche=self.fiche_form.get_fiche(),
                    armed_at=experiment.now_iso(),
                )
            except ValueError as exc:
                self.status.showMessage(f"Série : réglage invalide ({exc})")
                return

            # Extraction des plateaux seulement si U et I font partie des voies capturées.
            u, i = self.u_combo.currentData(), self.i_combo.currentData()
            analysed = u in config.channels and i in config.channels and u != i
            if analysed:
                config.u_channel, config.i_channel = u, i
            self._reset_analysis()
            self._opened = None
            self.capture_spin.hide()
            save_gui_settings(self._collect_settings(), self.settings_path)

            self._config = config
            self._armed = True
            self.id_label.setText(exp_id)
            self.id_state.setText("série armée — en attente du démarrage (signal)")
            self.cmd_queue.put(("series_start", config))
            self.btn_series_start.setEnabled(False)
            self.btn_series_stop.setEnabled(True)
            for w in self._series_lockable + self._recording_lockable + self._id_lockable + [self.btn_open]:
                w.setEnabled(False)
            self._update_alert()
            self.status.showMessage(
                f"Série « {config.experiment_id} » armée…"
                + ("" if analysed else f" (sans analyse des plateaux : cocher {u} et {i}, distinctes)")
            )

        # -- réglages mémorisés ----------------------------------------------------
        def _collect_settings(self) -> dict:
            return {
                "tab": self.tabs.currentIndex(),
                "active_channels": sorted(self.active_channels),
                "vdiv": {ch: c.currentData() for ch, c in self.vdiv_combos.items()},
                "coupling": {ch: c.currentData() for ch, c in self.coupling_combos.items()},
                "tdiv": self.tdiv_combo.currentData(),
                "points": str(self.display_max_points),
                "trig_src": self.trig_src.currentData(),
                "trig_slope": self.trig_slope.currentData(),
                "trig_level": self.trig_level.text(),
                "outdir": self.outdir_edit.text(),
                "png": self.png_check.isChecked(),
                "id_prefix": self.prefix_edit.text(),
                "fiche": self.fiche_form.get_fiche(),
                "theme": self.theme_name,
                "series_rate": self.series_rate_edit.text(),
                "series_per": self.series_per_combo.currentData(),
                "series_duration": self.series_dur_edit.text(),
                "start_mode": self._start_mode(),
                "series_delay": self.series_delay_edit.text(),
                "start_timeout": self.start_timeout_edit.text(),
                "analysis_u": self.u_combo.currentData(),
                "analysis_i": self.i_combo.currentData(),
            }

        def _apply_settings(self, st: dict) -> None:
            """Restaure les widgets. Les réglages scope (vdiv, couplage, timebase,
            trigger) sont affichés **sans** être renvoyés au scope (signaux
            bloqués) : pas de rafale SCPI au démarrage (cf. DEBOUNCE_MS). Seules
            les voies cochées passent par le chemin normal (_on_channel_toggled),
            nécessaire pour que le live les lise."""

            set_combo = self._select_code  # combos : codes SCPI mémorisés
            for ch in CHANNELS:
                set_combo(self.vdiv_combos[ch], st["vdiv"].get(ch, ""), silent=True)
                set_combo(self.coupling_combos[ch], st["coupling"].get(ch, ""), silent=True)
            set_combo(self.tdiv_combo, st["tdiv"], silent=True)
            set_combo(self.trig_src, st["trig_src"], silent=True)
            set_combo(self.trig_slope, st["trig_slope"], silent=True)
            try:  # ancien format « 1.0V » accepté, affiché sans l'unité
                self.trig_level.setText(trigger_level_scpi(st["trig_level"])[:-1])
            except ValueError:
                pass
            self.points_combo.setCurrentText(st["points"])
            self._on_points_entered()
            self.outdir_edit.setText(st["outdir"])
            self.png_check.setChecked(st["png"])
            self.prefix_edit.setText(st["id_prefix"])
            # Pré-remplissage : tout sauf l'ID d'échantillon et les notes (cf. experiment.prefill).
            self.fiche_form.set_fiche(experiment.prefill(st["fiche"]))
            self.fiche_form.set_tag_suggestions(experiment.collect_tags(st["outdir"]))
            self.apply_theme(st["theme"])
            self._refresh_next_id()
            self.series_rate_edit.setText(st["series_rate"])
            set_combo(self.series_per_combo, st["series_per"])
            self.series_dur_edit.setText(st["series_duration"])
            self.start_mode_buttons.get(st["start_mode"], self.start_mode_buttons["threshold"]).setChecked(True)
            self.series_delay_edit.setText(st["series_delay"])
            self.start_timeout_edit.setText(st["start_timeout"])
            set_combo(self.u_combo, st["analysis_u"])
            set_combo(self.i_combo, st["analysis_i"])
            self._refresh_start_summary()
            for ch in st["active_channels"]:
                if ch in self.channel_checks:
                    self.channel_checks[ch].setChecked(True)
            self.tabs.setCurrentIndex(st["tab"])

        # -- onglet Analyse ----------------------------------------------------------
        def _reset_analysis(self) -> None:
            self._evo = {k: [] for k in ("t", "U_med_pos", "U_std_pos", "U_med_neg", "U_std_neg",
                                         "I_med_pos", "I_std_pos", "I_med_neg", "I_std_neg",
                                         "freq_Hz", "freq_fft_Hz")}
            for curve, err in self.evo_items.values():
                curve.setData([], [])
                if err is not None:
                    err.setData(x=np.array([]), y=np.array([]), height=np.array([]))
            self.an_u_curve.setData([], [])
            self.an_i_curve.setData([], [])
            for region in self.an_regions:
                self.an_item.removeItem(region)
            self.an_regions = []

        def _draw_capture(self, title: str, traces) -> None:
            """Gauche : une capture et ses cœurs de plateaux (comme le PNG)."""
            for region in self.an_regions:
                self.an_item.removeItem(region)
            self.an_regions = []
            if traces is None:
                self.an_u_curve.setData([], [])
                self.an_i_curve.setData([], [])
            else:
                t, U, I, runs_pos, runs_neg = traces
                self.an_u_curve.setData(t, U)
                self.an_i_curve.setData(t, I)
                for runs, color in ((runs_pos, (44, 160, 44, 50)), (runs_neg, (214, 39, 40, 50))):
                    for s, e in runs:
                        s2, e2 = plateaux.core(s, e)
                        region = pg.LinearRegionItem(
                            values=(t[s2], t[e2 - 1]), movable=False, brush=pg.mkBrush(color)
                        )
                        self.an_item.addItem(region)
                        self.an_regions.append(region)
                self.an_vb_right.enableAutoRange()
            self.an_item.setTitle(title, color=getattr(self, "_plot_fg", None))

        def _append_evo(self, row) -> None:
            """Droite : un point par capture exploitable, comme UI_vs_t.png."""
            if row.get("flag") != "ok":
                return
            self._evo["t"].append(row["t_s"])
            for key in self._evo:
                if key != "t":
                    value = row.get(key, np.nan)
                    self._evo[key].append(np.nan if value is None else value)

        def _redraw_evo(self) -> None:
            if not self._evo["t"]:
                return
            t = np.array(self._evo["t"], float)
            for q in ("U", "I"):
                for pol in ("pos", "neg"):
                    med = np.array(self._evo[f"{q}_med_{pol}"], float)
                    std = np.array(self._evo[f"{q}_std_{pol}"], float)
                    curve, err = self.evo_items[(q, pol)]
                    if np.isnan(med).all():
                        continue  # pas de plateau négatif : rien à tracer
                    curve.setData(t, med)
                    err.setData(x=t, y=med, height=2 * np.nan_to_num(std))
            self.evo_items[("f", "fronts")][0].setData(t, np.array(self._evo["freq_Hz"], float))
            self.evo_items[("f", "fft")][0].setData(t, np.array(self._evo["freq_fft_Hz"], float))

        def on_plateau_ready(self, rec) -> None:
            row = rec["row"]
            self._draw_capture(f"Capture {row['index']:04d} — {row['flag']}", rec["traces"])
            self._append_evo(row)
            self._redraw_evo()

        def _show_series_header(self, folder) -> None:
            """Série affichée dans l'onglet Analyse : ID, échantillon, tags + actions."""
            self._current_series = Path(folder)
            try:
                meta = experiment.load_meta(folder)
            except (OSError, ValueError):
                self.series_label.setText(f"<b>{Path(folder).name}</b> — meta.json illisible")
                return
            fiche = meta["fiche"]
            sample = fiche["echantillon"]["id"] or "échantillon ?"
            parts = [f"<b>{meta['experiment_id']}</b>", sample, fiche["echantillon"]["materiau"],
                     fiche["operateur"], " ".join(f"#{t}" for t in fiche["tags"])]
            missing = experiment.missing_fields(fiche)
            if missing:
                parts.append(f"<span style='color:{theme.PALETTES[self.theme_name]['danger']}'>"
                             f"fiche incomplète ({len(missing)})</span>")
            self.series_label.setText("  ·  ".join(p for p in parts if p))
            live = self._recording and self._series_dir == Path(folder)
            self.btn_fiche.setEnabled(not live)
            self.btn_fiche.setToolTip("Pendant l'enregistrement, modifier la fiche dans l'onglet Mesure."
                                      if live else "Fiche, résultats post-essai, pièces jointes, historique.")
            self.btn_reprocess.setEnabled(not (self._armed or self._recording))

        def _on_open_series(self) -> None:
            start = str(self._current_series.parent) if self._current_series else self.outdir_edit.text()
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Ouvrir une série", start)
            if path:
                self._open_series(Path(path))

        def _open_series(self, folder: Path) -> None:
            """Charge une série enregistrée : empreintes (calculées a posteriori à la
            première ouverture), évolution U/I/f (plateaux.csv), parcours des captures."""
            user, when = experiment.current_user(), experiment.now_iso()
            try:
                meta = experiment.update_meta(
                    folder, lambda m: experiment.ensure_checksums(m, folder, user=user, when=when))
            except (OSError, ValueError) as exc:
                QtWidgets.QMessageBox.warning(self, "Série illisible", f"{folder}\n\n{exc}")
                return
            exp = meta["experiment_id"]
            report = experiment.verify_checksums(meta, folder)
            self._reset_analysis()
            flags = {}
            csv_path = folder / f"{exp}_plateaux.csv"
            if csv_path.exists():
                import pandas as pd

                df = pd.read_csv(csv_path, encoding="utf-8-sig")
                for row in df.to_dict("records"):
                    flags[int(row["index"])] = row.get("flag", "")
                    self._append_evo(row)
                self._redraw_evo()
            indices = sorted(c["index"] for c in meta["captures"]
                             if (folder / f"{exp}_{c['index']:04d}.csv").exists())
            self._opened = {"dir": folder, "exp": exp, "flags": flags,
                            "columns": experiment.capture_columns(meta), "indices": indices}
            self._show_series_header(folder)
            if indices:
                self.capture_spin.blockSignals(True)
                self.capture_spin.setRange(indices[0], indices[-1])
                self.capture_spin.setValue(indices[0])
                self.capture_spin.blockSignals(False)
                self.capture_spin.show()
                self._on_capture_selected(indices[0])
            else:
                self.capture_spin.hide()
            self.tabs.setCurrentIndex(1)
            if report["modifie"] or report["manquant"]:
                self.status.showMessage(
                    f"{exp} : ATTENTION données brutes — {len(report['modifie'])} modifiée(s), "
                    f"{len(report['manquant'])} manquante(s) (détail : Fiche… > Traçabilité)")
            elif not csv_path.exists():
                self.status.showMessage(f"{exp} : pas encore d'analyse des plateaux — cliquer « Re-traiter »")
            else:
                self.status.showMessage(f"{exp} : {len(indices)} capture(s), données brutes intègres")

        def _on_capture_selected(self, index: int) -> None:
            o = self._opened
            if not o:
                return
            path = o["dir"] / f"{o['exp']}_{index:04d}.csv"
            if not path.exists():
                self._draw_capture(f"Capture {index:04d} — absente (retirée)", None)
                return
            try:
                t, U, I = experiment.read_capture(path, o["columns"])
            except (OSError, ValueError, KeyError) as exc:
                self._draw_capture(f"Capture {index:04d} — illisible : {exc}", None)
                return
            row, traces = plateaux.analyse_arrays(t, U, I)
            flag = o["flags"].get(index, row["flag"])  # flag final (ex. U_saut, vu en fin de série)
            self._draw_capture(f"{o['exp']}_{index:04d}.csv — {flag}", traces or (t, U, I, [], []))

        def _on_fiche_dialog(self) -> None:
            if not self._current_series:
                return
            _, FicheDialog = gui_experiment.widgets()
            tags = experiment.collect_tags(self._current_series.parent)
            FicheDialog(self._current_series, tags, self).exec_()
            self._show_series_header(self._current_series)

        def _on_reprocess(self, force: bool) -> None:
            folder = self._current_series
            if not folder:
                return
            self.btn_reprocess.setEnabled(False)
            self.btn_open.setEnabled(False)
            self.status.showMessage(f"Re-traitement de {folder.name}…")
            user, when = experiment.current_user(), experiment.now_iso()

            def job():  # thread : figures matplotlib via Figure (pas pyplot), sans Qt
                try:
                    summary = experiment.reprocess(folder, user=user, when=when, force=force)
                    self._bridge.done.emit((folder, summary))
                except experiment.IntegrityError as exc:
                    self._bridge.integrity.emit((folder, str(exc)))
                except Exception as exc:  # noqa: BLE001 — remonté à l'UI
                    self._bridge.failed.emit(str(exc))

            threading.Thread(target=job, daemon=True).start()

        def _on_reprocess_done(self, result) -> None:
            folder, summary = result
            self.btn_open.setEnabled(True)
            self._open_series(folder)
            self.status.showMessage(
                f"Re-traité {folder.name} : {summary.get('n_ok')}/{summary.get('n_captures')} captures "
                f"exploitables, {summary.get('mode_majoritaire', '')} (algo {experiment.algo_version()})")

        def _on_reprocess_integrity(self, result) -> None:
            folder, message = result
            self.btn_open.setEnabled(True)
            self.btn_reprocess.setEnabled(True)
            answer = QtWidgets.QMessageBox.question(
                self, "Données brutes modifiées",
                f"{message}\n\nRe-traiter quand même ? L'analyse sera marquée « FORCÉE » "
                "dans la traçabilité de la série.",
            )
            if answer == QtWidgets.QMessageBox.StandardButton.Yes:
                self._on_reprocess(True)

        def _on_reprocess_failed(self, message: str) -> None:
            self.btn_open.setEnabled(True)
            self.btn_reprocess.setEnabled(True)
            QtWidgets.QMessageBox.warning(self, "Re-traitement impossible", message)

        # -- fiche pendant la série ----------------------------------------------------
        def _on_fiche_edited(self) -> None:
            self._update_alert()
            if self._recording:
                self._fiche_push_timer.start(1500)

        def _push_fiche(self) -> None:
            """Reporte la fiche dans le meta de la série en cours (modifications journalisées)."""
            folder = self._series_dir
            if not folder:
                return
            fiche, user, when = self.fiche_form.get_fiche(), experiment.current_user(), experiment.now_iso()
            try:
                experiment.update_meta(folder, lambda m: experiment.apply_fiche(m, fiche, user=user, when=when))
            except (OSError, ValueError) as exc:
                self.status.showMessage(f"Fiche non enregistrée dans {folder.name} : {exc}")
                return
            self._show_series_header(folder)

        def _update_alert(self) -> None:
            """Bandeau + champs en rouge si une série est armée ou enregistre avec une fiche
            incomplète (l'enregistrement démarre sur le signal : on ne bloque pas, on alerte)."""
            active = self._armed or self._recording
            missing = self.fiche_form.highlight_missing(active)
            if active and missing:
                what = "MANIP EN COURS" if self._recording else "Série armée"
                labels = ", ".join(experiment.FIELD_LABELS[k] for k in missing)
                self.banner.setText(f"⚠  {what} — fiche incomplète ({len(missing)}) : {labels}")
                self.banner.show()
            else:
                self.banner.hide()

        def on_plateau_error(self, msg: str) -> None:
            self.status.showMessage(f"Plateaux : {msg}")

        def on_plateau_summary(self, summary) -> None:
            self.status.showMessage(
                f"Plateaux « {summary['experiment']} » : {summary['n_ok']}/{summary['n_captures']} "
                f"captures exploitables, mode {summary['mode_majoritaire']} "
                f"-> {summary['experiment']}_plateaux.csv + _UI_vs_t.png"
            )

        def _on_points_entered(self) -> None:
            text = self.points_combo.currentText().strip()
            if not text.isdigit() or int(text) < 1:
                return
            self.display_max_points = int(text)  # décimation d'affichage, côté client

        # -- réception des signaux worker (thread UI) ----------------------------
        def on_connected(self, idn: str) -> None:
            self.status.showMessage(f"Connecté : {idn}")

        def on_connection_failed(self, msg: str) -> None:
            self.status.showMessage(f"Échec de connexion : {msg}")

        def on_waveform_ready(self, ch: str, wf) -> None:
            curve = self.curves.get(ch)
            if curve is None:
                return
            cfg = self.configs[ch]
            # Décime d'abord, applique le facteur ensuite (sur ~4000 pts, pas sur
            # les ~Mpts bruts) : même résultat, une multiplication ~1000x plus
            # petite à chaque frame (audit perf 2026-07-14).
            t, v = decimate(wf.time, wf.volts, max_points=self.display_max_points)
            v = v * cfg.factor
            curve.setData(t, v)
            self.status.showMessage(
                f"{cfg.display_name(ch)} : {len(wf.volts)} pts, {wf.sample_rate:.3g} Sa/s"
            )

        def on_acq_error(self, ch: str, msg: str) -> None:
            self.status.showMessage(f"{ch} : {msg}")

        def on_capture_done(self, result) -> None:
            extra = f" + {result['png']}" if result["png"] else ""
            self.status.showMessage(f"Capture : {result['channels']} voie(s) sauvées{extra}")

        def on_command_error(self, msg: str) -> None:
            self.status.showMessage(f"Erreur : {msg}")

        def on_series_progress(self, ev) -> None:
            if ev.kind == "started" and self._config is not None:
                self._recording = True
                self._series_dir = Path(self._config.outdir) / self._config.experiment_id
                self.id_state.setText("ENREGISTREMENT en cours — la fiche reste modifiable")
                self._push_fiche()  # modifications faites entre l'armement et le signal
                complete = not experiment.missing_fields(self.fiche_form.get_fiche())
                if complete and self._config.u_channel:
                    self.tabs.setCurrentIndex(1)  # fiche incomplète : on reste sur Mesure
                self._update_alert()
            elif ev.kind == "failed" and ev.message:
                QtWidgets.QMessageBox.warning(self, "Série refusée", ev.message)
            if ev.kind == "capture":
                self.status.showMessage(
                    f"Série : capture {ev.index}/{ev.total} "
                    f"({len(ev.result['errors'])} erreur(s))"
                )
            elif ev.kind in ("countdown", "waiting_threshold"):
                self.status.showMessage(f"Série : {ev.kind} — {ev.remaining_s:.0f}s restantes")
            else:
                self.status.showMessage(f"Série : {ev.kind}")

        def on_series_done(self, result) -> None:
            if not result.started:
                self.status.showMessage("Série : condition de démarrage non atteinte (rien capturé)")
            else:
                self.status.showMessage(
                    f"Série terminée : {len(result.captures)} capture(s) -> {result.meta_path}"
                )
            finished_dir = self._series_dir if self._recording else None
            if finished_dir:
                self._fiche_push_timer.stop()
                self._push_fiche()  # dernières modifications
            self._armed = self._recording = False
            self._series_dir = None
            self.btn_series_start.setEnabled(True)
            self.btn_series_stop.setEnabled(False)
            for w in self._series_lockable + self._recording_lockable + self._id_lockable + [self.btn_open]:
                w.setEnabled(True)
            if finished_dir:
                self._show_series_header(finished_dir)  # Fiche… / Re-traiter sur cette série
                # Essai suivant : fiche reprise sauf ID d'échantillon et notes.
                self.fiche_form.set_fiche(experiment.prefill(self.fiche_form.get_fiche()))
                self.fiche_form.set_tag_suggestions(experiment.collect_tags(finished_dir.parent))
            self._refresh_next_id()
            self._update_alert()

        # -- fermeture -------------------------------------------------------------
        def closeEvent(self, event) -> None:  # noqa: N802 — override Qt
            # Le "quit" n'est drainé qu'au tour de boucle suivant : si une série
            # est en cours, le tour en cours peut être bloqué dans un fetch
            # mémoire profonde (mesuré jusqu'à ~10-40s selon transport/matériel,
            # cf. mémoire projet) -- 2000ms suffisait pour le live seul, pas ici.
            save_gui_settings(self._collect_settings(), self.settings_path)
            self.cmd_queue.put(("quit",))
            self.worker.wait(30_000)
            super().closeEvent(event)

    return MainWindow()


def run_gui(
    ip: str,
    *,
    socket: bool = False,
    usb: bool = False,
    timeout_ms: int = 10_000,
    config_path=CONFIG_PATH,
) -> None:
    """Lance le panneau de contrôle graphique complet pour ``ip`` (ignorée si ``usb``).

    ``config_path`` : fichier JSON de config par voie (nom/unité/facteur), cf.
    ``channel_config.py`` — paramétrable pour les tests, défaut inchangé sinon.
    """
    from pyqtgraph.Qt import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = _build_main_window(
        ip, socket=socket, usb=usb, timeout_ms=timeout_ms, config_path=config_path
    )
    win.resize(1500, 920)
    win.show()
    app.exec()
