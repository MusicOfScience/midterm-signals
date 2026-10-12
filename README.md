# MIDTERM SIGNALS

Open, auditable probabilistic analysis for the **2026 United States midterm elections** on **3 November 2026**.

**Live site:** https://midterm-signals.pages.dev

## Production baseline

MIDTERM SIGNALS v0.2 publishes a live numerical baseline for **all 435 House races** and every 2026 Senate contest. It produces race-level Democratic/Republican win probabilities, predicted two-party vote shares, chamber seat distributions, control probabilities, tipping-point races, battleground rankings and immutable forecast history.

The numerical pipeline consumes four public input tables from the `ElectIndex/26_us_forecast_data` repository: current race/candidate definitions, historical presidential results on the 2026 district map, generic-ballot polls and race polls. Every refresh pins those inputs to one upstream Git commit and records a combined SHA-256. MIDTERM SIGNALS does **not** consume that repository's forecast outputs or code.

## Model contract

The v0.2 baseline combines:

- district/state partisan lean from 2016, 2020 and 2024 presidential results, centred on the national result;
- a recency-, quality- and sample-weighted 35-day generic congressional ballot;
- a modest incumbency term;
- nominee-matched race polling from the last 55 days when available;
- 30,000 Monte Carlo chamber simulations with correlated national error.

Raw observations, polling aggregation, election forecasting, third-party forecasts, qualitative campaign/news intelligence, scenarios and actual results remain separate. **Qualitative text and LLM judgement cannot silently alter numerical probabilities.**

This is a transparent baseline, not an oracle. Candidate-quality effects beyond incumbency, third-party/RCV transfer behaviour and several structural variables remain candidates for separately validated future model versions rather than hidden hand-tuning.

## Automation

`.github/workflows/forecast.yml` refreshes twice daily and on relevant pushes. It builds and validates the forecast, then commits only derived JSON artifacts. Cloudflare Pages deploys `public/` automatically from `main`.

```bash
python scripts/build_forecast.py
python scripts/validate_forecast.py
node scripts/check.mjs
```

## Repository layout

```text
scripts/build_forecast.py      numerical model + pinned public inputs
scripts/validate_forecast.py   fail-closed numerical invariants
public/data/forecast.json      current production snapshot
public/data/history/           immutable timestamped snapshots
public/data/status.json        publication/run metadata
public/                        static Cloudflare Pages application
.github/workflows/             validation + scheduled forecast refresh
```

## Deployment

Cloudflare Pages production branch: `main`; output directory: `public`; no build command is required.
