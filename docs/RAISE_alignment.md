# Alignment with HORIZON-RAISE-2027-01-01 — Automated Scientific Discovery

This page maps the call's expectations onto **what this repository already does**, with the
file that proves it, and **what is planned**. It deliberately separates the two: everything in
the *Today* column can be checked in the code and its tests.

PEOscillo is one component of Materia Nova's lab-retrofit approach: existing instruments are
kept, and are driven, read and analysed through vendor-neutral, open-source software instead
of closed vendor tools.

## Where PEOscillo sits in the closed loop

```
 plan ──► execute ──► acquire & document ──► process & analyse ──► decide ──► (next run)
  ▲       (PEO power    (PEOscillo: drive the    (PEOscillo: plateaux,   (AI planning layer,
  │        supply)       oscilloscope, record,    control mode,           human review)
  │                      trace, verify)           anomalies — live)              │
  └───────────────────────────────────────────────────────────────────────────────┘
```

PEOscillo covers the **acquire & document** step and the **process & analyse** step for the
electrical signature of a PEO run. It produces, at every capture, the quantities a decision
layer needs.

## Mapping

| Call expectation | Today (in this repository) | Planned (project) |
|---|---|---|
| **Intelligence layer** that lets instrumentation plan, run and **analyse** experiments semi- or fully autonomously | Unattended recording: the run starts on the process itself (hardware trigger on the voltage), captures at a fixed cadence, analyses each capture as it arrives, and summarises the run (control mode, anomalies) at the end — `scope/series.py`, `scope/plateaux.py` | Expose the run summary and live metrics to a planning agent (e.g. through the Model Context Protocol, as in Materia Nova's analysis tool *Plotter*); agent-proposed set-points |
| **Retrofit** an existing lab without redesigning it | A standard oscilloscope already on the bench becomes the recorder; pure-Python VISA (no vendor runtime), LAN or USB — `scope/connection.py`; the PEO supply is not modified | Direct control of the PEO power supply (set-point, start/stop) |
| **Comprehensive data management**: collection, storage, processing, sharing | Each run is a self-contained folder: raw CSV per capture and one `meta.json` with the experiment record, timestamps, instrument settings, results and attachments — `scope/experiment.py`, `scope/series.py` | **Ongoing**: experimental database built automatically from the runs, each sample uniquely and traceably identified, experiments linked to their analyses over the years; exchange with partners without loss of context (RO-Crate, see ROADMAP) |
| **Efficient (near-)real-time processing and analysis** | Every capture analysed in the acquisition thread as soon as it is recorded; live analysis tab — `scope/gui.py` (`LiveAnalysis`); analysis measured at ~2 ms per 2000-point capture | Live control-mode estimate (today: end of run) |
| **Reproducibility** | Algorithm version (hash of the analysis code) and parameters recorded with each analysis; re-processing of any run with the current algorithm; results pinned capture by capture in the test suite — `scope/experiment.py`, `tests/` | — |
| **Data integrity and provenance** | SHA-256 checksums of every raw file; re-processing refuses modified files and never writes into raw data; edit history (who, when, before, after) — `scope/experiment.py` | Signed archives |
| **Human oversight and interaction** | Incomplete experiment record highlighted during the run; one control sheet per run to validate every capture visually; anomalies flagged, never silently dropped — `scope/gui.py`, `scope/plateaux.py` | Approval step before an agent-proposed run reaches the supply |
| **Intuitive user interfaces** | Desktop GUI with readable instrument settings, record form, live analysis; zero-install Windows bundle — `scope/gui.py`, `packaging/` | — |
| **Interoperability standards and protocols** | Open formats (CSV, JSON); SCPI over standard VISA transports | Common exchange format with partner labs |
| **Security and robustness by design** | Arming blocked until the instrument answers; lost link or instrument error ends the run cleanly (data kept); time-stamped error log; fully tested without hardware (simulated instrument, real GUI) — `launcher.py`, `tests/test_gui_window.py` | — |
| **Transfer to other disciplines** | Plateau detection is unit- and probe-independent (thresholds relative to measured noise); any pulsed electrochemical process with voltage/current probes fits (anodising, pulsed plating) | Documented reuse cases |
| **Priority on software development** | Fully open-source software stack (Python), Apache 2.0 | — |

## Flagship scientific case

**Electrical signature of PEO coating growth.** In PEO, the transition from a
voltage-controlled to a current-controlled regime, the evolution of the plateau voltage and the
occurrence of anomalies reflect the growth and breakdown of the oxide layer. These signatures
are usually watched on a screen and lost. PEOscillo records them with their full context, and
turns each run into time series of plateau voltage, current, frequency and control mode. These
are the observables a planning layer needs to relate process parameters (bath, set-point,
waveform) to coating outcomes.

## Licensing

Released under the **[Apache License 2.0](../LICENSE)**: permissive, with an explicit patent
grant, so partners, other labs and industry can reuse and integrate the code. The Materia Nova
name, logo and visual identity are not covered (see [NOTICE](../NOTICE)).
