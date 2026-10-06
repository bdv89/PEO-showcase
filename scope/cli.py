"""Interface ligne de commande multiplateforme pour le SDS1204X-E.

Exemples ::

    python -m scope.cli idn 192.168.1.50
    python -m scope.cli scpi 192.168.1.50
    python -m scope.cli capture 192.168.1.50 --channels C1 C2 --plot
    python -m scope.cli screenshot 192.168.1.50 --out captures/ecran.bmp
    python -m scope.cli capture 192.168.1.50 --single --trigger-timeout 5
    python -m scope.cli series 192.168.1.50 --id essai42 --rate 10 --per minute \
        --duration 30m --channels C1 C2
    python -m scope.cli series 192.168.1.50 --id essai42 --rate 1 --per second \
        --duration 5m --start threshold --threshold-channel C1 --threshold-level 1V
    python -m scope.cli set 192.168.1.50 --timebase 1MS --c1-vdiv 1V
    python -m scope.cli live 192.168.1.50 --channels C1
    python -m scope.cli gui 192.168.1.50
    python -m scope.cli gui 192.168.1.50 --vxi11   # forcer VXI-11 (socket par défaut)
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from datetime import datetime

from . import control, measure as measure_mod, series
from .acquisition import read_inr, wait_for_trigger
from .channel_config import CONFIG_PATH, ChannelConfig, load_channel_configs
from .connection import Scope
from .discover import local_ipv4_cidrs, scan
from .waveform import VALID_FORMATS, fetch, save_capture


def _connect(args) -> Scope:
    return Scope(args.ip, socket=args.socket, usb=args.usb, timeout_ms=args.timeout)


def _live_transport(args) -> dict:
    """Transport pour live/gui/capture/series : socket par défaut (~30-50x plus
    rapide qu'en VXI-11 pour un fetch complet, mesuré sur matériel — cf.
    docs/architecture.md), USB si ``--usb`` (⚠️ confirmé cassé sur ce scope pour
    ``WF? DESC``/``DAT2`` — bug du firmware (tronque la réponse à un seul paquet
    USB tout en déclarant EOM=1 à tort, capture `usbmon` à l'appui), pas du
    logiciel client. Cf. docs/architecture.md § « Mesure socket vs USB ». Laissé
    disponible pour d'autres instruments/firmwares), VXI-11 si ``--vxi11`` force
    l'ancien transport.

    ``capture``/``series`` fetchent elles aussi la mémoire native complète à
    chaque lecture (cf. ``waveform.fetch``, ``series.capture_once``) : même coût
    par requête que live/gui, donc même défaut socket (audit du 2026-07-14 —
    VXI-11 y faisait décrocher une série time-lapse, chaque capture prenant
    jusqu'à ~10s/voie au lieu de ~0,2-1s). Indépendant de ``--socket`` (qui garde
    son défaut ``False`` pour idn/scpi/set/measure/screenshot, où la vitesse
    importe moins — et où ``screenshot`` en particulier doit rester en VXI-11 par
    défaut : ``screen_dump()`` lit avec ``read_raw()`` délimité par le flag END,
    incompatible avec la terminaison ``\\n`` du mode socket sur un BMP contenant
    des octets ``0x0A``)."""
    if args.usb:
        return {"socket": False, "usb": True}
    return {"socket": not args.vxi11, "usb": False}


# --- sous-commandes ------------------------------------------------------------
def cmd_idn(args) -> int:
    with _connect(args) as scope:
        print(scope.idn())
    return 0


def cmd_scpi(args) -> int:
    """REPL SCPI : une ligne finie par '?' est traitée comme une query."""
    with _connect(args) as scope:
        print("Console SCPI — Ctrl-D pour quitter. (Une commande finissant par '?' = query.)")
        while True:
            try:
                line = input("scpi> ").strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            try:
                if line.endswith("?"):
                    print(scope.query(line))
                else:
                    scope.write(line)
            except Exception as exc:  # noqa: BLE001 — feedback interactif
                print(f"erreur : {exc}", file=sys.stderr)
    return 0


def _capture_channels(scope, channels, outdir: str, stamp: str, formats=("csv", "npy"), configs=None):
    """Lit et sauve chaque voie ; isole les échecs pour ne pas perdre les autres.

    ``configs`` : réglage (label/unité/facteur) par voie, cf.
    ``channel_config.ChannelConfig`` — appliqué à chaque waveform avant export
    (nom de colonne du CSV combiné, conversion), symétrique à la GUI.

    Retourne ``(waveforms, errors)`` : les voies lues avec succès (:class:`Waveform`,
    déjà configurées) et les messages d'erreur des voies en échec (ex.
    acquisition vide). Le CSV combiné (une colonne par voie) + les fichiers
    binaires par voie sont écrits une fois toutes les voies lues, cf.
    :func:`cmd_capture`.
    """
    configs = configs or {}
    waveforms = []
    errors = []
    for ch in channels:
        try:
            wf = fetch(scope, ch)
            cfg = configs.get(ch, ChannelConfig())
            wf = dataclasses.replace(wf, label=cfg.label, unit=cfg.unit, factor=cfg.factor)
            waveforms.append(wf)
        except Exception as exc:  # noqa: BLE001 — isole la voie, ne bloque pas les autres
            errors.append(f"{ch} : {exc}")
            print(f"{ch}: échec ({exc})", file=sys.stderr)

    if waveforms:
        base = f"{outdir}/{stamp}"
        try:
            paths = save_capture(waveforms, base, formats=formats)
            print(f"{len(waveforms)} voie(s) -> {', '.join(paths)}")
        except Exception as exc:  # noqa: BLE001 — ex. axes incompatibles entre voies
            errors.append(str(exc))
            print(f"échec de sauvegarde : {exc}", file=sys.stderr)

    return waveforms, errors


def cmd_capture(args) -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    configs = load_channel_configs(CONFIG_PATH)
    with Scope(args.ip, timeout_ms=args.timeout, **_live_transport(args)) as scope:
        if args.single:
            control.set_trigger_mode(scope, "SINGLE")
            read_inr(scope)  # purge un résidu d'un précédent armement, AVANT ARM
            control.run(scope)
            if not wait_for_trigger(scope, timeout_s=args.trigger_timeout):
                print(
                    f"aucun déclenchement en {args.trigger_timeout:g}s, capture annulée",
                    file=sys.stderr,
                )
                return 1
        waveforms, errors = _capture_channels(
            scope, args.channels, args.outdir, stamp, formats=args.format, configs=configs
        )

    if args.plot and waveforms:
        from .plot import plot_static

        png = f"{args.outdir}/{stamp}.png"
        plot_static(waveforms, save_path=png, show=not args.no_show)
        print(f"plot -> {png}")
    return 1 if errors and not waveforms else 0


def cmd_series(args) -> int:
    """Série de captures time-lapse (voir ``scope.series``)."""
    threshold = None
    if args.start == "threshold":
        threshold = {
            "channel": args.threshold_channel,
            "level": args.threshold_level,
            "slope": args.threshold_slope,
            "timeout_s": args.threshold_timeout,
        }
    config = series.SeriesConfig(
        experiment_id=args.id,
        channels=args.channels,
        outdir=args.outdir,
        rate=args.rate,
        per_seconds=series.PER_UNIT_SECONDS[args.per],
        duration_max=series.parse_duration(args.duration),
        start_mode=args.start,
        delay_s=args.countdown,
        threshold=threshold,
        formats=tuple(args.format),
        points=args.points,
        configs=load_channel_configs(CONFIG_PATH),
    )
    with Scope(args.ip, timeout_ms=args.timeout, **_live_transport(args)) as scope:
        result = series.run_series(config, scope, clock=time.monotonic, sleep=time.sleep)

    if not result.started:
        print("série annulée : condition de démarrage non atteinte (rien capturé)", file=sys.stderr)
        return 1

    print(f"{len(result.captures)} capture(s) -> {config.outdir}/{config.experiment_id}/")
    if result.meta_path:
        print(f"méta -> {result.meta_path}")
    return 0


def cmd_set(args) -> int:
    with _connect(args) as scope:
        if args.timebase:
            control.set_timebase(scope, args.timebase)
        for ch in ("C1", "C2", "C3", "C4"):
            vdiv = getattr(args, f"{ch.lower()}_vdiv")
            if vdiv:
                control.set_vdiv(scope, ch, vdiv)
        if args.coupling:
            ch, val = args.coupling
            control.set_coupling(scope, ch, val)
        if args.autoset:
            control.autoset(scope)
        if args.autoscale:
            channels = args.autoscale_channels or control.active_channels(scope)
            for ch in channels:
                control.autoscale(scope, ch)
        if args.run:
            control.run(scope)
        if args.stop:
            control.stop(scope)
        print("OK")
    return 0


def cmd_screenshot(args) -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = args.out or f"{args.outdir}/{stamp}.bmp"
    with _connect(args) as scope:
        data = scope.screen_dump()
    with open(path, "wb") as fh:
        fh.write(data)
    print(f"screenshot -> {path}")
    return 0


def cmd_measure(args) -> int:
    with _connect(args) as scope:
        for ch in args.channels:
            if args.all:
                values = measure_mod.measure_all(scope, ch)
            else:
                values = {p: measure_mod.measure(scope, ch, p) for p in args.params}
            for param, value in values.items():
                shown = "--" if value is None else value
                print(f"{ch} {param}: {shown}")
    return 0


def cmd_discover(args) -> int:
    cidrs = [args.cidr] if args.cidr else local_ipv4_cidrs()
    if not cidrs:
        print("aucune interface réseau locale exploitable trouvée", file=sys.stderr)
        return 1
    results = []
    for cidr in cidrs:
        results.extend(scan(cidr))
    if not results:
        print("aucun scope Siglent trouvé", file=sys.stderr)
        return 1
    for ip, idn in results:
        print(f"{ip}\t{idn}")
    return 0


def cmd_live(args) -> int:
    from .live import run_live

    with Scope(args.ip, timeout_ms=args.timeout, **_live_transport(args)) as scope:
        run_live(scope, args.channels, interval_ms=args.interval)
    return 0


def cmd_gui(args) -> int:
    """Panneau de contrôle graphique complet : ne pas ouvrir de Scope ici.

    Le thread d'acquisition dédié (``scope.gui.AcquisitionWorker``) ouvre et
    possède l'unique ``Scope`` — la ressource VISA n'est pas thread-safe.
    """
    from .gui import run_gui

    run_gui(args.ip, timeout_ms=args.timeout, **_live_transport(args))
    return 0


# --- parseur -------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scope", description="Pilotage SCPI du Siglent SDS1204X-E")
    p.add_argument(
        "--socket",
        action="store_true",
        help=(
            "transport socket brut pour idn/scpi/set/screenshot/measure (sinon "
            "VXI-11, défaut). capture/series/live/gui utilisent déjà socket par "
            "défaut (cf. --vxi11) — ce flag n'a pas d'effet sur eux."
        ),
    )
    p.add_argument(
        "--usb",
        action="store_true",
        help=(
            "transport USBTMC (scope branché en USB, découvert automatiquement par "
            "VID:PID — l'IP passée en argument est ignorée). Pour idn/scpi/set/"
            "screenshot/measure : remplace VXI-11/--socket. Pour capture/series/"
            "live/gui : prioritaire sur --vxi11. Nécessite pyusb + libusb installés "
            "et les droits udev sur le périphérique (cf. docs/architecture.md). "
            "Vitesse à mesurer avec tools/profile_capture.py --usb sur ta machine "
            "avant d'en faire le défaut."
        ),
    )
    p.add_argument(
        "--vxi11",
        action="store_true",
        help=(
            "pour capture/series/live/gui uniquement : forcer VXI-11 au lieu de "
            "socket (défaut). Socket est ~30-50x plus rapide pour un fetch complet, "
            "mesuré sur matériel (~0,2-1s contre ~10s) — cf. docs/architecture.md. "
            "À utiliser si le mode socket pose problème sur ton réseau. Sans effet "
            "si --usb est aussi passé."
        ),
    )
    p.add_argument("--timeout", type=int, default=10_000, help="timeout VISA en ms")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("idn", help="lire l'identité (*IDN?)")
    sp.add_argument("ip")
    sp.set_defaults(func=cmd_idn)

    sp = sub.add_parser("scpi", help="console SCPI interactive")
    sp.add_argument("ip")
    sp.set_defaults(func=cmd_scpi)

    sp = sub.add_parser("capture", help="récupérer des waveforms -> fichiers")
    sp.add_argument("ip")
    sp.add_argument("--channels", nargs="+", default=["C1"], help="voies, ex. C1 C2")
    sp.add_argument("--outdir", default="captures", help="dossier de sortie")
    sp.add_argument("--plot", action="store_true", help="générer aussi un PNG")
    sp.add_argument("--no-show", action="store_true", help="ne pas ouvrir la fenêtre du plot")
    sp.add_argument(
        "--single",
        action="store_true",
        help="arme un trigger unique (TRMD SINGLE) et attend le déclenchement avant de capturer",
    )
    sp.add_argument(
        "--trigger-timeout",
        type=float,
        default=10.0,
        help="délai max d'attente du déclenchement en secondes, avec --single (défaut 10)",
    )
    sp.add_argument(
        "--format",
        nargs="+",
        default=["csv", "npy"],
        choices=sorted(VALID_FORMATS),
        help="formats de sortie (défaut csv npy) : csv npy npz hdf5 mat",
    )
    sp.set_defaults(func=cmd_capture)

    sp = sub.add_parser("series", help="série de captures time-lapse (expérience datée)")
    sp.add_argument("ip")
    sp.add_argument("--id", required=True, help="ID d'expérience, préfixe des fichiers")
    sp.add_argument("--rate", type=float, required=True, help="nombre de captures par --per")
    sp.add_argument(
        "--per",
        choices=sorted(series.PER_UNIT_SECONDS),
        default="minute",
        help="unité de cadence pour --rate (défaut minute)",
    )
    sp.add_argument(
        "--duration",
        required=True,
        help="durée max de la série, ex. 30m, 2h, 90s (ou un nombre nu = secondes)",
    )
    sp.add_argument("--channels", nargs="+", default=["C1"], help="voies, ex. C1 C2")
    sp.add_argument("--outdir", default="captures", help="dossier de sortie")
    sp.add_argument(
        "--format",
        nargs="+",
        default=["csv", "npy"],
        choices=sorted(VALID_FORMATS),
        help="formats de sortie (défaut csv npy)",
    )
    sp.add_argument(
        "--points",
        type=int,
        default=4000,
        help=(
            "points par capture, décimés côté client comme l'affichage GUI/live "
            "(défaut 4000) -- une capture est un instantané, pas le dump brut de "
            "la mémoire profonde (~14 Mpts, ~300 Mo/CSV)"
        ),
    )
    sp.add_argument(
        "--start",
        choices=sorted(series.VALID_START_MODES),
        default="now",
        help="mode de démarrage (défaut now)",
    )
    sp.add_argument(
        "--countdown",
        type=float,
        default=0.0,
        help="délai en secondes avant démarrage, avec --start countdown",
    )
    sp.add_argument("--threshold-channel", default="C1", help="voie surveillée, avec --start threshold")
    sp.add_argument("--threshold-level", default="1V", help="niveau de déclenchement, ex. 1V")
    sp.add_argument("--threshold-slope", default="POS", choices=sorted(control.VALID_SLOPE))
    sp.add_argument(
        "--threshold-timeout",
        type=float,
        default=60.0,
        help="délai max d'attente du seuil en secondes (défaut 60)",
    )
    sp.set_defaults(func=cmd_series)

    sp = sub.add_parser("set", help="modifier les réglages")
    sp.add_argument("ip")
    sp.add_argument("--timebase", help="base de temps, ex. 1MS")
    for ch in ("c1", "c2", "c3", "c4"):
        sp.add_argument(f"--{ch}-vdiv", help=f"volts/div {ch.upper()}, ex. 1V")
    sp.add_argument("--coupling", nargs=2, metavar=("CH", "VAL"), help="ex. C1 D1M")
    sp.add_argument("--autoset", action="store_true", help="auto setup (firmware, ASET)")
    sp.add_argument(
        "--autoscale",
        action="store_true",
        help="autoscale logiciel (volts/div + offset, cf. --autoscale-channels)",
    )
    sp.add_argument(
        "--autoscale-channels",
        nargs="+",
        help="voies à autoscaler (défaut : voies actives du scope)",
    )
    sp.add_argument("--run", action="store_true", help="démarrer l'acquisition")
    sp.add_argument("--stop", action="store_true", help="arrêter l'acquisition")
    sp.set_defaults(func=cmd_set)

    sp = sub.add_parser("measure", help="mesures automatiques (PAVA?)")
    sp.add_argument("ip")
    sp.add_argument("--channels", nargs="+", default=["C1"], help="voies, ex. C1 C2")
    sp.add_argument(
        "--params",
        nargs="+",
        default=["PKPK", "FREQ", "MEAN", "RMS"],
        help="paramètres PAVA à lire (ignoré avec --all)",
    )
    sp.add_argument("--all", action="store_true", help="lire toutes les mesures (PAVA? ALL)")
    sp.set_defaults(func=cmd_measure)

    sp = sub.add_parser("discover", help="découverte réseau du scope (scan port 5025)")
    sp.add_argument(
        "--cidr",
        help="sous-réseau à scanner, ex. 10.11.13.0/24 (défaut : interfaces locales)",
    )
    sp.set_defaults(func=cmd_discover)

    sp = sub.add_parser("screenshot", help="dump de l'écran du scope (SCDP) -> BMP")
    sp.add_argument("ip")
    sp.add_argument("--outdir", default="captures", help="dossier de sortie (si --out absent)")
    sp.add_argument("--out", help="chemin du fichier .bmp (remplace --outdir)")
    sp.set_defaults(func=cmd_screenshot)

    sp = sub.add_parser("live", help="affichage temps réel")
    sp.add_argument("ip")
    sp.add_argument("--channels", nargs="+", default=["C1"])
    sp.add_argument("--interval", type=int, default=100, help="rafraîchissement (ms)")
    sp.set_defaults(func=cmd_live)

    sp = sub.add_parser("gui", help="panneau de contrôle graphique complet")
    sp.add_argument("ip")
    sp.set_defaults(func=cmd_gui)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
