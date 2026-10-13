# Data sources

MIDTERM SIGNALS keeps numerical election inputs separate from contextual/external data.

## Numerical forecast inputs

The production baseline reads four public, machine-readable input files from `ElectIndex/26_us_forecast_data`:

- `races.csv` — current 2026 House/Senate race definitions, candidates, incumbency and ballot structure;
- `historical.csv` — 2016/2020/2024 presidential results mapped onto the 2026 districts/states;
- `gcb_polls.csv` — generic congressional ballot observations;
- `race_polls.csv` — race-specific polling observations.

At the start of each run MIDTERM SIGNALS resolves the upstream `main` branch to an exact Git commit SHA and performs all four reads against that immutable SHA. The combined raw bytes are hashed and written into `forecast.json`/`status.json`.

The upstream repository is used as a curated **input mirror**. MIDTERM SIGNALS does not import its forecast probabilities, Monte Carlo results or model code. Numerical transformations are defined in this repository.

## External forecasters

Third-party forecasts are a separate comparison layer and never alter MIDTERM SIGNALS probabilities.

- **Inside Elections** — native 2026 House/Senate ratings are imported from the public JSON API links exposed by its ratings pages. Native labels are preserved. A failed refresh may retain the last-known-good snapshot as `STALE`.
- **Cook Political Report** — `RESTRICTED`: MIDTERM SIGNALS does not automate or redistribute Cook ratings without a licensed feed/API arrangement.
- **Sabato's Crystal Ball** — `MANUAL`: the public source is linked, but no redistribution-safe machine feed is currently configured.
- **Silver Bulletin** — `RESTRICTED`: subscriber/licensing boundary; no paywall bypass, scraping or reconstructed forecast is permitted.
- **Decision Desk HQ** — `MANUAL`: public forecast pages are linked, but no undocumented scraping/API use is performed.

The external-forecaster source catalogue and any redistributable native ratings are published at `/data/external-forecasters.json`.

## Federal Election Commission

Campaign finance is sourced from the **official FEC current-campaign House/Senate bulk files**. This adapter does not require a private API credential and does not affect the numerical forecast.

Candidate matching is conservative: state, chamber/district, party and candidate-name evidence must agree. Ambiguous candidates remain unmatched rather than guessed. Every dollar record carries its coverage-through date, and the UI warns when candidates in the same race have mismatched reporting periods.

Machine-readable FEC adapter output is published at `/data/fec.json`.

## Campaign signals

`/data/signals.json` is a structured election-intelligence layer. Current automated signal types include:

- recent production generic-ballot and race-poll observations (`MODEL EFFECT: POLL INPUT` because those quantitative observations are already consumed by the documented poll model);
- external rating changes (`MODEL EFFECT: NONE`);
- official FEC reporting summaries (`MODEL EFFECT: NONE`);
- candidate-roster changes detected between immutable production snapshots (`MODEL EFFECT: NONE`).

Signal text is descriptive metadata derived from structured records. It is not an LLM adjustment layer and cannot silently change probabilities.

## Adapter contract

This architecture remains deliberately replaceable: source-specific adapters can promote more primary/authoritative feeds while preserving the same provenance contract. The absence of a legally redistributable or reliable source is preferable to fabricated, scraped-behind-access-control, or silently inferred data.
