"""Capture temporelle (série d'expérience) : time-lapse de waveforms.

Orchestre des briques déjà validées sur matériel -- ``waveform.fetch``/``save``,
``control`` (trigger natif) et ``acquisition.wait_for_trigger`` -- pour
enregistrer une série de captures à intervalle régulier, sous un ``experiment_id``,
avec plusieurs façons de démarrer la série.

Toute la logique est pure/injectée (``clock``/``sleep``/``fetch``/``save``/
``wait``), testable sans matériel ni vraie temporisation -- même principe que
``acquisition.wait_for_trigger``.

**Démarrage** (:func:`start_series`), un seul mécanisme pour trois modes :

- ``"now"`` : démarre immédiatement.
- ``"countdown"`` : attend ``delay_s`` secondes (le temps de préparer le montage).
- ``"threshold"`` : configure le trigger *natif* du scope (EDGE sur une voie/niveau/
  front) et attend le déclenchement (:func:`scope.acquisition.wait_for_trigger`).
  C'est aussi la façon de « jeter le rodage » : rien n'est capturé avant la mise
  sous tension détectée par ce seuil -- inutile de coder une détection séparée.

**Boucle** (:func:`run_series`) : capture le waveform courant de chaque voie à
intervalle régulier (pas de ré-armement par tick), jusqu'à la première limite
atteinte entre le nombre de tops calculés et ``duration_max``. Écrit un sidecar
``{experiment_id}_meta.json`` pour la traçabilité du protocole.

**Pilotage pas à pas** (:class:`SeriesRunner`) : même logique que
:func:`run_series`, mais découpée en une machine à états dont
:meth:`SeriesRunner.step` ne bloque jamais -- pour être appelée depuis la
boucle d'un ``QThread`` (GUI) qui doit rester réactive (drainer sa file de
commandes, honorer un arrêt) pendant qu'une série tourne, sans thread ni
connexion supplémentaire (VXI-11 n'accepte qu'un seul client).
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import asdict, dataclass, field, replace

from . import control, experiment
from .acquisition import read_inr, triggered
from .acquisition import wait_for_trigger as _default_wait
from .channel_config import ChannelConfig
from .waveform import decimate as _default_decimate
from .waveform import fetch as _default_fetch
from .waveform import save_capture as _default_save

VALID_START_MODES = frozenset({"now", "countdown", "threshold"})

# Cadence CLI (--per) -> secondes par unité.
PER_UNIT_SECONDS = {"second": 1.0, "minute": 60.0, "hour": 3600.0}

_DURATION_UNIT_SECONDS = {"s": 1.0, "m": 60.0, "h": 3600.0}


# --- helpers purs --------------------------------------------------------------------
def parse_duration(text: str) -> float:
    """Parse une durée CLI en secondes : ``"30s"``, ``"5m"``, ``"2h"``, ou un
    nombre nu (secondes), ex. ``"90"`` -> ``90.0``. Lève ``ValueError`` sinon."""
    text = text.strip()
    if text and text[-1] in _DURATION_UNIT_SECONDS:
        try:
            value = float(text[:-1])
        except ValueError as exc:
            raise ValueError(f"durée invalide {text!r}") from exc
        return value * _DURATION_UNIT_SECONDS[text[-1]]
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"durée invalide {text!r}, attendu un nombre de secondes ou un suffixe "
            f"parmi {sorted(_DURATION_UNIT_SECONDS)}"
        ) from exc


def series_filename(experiment_id: str, index: int, channel: str) -> str:
    """Nom de base (sans extension) d'une capture de série : ``{id}_{index:04d}_{channel}``."""
    return f"{experiment_id}_{index:04d}_{channel}"


