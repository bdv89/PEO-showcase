"""Generate the SYNTHETIC demo series used for the showcase screenshots and tests.

Scenario (illustrative only, NOT measured data): a plasma electrolytic oxidation
(PEO) run recorded by the oscilloscope, one capture every 30 s (16 captures).

- Unipolar pulses at 150 Hz, 2.07 ms on (duty ~31 %), 28 ms window, 2001 points.
- Captures #1-#8: voltage-controlled ramp (200 -> 270 V); the current is
  erratic, as during micro-discharges.
- Captures #9-#16: the current limit is reached (I = 8.8 A) and the voltage keeps
  rising as the oxide layer grows: current-controlled.
- Capture #13: isolated voltage dip (200 V) with an unchanged current.
- Realistic scope artefacts: 8-bit quantisation (8 V and 0.2 A steps), noise,
  negative spike at every turn-off.

Same layout as a real series: ``<id>_NNNN.csv`` (time_s, sonde HT_V, I_A) and a
``<id>_meta.json`` listing the captures and their timestamps.

    python examples/make_demo_data.py
"""

import json
from pathlib import Path

import numpy as np

EXPERIMENT = "PEO_DEMO_01"
OUT = Path(__file__).parent / "demo-data" / EXPERIMENT
N_CAPTURES, PERIOD_S = 16, 30.0
FREQ_HZ, T_ON_S = 150.0, 2.07e-3
U_STEP_V, I_STEP_A = 8.0, 0.2


def levels(k: int, rng) -> tuple[float, float]:
    """(U, I) plateau levels of capture k (1-based)."""
    if k <= 8:
        return 200.0 + 10.0 * (k - 1), rng.uniform(3.0, 7.0)   # voltage-controlled ramp
    u = 285.0 + 7.0 * (k - 9)                                    # current limit reached
    return (200.0 if k == 13 else u), 8.8                        # #13: isolated voltage dip


def capture(k: int, rng) -> np.ndarray:
    t = -0.014 + 14e-6 * np.arange(2001)
    on = ((t + 0.0133) % (1 / FREQ_HZ)) < T_ON_S
    u_on, i_on = levels(k, rng)
    phase = (t + 0.0133) % (1 / FREQ_HZ)
    U = np.where(on, u_on * (1 - np.exp(-phase / 0.15e-3)), 0.0)          # RC rise
    decay = 1.0 if k > 8 else 1.25 - 0.5 * phase / T_ON_S                  # spiky current early on
    I = np.where(on, i_on * decay, 0.0)
    U += rng.normal(0, 2.0, t.size)
    I += rng.normal(0, 0.08, t.size)
    for j in np.flatnonzero(np.diff(on.astype(int)) == -1) + 1:            # turn-off spike
        U[j:j + 3], I[j:j + 3] = -60.0, -12.0
    U = np.round(U / U_STEP_V) * U_STEP_V
    I = np.round(I / I_STEP_A) * I_STEP_A
    return np.column_stack([t, U, I])


def main() -> None:
    rng = np.random.default_rng(2026)
    OUT.mkdir(parents=True, exist_ok=True)
    captures = []
    for k in range(1, N_CAPTURES + 1):
        data = capture(k, rng)
        lines = ["time_s,sonde HT_V,I_A"] + [f"{a:.9g},{b:g},{c:.3g}" for a, b, c in data]
        (OUT / f"{EXPERIMENT}_{k:04d}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        captures.append({"index": k, "timestamp": round(1000.0 + PERIOD_S * (k - 1), 3)})
    meta = {"experiment_id": EXPERIMENT, "channels": ["C2", "C3"], "rate": 2.0, "per_seconds": 60.0,
            "points": 2000, "note": "SYNTHETIC demo data (examples/make_demo_data.py), not measured",
            "captures": captures}
    (OUT / f"{EXPERIMENT}_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {N_CAPTURES} captures in {OUT}")


if __name__ == "__main__":
    main()
