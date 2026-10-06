# Roadmap

What exists today is described in the [README](../README.md). The items below are the steps
envisaged to turn PEOscillo into the acquisition and analysis stage of a closed-loop,
AI-assisted PEO experimentation pipeline (see [RAISE_alignment.md](RAISE_alignment.md)).

## ONGOING — Automatically built experimental database

Characterise **each sample in a unique and traceable way** and build the experimental database
automatically from the recorded runs: every experiment linked to its analyses and to the later
characterisations of the same sample, so that **no information is lost over the years**, and
runs can be **exchanged with partners without compromise** (full context, provenance,
integrity proofs). Details and status:
[SHOWCASE.md § ONGOING](SHOWCASE.md#ongoing--an-automatically-built-experimental-database).

## Data and metadata

- **Standard metadata**: export each run as an **RO-Crate** (JSON-LD on schema.org) wrapping
  the raw captures, the experiment record and the processing provenance (W3C PROV), with
  column units described by Frictionless Table Schema / CSVW and domain terms aligned with
  EMMO. Today the same information is already stored, but in a project-specific `meta.json`.
- **Archive and synchronisation** of runs to a shared, versioned store.
- **Columnar export** (Apache Parquet) for cross-run analysis of large campaigns.

## Closing the loop

- **Decision interface**: expose the live metrics and the run summary (plateau values,
  control mode, anomalies, uncertainties) in a form a planning agent can consume, e.g. through
  the Model Context Protocol.
- **Live control-mode estimate** during the run. Today it is computed at the end, because it
  needs the neighbouring captures on both sides.
- **Supply control**: set-point and start/stop of the PEO power supply from the same station,
  with a **human approval step** before any agent-proposed run is executed.
- **Link to coating outcomes**: attach post-run measurements (thickness, porosity, hardness…)
  to the run record, which the record form already supports, to learn process → property
  relations.

## Robustness

- Automatic reconnection after a network freeze of the oscilloscope. Today the run ends
  cleanly and the application must be restarted (see [TODO.md](../TODO.md)).
- Container- or Nix-based build of the Windows bundle with pinned dependency versions.

Known issues and bugs are tracked in [TODO.md](../TODO.md).
