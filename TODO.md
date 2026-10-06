# TODO

## Known issues

- **Oscilloscope network freeze**: a burst of setting changes can freeze the instrument's
  network interface. The link still opens, but `*IDN?` gets no answer. Since 2026-10-06 the
  application detects it, blocks arming and logs the error, but only a **power cycle of the
  oscilloscope** recovers it (see [INSTALL.md](INSTALL.md) for the diagnostic commands). Setting
  changes are debounced (200 ms) to make it unlikely.
- **Isolated voltage jumps are flagged at the end of the run only**: during the run, such a
  capture is drawn as a normal point on the U(t) curve. The `U_saut` flag needs the following
  captures, so it appears in the synthesis, the CSV and the control sheet.
- **The control sheet (one row per capture) is produced by re-processing only**, not at the end
  of a live run. Workaround: **Re-traiter** in the Analysis tab, or
  `tools/extract_plateaux.py`.
- **Control-mode estimate needs the current to be resolved**: when the current plateau is only
  a few quantisation steps above zero, the estimate is not reliable. Plateau detection still
  works, because it falls back to the voltage channel.
- **Marginal negative plateau on weak bipolar signals**: on one real bipolar series, the
  negative voltage plateau sits only slightly above the detection threshold (≈ 24 V for a
  threshold of ≈ 21 V).
- **Live analysis requires the U and I channels to be recorded**: arming asks to check them if
  they are not.

## Done

- [x] Plateau detection independent of units and probe factors: thresholds relative to the
  measured noise, results on legacy runs unchanged capture by capture.
- [x] Oscilloscope returned to continuous acquisition (`TRMD AUTO` + `ARM`) when the recording
  starts. A threshold start left it in single-shot mode, and every capture re-read the same
  frozen trace.
- [x] Robust connection: "connected" means the instrument answers; Stop always resets the UI;
  an instrument error ends the run cleanly.
- [x] One control sheet per run with large capture numbers and red-veiled anomalies.
