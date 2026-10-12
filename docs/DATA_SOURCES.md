# Data sources and provenance

The v0.2 production baseline reads four public, machine-readable input files from `ElectIndex/26_us_forecast_data`:

- `races.csv` — current 2026 House/Senate race definitions, candidates, incumbency and ballot structure;
- `historical.csv` — 2016/2020/2024 presidential results mapped onto the 2026 districts/states;
- `gcb_polls.csv` — generic congressional ballot observations;
- `race_polls.csv` — race-specific polling observations.

At the start of each run MIDTERM SIGNALS resolves the upstream `main` branch to an exact Git commit SHA and performs all four reads against that immutable SHA. The combined raw bytes are hashed and written into `forecast.json`/`status.json`.

The upstream repository is used as a curated **input mirror**. MIDTERM SIGNALS does not import its forecast probabilities, Monte Carlo results or model code. Numerical transformations are defined in this repository.

This architecture is deliberately replaceable: source-specific adapters can later promote primary FEC, Census, official candidate/ballot and pollster releases while preserving the same provenance contract.
