# MIDTERM SIGNALS

MIDTERM SIGNALS is an open, auditable election-analysis and probabilistic forecasting project for the 2026 United States midterm elections on **3 November 2026**.

Production site: https://midterm-signals.pages.dev

## Product contract

The project visibly separates:

1. facts/raw observations;
2. polls;
3. polling aggregates;
4. MIDTERM SIGNALS model estimates;
5. third-party forecasts;
6. qualitative campaign signals;
7. user scenarios;
8. actual results.

Qualitative news or LLM judgement never silently changes numerical probabilities. Missing observations are never converted to zero. Failed refreshes do not destroy the last healthy deployment.

## PROD v1.0

The v1.0 public application adds an integrated Forecast Centre, House/Senate centres, deep race pages, Race Explorer, accessible race grid, Polling Centre, global search, candidate pages, Campaign Signals boundary, FEC/money boundary, Scenario Lab, Build Your Own Election, immutable forecast history, source health, provenance and layered methodology.

The official numerical baseline preserves the v0.2 prospective coefficients. v1.0 expands outputs and transparency rather than retuning to external conventional wisdom.

## Local checks

```bash
npm test
python -m py_compile scripts/build_forecast.py scripts/validate_forecast.py
```

A networked production refresh is run by GitHub Actions:

```bash
python scripts/build_forecast.py
python scripts/validate_forecast.py
```

## Key public files

- `public/data/forecast.json`
- `public/data/races.csv`
- `public/data/polls.csv`
- `public/data/source-status.json`
- `public/data/history/`
- `docs/METHODOLOGY.md`
- `docs/DATA_PROVENANCE.md`
- `docs/MODEL_CHANGELOG.md`
- `docs/SOURCE_STATUS.md`

Historical Brier/log-loss metrics for 2018/2022 are intentionally unavailable until leakage-free retrospective replays exist.
