# Polling sparsity × race-difficulty audit

## Question

PR #11 showed that the 2022 House polling stream was much thinner than 2018: far more races had only one eligible poll or one eligible pollster. This audit asks whether that sparsity was disproportionately concentrated in races the frozen model already regarded as difficult before race polls were blended.

This is an evaluation-only diagnostic. It does not change `baseline-v1.0-frozen`, any coefficient, or any historical/live forecast probability.

## Pre-specified race difficulty

Race difficulty is defined from the **absolute structural+generic pre-poll prior margin** at the checkpoint. Certified results and race-poll error are forbidden from defining the bands.

Fixed bands:

- `≤5 pp`
- `>5–10 pp`
- `>10–20 pp`
- `>20 pp`

The headline interaction uses a fixed `10 pp` cut:

- prior-competitive: absolute pre-poll prior margin `≤10 pp`
- prior-noncompetitive: `>10 pp`

## Pre-specified sparsity

Two separate sparsity definitions are tested:

1. **poll sparsity**: exactly one eligible race poll versus two or more;
2. **source sparsity**: exactly one eligible pollster versus two or more.

Eligibility and weighting are inherited from the frozen model/source-mix audit: publication/as-of eligibility, 55-day window, candidate matching, 13-day half-life, quality/sample/sponsor weighting and freshness-adjusted blend.

## Geography

Geography is assigned solely from the state code in `race_code`, using fixed Census-style regions:

- Northeast
- Midwest
- South
- West

Geography is descriptive. No region is created, merged or split based on forecast error.

## Outcomes and leakage boundary

The pipeline order is:

1. reconstruct the exact eligible polling stream;
2. assign poll/source sparsity;
3. assign pre-poll prior-difficulty band;
4. assign geographic region;
5. only then join separately admitted certified D/R result margins;
6. score raw-poll, prior and full-model margin error.

Missing certified margins remain missing. They are never treated as zero.

## Interpretation boundary

A finding that sparse competitive races have larger error does **not** prove another poll would have caused a better estimate. Competitive races may be systematically harder to poll; geography, electorate change, survey mode and campaign effects may confound the relationship.

The diagnostic can support or weaken a **coverage/composition** explanation. It cannot estimate a causal treatment effect of adding polls.

## Model effect

`NONE`.
