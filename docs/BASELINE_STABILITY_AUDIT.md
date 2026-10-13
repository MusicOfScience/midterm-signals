# MIDTERM SIGNALS — Structural baseline stability audit

## Purpose

This audit asks a narrower question than “did redistricting break the model?”:

> Were the three pre-election presidential relative leans used by the frozen structural model internally stable, and did model error concentrate where that history was unstable?

The audit is evaluation-only. It cannot alter `baseline-v1.0-frozen`, any replayed probability, or the live 2026 forecast.

## Why this is not a redistricting indicator

For 2022, the admitted structural pipeline does **not** carry old congressional district identifiers forward and pretend they are the new map. It reconstructs 2012, 2016 and 2020 presidential vote on the 118th-Congress district geography by joining block-level election data to the U.S. Census Bureau 118th Congressional District Block Equivalency File.

Relevant official Census references:

- https://www.census.gov/geographies/mapping-files/2023/dec/rdo/118-congressional-district-bef.html
- https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.118th_Congress.html

The repository admission path is `scripts/admit_historical_2022.py::strict_structural_priors`.

That means a simple old-map/new-map identifier mismatch is already guarded against. A district can still have a structurally unstable history because of partisan realignment, demographic change, candidate-independent geographic change, imperfect historical comparability, or other non-stationarity. This diagnostic measures that instability; it does not assign its cause.

## Pre-outcome stability measure

For each admitted House district, define three presidential **relative leans**:

`district Democratic-minus-Republican margin - national Democratic-minus-Republican margin`

using the three presidential elections admitted for that cycle:

- 2018 replay: 2008, 2012, 2016;
- 2022 replay: 2012, 2016, 2020.

The stability statistic is the range of those three relative leans:

`max(relative lean) - min(relative lean)`

Smaller values mean the district's presidential structural history was more internally stable.

## Fixed bands

Bands are fixed before outcomes are consulted:

- **0–5 pp**: stable;
- **>5–10 pp**: moderate instability;
- **>10–15 pp**: high instability;
- **>15 pp**: very high instability.

The standing high-instability threshold is **>10 percentage points**.

These are diagnostic thresholds, not model coefficients.

## Sample

The audit is House-only and requires both a Democratic and Republican candidate in the admitted fixed replay sample. No-opponent races are excluded so production's mechanical 0.001/0.999 branches cannot dominate the comparison.

The stability band is assigned without election outcomes. Certified results are then used only to score:

1. the frozen structural + incumbency probability; and
2. the published full forecast probability

inside each already-assigned stability band.

## Published outputs

At every 60/30/14/7/1-day checkpoint the Model Lab JSON exposes:

- denominator by stability band;
- mean relative-lean range;
- mean absolute earliest-to-latest structural trend;
- structural-stage Brier score, log loss and winner-call accuracy;
- published full-forecast Brier score, log loss and winner-call accuracy;
- full-minus-structural Brier delta;
- fixed-80% confident miss counts at the structural and full stages;
- the most unstable admitted district histories.

## Interpretation boundary

Evidence that error increases with structural instability supports the claim that **baseline non-stationarity is a model-risk factor**.

It does **not** by itself support the stronger claim that redistricting caused the error.

A causal or descriptive redistricting-specific audit would require a separately admitted, pre-specified boundary-change/comparability variable, such as population-weighted overlap between predecessor and successor districts. That measure must be defined without using election outcomes and must never be used to retune the frozen model merely because a historical result looks surprising.

## Model effect

`NONE`
