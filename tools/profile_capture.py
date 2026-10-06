#!/usr/bin/env python
"""Profilage de la latence d'un instantané : DESC, DAT2, décodage, écriture npy/csv.

Script autonome (hors package `scope/`) : sert uniquement à **mesurer**, pas à
optimiser (cf. `CLAUDE.md` — pas d'optim sans mesure). Objectif : savoir si le
goulot d'un instantané (bouton *Capture* de la CLI ou de la GUI) est le
transfert réseau (`WF? DAT2`), l'écriture CSV, ou le décodage.

Usage ::

    python tools/profile_capture.py 192.168.1.50 --channel C1 --points 1400 100000 0
    python tools/profile_capture.py --usb --channel C1              # scope branché en USB
    python tools/profile_capture.py 192.168.1.50 --socket            # comparer au transport socket

`--points 0` = ne touche pas à `WFSU NP` (mémoire native du scope, la plus lente).

Pour trancher entre transports (LAN VXI-11/socket vs USB), lancer ce script deux
fois de suite (même `--points`) en changeant uniquement `--socket`/`--usb` et
comparer les colonnes `desc_s`/`dat2_s` -- cf. plan « réactivité extrême »,
Phase 0.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# Rend `scope` importable en exécutant ce script directement (hors installation).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from scope import control  # noqa: E402
from scope.connection import Scope  # noqa: E402
from scope.waveform import decode, parse_descriptor  # noqa: E402


@contextmanager
def timed(label: str, results: dict):
    t0 = time.perf_counter()
    yield
    results[label] = time.perf_counter() - t0


def profile_once(scope, channel: str, npoints: int) -> dict:
    """Capture une trame en chronométrant chaque étape séparément."""
    results: dict = {"npoints_requested": npoints}
    if npoints > 0:
        control.set_waveform_points(scope, npoints)

    with timed("desc_s", results):
        desc = scope.query_block(f"{channel}:WF? DESC")
    p = parse_descriptor(desc)
    if p["count"] <= 0:
        raise ValueError(f"{channel} : acquisition vide (pas de signal/trigger)")

    with timed("dat2_s", results):
        data = scope.query_block(f"{channel}:WF? DAT2")

    with timed("decode_s", results):
        wf = decode(data, p["vdiv"], p["offset"], p["interval"], channel)

    with timed("npy_write_s", results):
        np.save("/tmp/profile_capture.npy", np.column_stack([wf.time, wf.volts]))

    with timed("csv_write_s", results):
        with open("/tmp/profile_capture.csv", "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["time_s", f"{channel}_volt"])
            writer.writerows(zip(wf.time.tolist(), wf.volts.tolist()))

    results["n_points_actual"] = len(wf.volts)
    return results


def _print_table(rows: list[dict]) -> None:
    cols = ["npoints_requested", "n_points_actual", "desc_s", "dat2_s", "decode_s", "npy_write_s", "csv_write_s"]
    widths = {c: max(len(c), *(len(f"{r[c]:.4g}" if isinstance(r[c], float) else str(r[c])) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        cells = [f"{r[c]:.4g}" if isinstance(r[c], float) else str(r[c]) for c in cols]
        print("  ".join(cell.ljust(widths[c]) for cell, c in zip(cells, cols)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ip", nargs="?", help="ignorée avec --usb")
    ap.add_argument("--channel", default="C1")
    ap.add_argument("--socket", action="store_true")
    ap.add_argument(
        "--usb",
        action="store_true",
        help="transport USBTMC (scope branché en USB, découvert par VID:PID) au lieu du LAN",
    )
    ap.add_argument(
        "--points",
        type=int,
        nargs="+",
        default=[1400, 100_000, 0],
        help="valeurs WFSU NP à tester (0 = ne pas régler, mémoire native)",
    )
    args = ap.parse_args(argv)

    if not args.usb and not args.ip:
        ap.error("ip requise sauf avec --usb")

    rows = []
    with Scope(args.ip, socket=args.socket, usb=args.usb) as scope:
        for n in args.points:
            print(f"-- points={n} --", file=sys.stderr)
            rows.append(profile_once(scope, args.channel, n))

    _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
