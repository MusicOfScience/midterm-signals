# MIDTERM SIGNALS

Open, auditable analysis infrastructure for the **2026 United States midterm elections** on **3 November 2026**.

MIDTERM SIGNALS separates six layers that are often blurred together in election coverage:

1. raw observations;
2. polling aggregation;
3. election forecasting;
4. third-party forecaster consensus;
5. qualitative campaign/news intelligence;
6. scenarios and actual results.

Qualitative text and LLM judgement must never silently change numerical forecast probabilities.

## Current publication state

The public front end is live-capable, but the **production forecast remains withheld** until verified 2026 inputs, model-specification acceptance and historical replay gates are complete. Missing observations are never filled with invented values or treated as zero.

## Local preview

```bash
python -m http.server 8000 --directory public
```

Then open `http://localhost:8000`.

## Cloudflare Pages

This repository is configured as a static Cloudflare Pages project.

- Build command: none required
- Output directory: `public`
- Production branch: `main`

Or deploy with Wrangler after authenticating Cloudflare:

```bash
npx wrangler pages deploy public --project-name midterm-signals
```

## Repository layout

```text
public/                 static application
  data/status.json      machine-readable publication state
.github/workflows/      validation workflow
docs/                   architecture and deployment notes
wrangler.toml           Cloudflare Pages configuration
```

## Analytical contract

- Reproducible inputs and model runs.
- Explicit provenance for material observations.
- Immutable historical snapshots.
- No hidden manual probability adjustments.
- No retuning merely because a result seems surprising.
- Facts, estimates, external forecasts, scenarios and results remain visibly distinct.
- Failed fetches create source-health information, not fabricated observations.
- Paywalls and access controls are never bypassed.

The data pipeline and forecasting engine will be added behind these publication gates rather than faking a production forecast before the evidence is ready.
