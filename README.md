# MIDTERM SIGNALS

Open, auditable probabilistic analysis for the **2026 United States midterm elections** on **3 November 2026**.

**Live site:** https://midterm-signals.pages.dev

## Current forecast

Model **v0.1** is an operational, provisional production baseline using a dated **12 October 2026** evidence snapshot.

The published system includes House expected/median seats and control probability; Senate expected/median Democratic-caucus seats and control probability; correlated joint-control probabilities; all 435 House seats in chamber arithmetic; the 76 non-Solid House races as explicit map priors; all 35 Senate contests; polling observations, provenance, uncertainty intervals and immutable forecast history.

The model is intentionally explicit about its remaining limitation: this is **not yet the final district-level backtested model**. See `docs/MODEL.md` and `docs/BACKTESTING.md`.

## Analytical contract

MIDTERM SIGNALS keeps raw observations, polling aggregation, election forecasting, third-party analysis, qualitative campaign/news intelligence, scenarios and actual results separate. Qualitative text and LLM judgement cannot silently alter numerical probabilities.

Additional rules: reproducible inputs and deterministic model runs; explicit provenance and hashes; immutable published snapshots; no hidden manual probability adjustments; no retuning because an output feels surprising; missing observations remain missing; failed fetches create source-health information rather than fabricated observations; no paywall bypassing or reproduction of subscriber-only material.

## Reproduce

Requires Python 3.12+ and Node 22+; there are no third-party runtime packages.

```bash
python scripts/build_forecast.py
python scripts/validate_forecast.py
node scripts/check.mjs
```

or `npm test`.

## Deployment

Cloudflare Pages deploys `public/` from production branch `main` with no build command. The numerical model is rebuilt and validated in GitHub Actions; derived artifacts are committed before the production UI consumes them.

## Source boundary

Current inputs use public snapshots from Track the Vote, public Cook Political Report ratings pages and public U.S. House historical election statistics. MIDTERM SIGNALS does **not** automate scraping Cook or reproduce subscriber-only analysis. See `docs/DATA_SOURCES.md`.
