# Structural-stage audit

This document defines the evaluation-only structural decomposition used by MIDTERM SIGNALS Model Lab.

## Question

The 2022 historical replay contains several confident misses, including multiple post-redistricting California House seats. That makes structural-prior quality a legitimate audit hypothesis. It does **not** make redistricting an established cause.

The audit therefore asks a narrower question first:

> On the same frozen races, how much forecast skill came from the structural baseline, the generic ballot, and the race-poll layer?

No result from this audit may change `baseline-v1.0-frozen`, the 2026 live probabilities, or any production coefficient.

## Three frozen stages

For each scored checkpoint, the diagnostic carries the same eligible race through three stages:

1. **Structural + incumbency**: the admitted presidential relative-lean baseline plus the frozen incumbency term.
2. **Structural + generic ballot**: the production prior immediately before the race-poll blend.
3. **Published full forecast**: the checkpoint probability produced by the frozen model, including any eligible race-poll blend and associated uncertainty reduction.

The historical replay already stores `prior_margin`, which equals structural + incumbency + checkpoint generic-ballot margin. The diagnostic reconstructs the first stage as:

`structural_incumbency_margin = prior_margin - checkpoint_generic_ballot_margin`

It then converts that margin to probability using the same frozen chamber-level unpolled sigma and probability clamp.

This is a downstream evaluation calculation. It introduces no new historical input into the forecast.

## Fixed sample rules

The structural decomposition is evaluated only on races that:

- already passed the cycle-wide pre-outcome scoreability gate;
- have certified Democratic/Republican outcomes in the admitted result file; and
- contain both a Democratic and Republican candidate in the frozen checkpoint prediction.

No-opponent and same-party mechanics are intentionally kept out of this decomposition. Otherwise the production 0.001/0.999 branches could make the structural baseline look artificially strong without testing the geographic prior at all.

Two views are published:

- **all two-major-party contests**;
- **structural 20–80%**, a fixed competitive subset selected using the structural-stage Democratic probability before later information is added.

The 20–80 threshold was fixed before reviewing the resulting component scores.

## Metrics

Each stage is scored with:

- Brier score;
- log loss;
- winner-call accuracy.

For the same sample, Model Lab also publishes:

- `generic minus structural` score deltas;
- `full minus structural+generic` score deltas;
- `full minus structural` total deltas;
- mean winner-directed probability movement from the generic-ballot stage;
- mean winner-directed probability movement from the race-poll stage;
- confident structural misses using the already-fixed 80% confidence threshold.

Negative Brier/log-loss deltas mean the later stage improved the same frozen race sample. Positive deltas mean it degraded it.

## Leakage boundary

Certified outcomes are opened only after the replay probabilities and cycle scoreability sample have been frozen by the Model Lab builder. The structural decomposition uses outcomes solely for scoring and winner-directed forensic labels.

It does not read post-election district characteristics, certified vote margin, retrospective polling-error fields, or hindsight classifications when constructing any stage probability.

## What this can and cannot establish

The decomposition can establish whether the admitted structural component was materially stronger or weaker than later model stages in 2018 and 2022, including on structurally competitive races and among confident structural misses.

It **cannot**, by itself, establish that redistricting caused any structural weakness. A causal redistricting test would require a separately admitted, pre-specified measure of district-boundary change or baseline comparability that does not use election outcomes to define the subset.

Until such a source and rule are admitted, the project state remains:

**structural component exposed; redistricting not identified.**
