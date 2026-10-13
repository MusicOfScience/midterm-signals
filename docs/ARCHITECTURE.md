# Architecture — PROD v1.0

MIDTERM SIGNALS keeps the v0.2 static architecture because it is appropriate for a public election reference and Cloudflare Pages deployment.

## Data/model layers

1. raw/public observations;
2. normalised polling observations;
3. polling aggregates;
4. MIDTERM SIGNALS model estimates;
5. third-party forecast adapters;
6. qualitative Campaign Signals;
7. user-created scenarios / Build Your Own Election;
8. actual results.

These layers are never silently merged.

## Build path

`GitHub Actions -> scripts/build_forecast.py -> validation -> immutable snapshot + current artifacts -> Git commit -> Cloudflare Pages`

Cloudflare receives a complete static publication bundle. Python is not required at request time.

## Front-end

The public application is dependency-light ES modules plus semantic HTML/CSS. It provides:

- a global search command interface;
- integrated route views;
- deep race/candidate/pollster pages;
- Race Explorer with shareable URL filters;
- accessible national race grid;
- Polling Centre;
- Forecast Centre and history;
- Scenario Lab and Build Your Own Election;
- data/source/provenance surfaces.

Competitive race, candidate and pollster routes are statically generated for indexable deep links. Interactive state remains client-side and never writes to the official forecast.