def capture_interval(rate: float, per_seconds: float) -> float:
    """Convertit une cadence (``rate`` captures par ``per_seconds`` secondes) en
    intervalle entre deux captures, en secondes.

    Ex. ``capture_interval(10, 60)`` (10 captures/minute) -> ``6.0``.
    Lève ``ValueError`` si ``rate`` n'est pas strictement positif.
    """
    if rate <= 0:
        raise ValueError(f"cadence invalide {rate!r}, attendu > 0")
    return per_seconds / rate


def tick_deadlines(t0: float, interval: float, duration_max: float) -> list[float]:
    """Instants absolus des captures : ``t0``, ``t0+interval``, ... tant que
    ``<= t0 + duration_max``.

    Calculés par multiplication (``t0 + i*interval``), pas par addition répétée,
    pour éviter toute dérive cumulée sur une série longue.
    """
    deadlines = []
    i = 0
    while True:
        t = t0 + i * interval
        if t > t0 + duration_max:
            break
        deadlines.append(t)
        i += 1
    return deadlines


# --- démarrage -------------------------------------------------------------------------
def arm_threshold(scope, threshold: dict) -> None:
    """Configure le trigger natif du scope pour le mode de démarrage ``"threshold"``.

    ``threshold`` : ``{"channel", "level", "slope", "timeout_s"}`` (``timeout_s``
    n'est pas utilisé ici, seulement par l'attente qui suit cet armement). Arme
    un trigger EDGE en mode ``SINGLE`` puis lance l'acquisition (``ARM``) --
    séparé de l'attente (:func:`scope.acquisition.wait_for_trigger`) pour être
    réutilisable par :class:`SeriesRunner` (GUI), qui sonde sans bloquer.
    """
    control.set_trigger_source(scope, threshold["channel"])
    control.set_trigger_level(scope, threshold["channel"], threshold["level"])
    control.set_trigger_slope(scope, threshold["channel"], threshold["slope"])
    control.set_trigger_mode(scope, "SINGLE")
    control.run(scope)


def start_series(
    scope,
    mode: str,
    *,
    delay_s: float = 0.0,
    threshold: dict | None = None,
    clock,
    sleep,
    wait=_default_wait,
) -> bool:
    """Démarre une série : ``"now"``, ``"countdown"`` ou ``"threshold"``.

    ``threshold`` (mode ``"threshold"``) : voir :func:`arm_threshold`. Retourne
    ``False`` si le seuil n'est pas atteint dans le délai (la série est alors
    annulée par l'appelant, rien n'est capturé -- c'est le mécanisme de
    « rodage jeté »).
    """
    if mode not in VALID_START_MODES:
        raise ValueError(f"mode de démarrage invalide {mode!r}, attendu {sorted(VALID_START_MODES)}")

    if mode == "now":
        return True

    if mode == "countdown":
        sleep(delay_s)
        return True

    # mode == "threshold"
    arm_threshold(scope, threshold)
    return wait(scope, timeout_s=threshold["timeout_s"])


# --- boucle time-lapse -------------------------------------------------------------------
@dataclass
class SeriesConfig:
    """Paramètres d'une série d'expérience (indépendant du transport/matériel).

    ``configs`` : réglage (label/unité/facteur) par voie, cf.
    ``channel_config.ChannelConfig`` -- chargé une fois par l'appelant (CLI
    ``cmd_series``, GUI ``_on_series_start``) depuis ``channels_config.json``,
    appliqué à chaque waveform avant export (nom de colonne du CSV combiné,
    conversion).
    """

    experiment_id: str
    channels: list[str]
    outdir: str
    rate: float
    per_seconds: float
    duration_max: float
    start_mode: str = "now"
    delay_s: float = 0.0
    threshold: dict | None = None
    formats: tuple = ("csv", "npy")
    points: int = 4000
    configs: dict = field(default_factory=dict)
    # Voies tension/courant pour l'extraction des plateaux (``plateaux.py``,
    # GUI) ; None = pas d'analyse. Enregistrées dans le meta pour traçabilité.
    u_channel: str | None = None
    i_channel: str | None = None
    # Fiche d'expérience (cf. ``experiment.FICHE_FIELDS``) et heure murale ISO de
    # l'armement -- écrites dans le meta dès la détection, pour la traçabilité.
    fiche: dict | None = None
    armed_at: str | None = None


@dataclass
class RunResult:
    """Résultat d'une série : capture par capture, plus le sidecar meta écrit."""

    started: bool
    captures: list[dict] = field(default_factory=list)
    meta_path: str | None = None


def _series_dir(config: SeriesConfig) -> str:
    """Dossier de sortie d'une série : ``{outdir}/{experiment_id}/``."""
    return os.path.join(config.outdir, config.experiment_id)


def _check_new_series_dir(config: SeriesConfig) -> None:
    """Une série ne s'écrase jamais : refuse un dossier existant non vide (ID figé)."""
    series_dir = _series_dir(config)
    if os.path.isdir(series_dir) and os.listdir(series_dir):
        raise FileExistsError(f"le dossier de série {series_dir} existe déjà et n'est pas vide")


def _protocol(config: SeriesConfig) -> dict:
    """Clés du protocole d'acquisition (schéma v1, conservées à la racine du meta)."""
    return {
        "experiment_id": config.experiment_id,
        "channels": config.channels,
        "rate": config.rate,
        "per_seconds": config.per_seconds,
        "duration_max": config.duration_max,
        "start_mode": config.start_mode,
        "formats": list(config.formats),
        "points": config.points,
        "u_channel": config.u_channel,
        "i_channel": config.i_channel,
    }


def create_series_meta(config: SeriesConfig, started_at: str) -> str:
    """Premier meta, écrit dès le démarrage (détection) : la fiche peut ensuite y être
    modifiée pendant l'enregistrement (:func:`experiment.update_meta`)."""
    voies = {ch: asdict(config.configs.get(ch, ChannelConfig())) for ch in config.channels}
    meta = {
        **_protocol(config),
        "uuid": uuid.uuid4().hex,
        "station": socket.gethostname(),
        "utilisateur_windows": experiment.current_user(),
        "dates": {"armee": config.armed_at or started_at, "debut": started_at, "fin": None},
        "acquisition": {"voies": voies, "scope": {}},
        "fiche": config.fiche or experiment.empty_fiche(),
        "captures": [],
    }
    return str(experiment.create_meta(_series_dir(config), meta))


def write_series_meta(config: SeriesConfig, captures: list[dict], *, ended_at: str | None = None,
                      scope_settings: dict | None = None) -> str:
    """Écrit le sidecar ``{experiment_id}_meta.json`` (protocole + captures) et
    retourne son chemin. Traçabilité du protocole -- indépendant du transport.

    Fusion : si le meta existe (créé au démarrage), seules les clés d'acquisition
    sont mises à jour -- la fiche et son historique, modifiables pendant la série,
    sont conservés. En fin de série (``ended_at``), ajoute les empreintes SHA-256
    des fichiers bruts."""
    series_dir = _series_dir(config)
    if not os.path.exists(os.path.join(series_dir, f"{config.experiment_id}_meta.json")):
        create_series_meta(config, ended_at or experiment.now_iso())

    def merge(meta):
        meta.update(_protocol(config))
        meta["captures"] = captures
        if scope_settings:
            meta.setdefault("acquisition", {})["scope"] = scope_settings
        if ended_at:
            meta.setdefault("dates", {})["fin"] = ended_at
            meta["empreintes"] = experiment.compute_checksums(series_dir, config.experiment_id)
            meta["empreintes_info"] = {"date": ended_at, "a_posteriori": False}

    experiment.update_meta(series_dir, merge)
    return str(experiment.meta_path(series_dir))


def scope_settings_from(waveforms: dict) -> dict:
    """Réglages réels lus dans les waveforms (descripteur WAVEDESC) : VDIV, offset,
    période d'échantillonnage native -- pas les valeurs affichées dans la GUI."""
    settings = {}
    for ch, wf in waveforms.items():
        values = {k: getattr(wf, k, None) for k in ("vdiv", "offset", "interval")}
        if any(v is not None for v in values.values()):
            settings[ch] = {"vdiv_V": values["vdiv"], "offset_V": values["offset"],
                            "periode_echantillonnage_s": values["interval"]}
    return settings


def capture_once(
    config: SeriesConfig,
    scope,
    index: int,
    series_dir: str,
    *,
    fetch=_default_fetch,
    save=_default_save,
    decimate=_default_decimate,
) -> dict:
    """Effectue une capture de série (un tick) : fetch + décimation de chaque
    voie de ``config`` (échecs isolés par voie), puis **un seul** CSV combiné
    (une colonne par voie) + un fichier par voie pour les formats binaires
    (:func:`scope.waveform.save_capture`, cf. sa docstring).

    **Une capture = un instantané décimé à ``config.points``** (défaut 4000),
    même principe que l'affichage GUI/live (``gui.py`` : fetch la mémoire
    native complète puis ``decimate()`` côté client) -- pas le dump brut de la
    mémoire profonde (~14 Mpts, ~300 Mo/CSV). Ça garde les fichiers de série
    légers ; ça ne réduit pas le temps de transfert depuis le scope (toujours
    la mémoire complète lue), qui reste le plancher de cadence réel.

    Retourne ``{"index", "files", "errors", "waveforms"}`` -- ``waveforms``
    (``{channel: Waveform décimée}``) sert à la GUI pour rafraîchir le plot
    pendant une série ; :func:`run_series` (CLI) l'ignore.
    """
    errors = []
    waveform_list = []
    waveforms = {}
    for channel in config.channels:
        try:
            wf = fetch(scope, channel)
            cfg = config.configs.get(channel, ChannelConfig())
            wf = replace(wf, label=cfg.label, unit=cfg.unit, factor=cfg.factor)
            wf.time, wf.volts = decimate(wf.time, wf.volts, max_points=config.points)
            waveform_list.append(wf)
            waveforms[channel] = wf
        except Exception as exc:  # noqa: BLE001 — isole la voie, ne bloque pas les autres
            errors.append(str(exc))

    files = []
    if waveform_list:
        base = os.path.join(series_dir, f"{config.experiment_id}_{index:04d}")
        try:
            files = save(waveform_list, base, formats=config.formats)
        except Exception as exc:  # noqa: BLE001 — ex. axes incompatibles entre voies
            errors.append(str(exc))

    return {"index": index, "files": files, "errors": errors, "waveforms": waveforms}


def run_series(
    config: SeriesConfig,
    scope,
    *,
    clock,
    sleep,
    fetch=_default_fetch,
    save=_default_save,
    wait=_default_wait,
    decimate=_default_decimate,
    wall_clock=None,
) -> RunResult:
    """Exécute une série de captures time-lapse selon ``config``.

    À chaque tick : capture (:func:`capture_once`, pas de ré-armement),
    jusqu'à la première limite atteinte entre le nombre de tops calculés et
    ``duration_max``. Écrit un sidecar ``{experiment_id}_meta.json``
    (:func:`write_series_meta`) pour la traçabilité du protocole -- sauf si la
    série n'a jamais démarré (seuil non atteint : aucun fichier écrit, rodage
    jeté). Refuse un dossier de série existant non vide (``FileExistsError``).
    """
    _check_new_series_dir(config)
    started = start_series(
        scope,
        config.start_mode,
        delay_s=config.delay_s,
        threshold=config.threshold,
        clock=clock,
        sleep=sleep,
        wait=wait,
    )
    if not started:
        return RunResult(started=False)

    interval = capture_interval(config.rate, config.per_seconds)
    t0 = clock()
    deadlines = tick_deadlines(t0, interval, config.duration_max)

    series_dir = _series_dir(config)
    os.makedirs(series_dir, exist_ok=True)
    create_series_meta(config, experiment.now_iso(wall_clock))

    captures = []
    scope_settings = {}
    for index, deadline in enumerate(deadlines, start=1):
        now = clock()
        if deadline > now:
            sleep(deadline - now)

        rec = capture_once(config, scope, index, series_dir, fetch=fetch, save=save, decimate=decimate)
        captures.append({
            "index": index,
            "timestamp": clock(),
            "heure": experiment.now_iso(wall_clock),
            "files": rec["files"],
            "errors": rec["errors"],
        })
        scope_settings = scope_settings or scope_settings_from(rec["waveforms"])

    meta_path = write_series_meta(config, captures, ended_at=experiment.now_iso(wall_clock),
                                  scope_settings=scope_settings)
    return RunResult(started=True, captures=captures, meta_path=meta_path)


# --- pilotage pas à pas (GUI) --------------------------------------------------------
def _default_poll(scope) -> bool:
    """Sondage par défaut du seuil : bit 0 du registre ``INR?`` (lit-et-efface).

    Même primitive que :func:`scope.acquisition.wait_for_trigger`, mais un seul
    sondage par appel (non bloquant) -- c'est :class:`SeriesRunner` qui rappelle
    ce sondage à chaque ``step``, pas une boucle interne.
    """
    return triggered(read_inr(scope))


@dataclass
class SeriesEvent:
    """Un événement émis par :meth:`SeriesRunner.step`, traduit en signaux Qt côté GUI."""

    kind: str  # started|countdown|armed|waiting_threshold|capture|done|failed
    index: int | None = None
    total: int | None = None
    remaining_s: float | None = None
    result: dict | None = None  # dict de capture_once, si kind == "capture"
    waveforms: dict | None = None  # {channel: Waveform}, si kind == "capture"
    message: str = ""  # cause, si kind == "failed"


class SeriesRunner:
    """Machine à états Qt-free pour une série, pilotée pas à pas via :meth:`step`.

    Équivalent de :func:`run_series`, mais ``step(scope, now)`` ne bloque
    jamais : chaque appel fait au plus une petite unité de travail (armer,
    sonder le seuil, ou faire **une seule** capture même si plusieurs
    deadlines sont en retard) et retourne aussitôt. Conçu pour être appelé
    depuis la boucle d'un ``QThread`` qui doit rester réactive (drainer sa
    file de commandes) pendant qu'une série tourne -- voir ``gui.py``.

    Ne stocke jamais le ``scope`` : il est passé à chaque ``step``, comme
    ``execute_command(scope, cmd)``.
    """

    def __init__(
        self,
        config: SeriesConfig,
        *,
        clock,
        arm=arm_threshold,
        poll=_default_poll,
        fetch=_default_fetch,
        save=_default_save,
        decimate=_default_decimate,
        wall_clock=None,
    ) -> None:
        self.config = config
        self.clock = clock
        self.wall_clock = wall_clock  # heure murale (dates du meta), injectable
        self._arm = arm
        self._poll = poll
        self._fetch = fetch
        self._save = save
        self._decimate = decimate

        self.phase = "start"  # start|countdown|threshold|running|done|failed
        self.captures: list[dict] = []
        self.result: RunResult | None = None

        self._deadline_wall: float | None = None
        self._deadlines: list[float] = []
        self._ptr = 0
        self._stop = False
        self._scope_settings: dict = {}

    def request_stop(self) -> None:
        """Demande l'arrêt à la prochaine occasion (honoré au ``step`` suivant)."""
        self._stop = True

    @property
    def finished(self) -> bool:
        return self.phase in ("done", "failed")

    def step(self, scope, now: float) -> list[SeriesEvent]:
        """Fait avancer la machine d'un pas ; jamais bloquant. Retourne 0..n événements."""
        if self.phase == "start":
            return self._step_start(scope, now)
        if self.phase == "countdown":
            return self._step_countdown(now)
        if self.phase == "threshold":
            return self._step_threshold(scope, now)
        if self.phase == "running":
            return self._step_running(scope, now)
        return []  # done/failed : plus rien à faire

    # --- phases -----------------------------------------------------------------
    def _step_start(self, scope, now: float) -> list[SeriesEvent]:
        mode = self.config.start_mode
        if mode == "now":
            return self._begin_running(now)
        if mode == "countdown":
            self._deadline_wall = now + self.config.delay_s
            self.phase = "countdown"
            return [SeriesEvent("countdown", remaining_s=self.config.delay_s)]
        # mode == "threshold"
        self._arm(scope, self.config.threshold)
        self._deadline_wall = now + self.config.threshold["timeout_s"]
        self.phase = "threshold"
        return [SeriesEvent("armed")]

    def _step_countdown(self, now: float) -> list[SeriesEvent]:
        if self._stop:
            return self._finalize(now)
        if now >= self._deadline_wall:
            return self._begin_running(now)
        return [SeriesEvent("countdown", remaining_s=self._deadline_wall - now)]

    def _step_threshold(self, scope, now: float) -> list[SeriesEvent]:
        if self._stop:
            self.phase = "failed"
            self.result = RunResult(started=False)
            return [SeriesEvent("failed")]
        if self._poll(scope):
            return self._begin_running(now)
        if now >= self._deadline_wall:
            self.phase = "failed"
            self.result = RunResult(started=False)
            return [SeriesEvent("failed")]
        return [SeriesEvent("waiting_threshold", remaining_s=self._deadline_wall - now)]

    def _step_running(self, scope, now: float) -> list[SeriesEvent]:
        if self._stop or self._ptr >= len(self._deadlines):
            return self._finalize(now)
        if now >= self._deadlines[self._ptr]:
            index = self._ptr + 1
            rec = capture_once(
                self.config,
                scope,
                index,
                _series_dir(self.config),
                fetch=self._fetch,
                save=self._save,
                decimate=self._decimate,
            )
            self.captures.append({
                "index": index,
                "timestamp": self.clock(),
                "heure": experiment.now_iso(self.wall_clock),
                "files": rec["files"],
                "errors": rec["errors"],
            })
            self._scope_settings = self._scope_settings or scope_settings_from(rec["waveforms"])
            self._ptr += 1
            return [
                SeriesEvent(
                    "capture",
                    index=index,
                    total=len(self._deadlines),
                    result=rec,
                    waveforms=rec["waveforms"],
                )
            ]
        return []

    # --- transitions --------------------------------------------------------------
    def _begin_running(self, now: float) -> list[SeriesEvent]:
        """Détection : crée le dossier et le meta (fiche, dates) -- ou échoue sans rien
        écraser si le dossier de série existe déjà."""
        try:
            _check_new_series_dir(self.config)
        except FileExistsError as exc:
            self.phase = "failed"
            self.result = RunResult(started=False)
            return [SeriesEvent("failed", message=str(exc))]
        interval = capture_interval(self.config.rate, self.config.per_seconds)
        self._deadlines = tick_deadlines(now, interval, self.config.duration_max)
        self._ptr = 0
        os.makedirs(_series_dir(self.config), exist_ok=True)
        create_series_meta(self.config, experiment.now_iso(self.wall_clock))
        self.phase = "running"
        return [SeriesEvent("started")]

    def _finalize(self, now: float) -> list[SeriesEvent]:
        meta_path = None
        if self.phase == "running":  # arrêt pendant un compte à rebours : rien n'a été créé
            meta_path = write_series_meta(
                self.config, self.captures, ended_at=experiment.now_iso(self.wall_clock),
                scope_settings=self._scope_settings,
            )
        self.result = RunResult(started=True, captures=self.captures, meta_path=meta_path)
        self.phase = "done"
        return [SeriesEvent("done")]
