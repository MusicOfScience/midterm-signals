# Historical replay corpus

This directory is the admission boundary for MIDTERM SIGNALS Model Lab.

Historical performance is **not** reconstructed from final-cycle files. A cycle may be scored only when we can establish what the model could have known at each checkpoint without future information leaking backwards.

## Required files per cycle

Each `historical/<year>/` directory contains `cycle.json` plus, once verified, three source tables:

- `races.csv` — versioned race/candidate roster. Every row needs `race_code`, `race_type`, `known_date`, candidate fields, incumbent party and the three cycle-appropriate presidential baseline margins (`margin_earliest`, `margin_middle`, `margin_latest`). Multiple rows for one race are allowed; Model Lab selects the latest version whose `known_date` is on or before the replay cutoff.
- `polls.csv` — both generic-ballot and race polls. `kind` is `generic_ballot` or `race`; rows carry `end_date` and preferably `publication_date`. If a publication date exists, it controls availability. Race polls also carry `race_code`, candidate names and the same poll metadata used by the live model.
- `results.csv` — `race_code,winner_party` with winner party `DEM` or `REP`. This file is scoring-only. It is deliberately loaded after replay predictions are generated and is never accepted by a modelling function.

## Five fixed checkpoints

Replays are generated at 60, 30, 14, 7 and 1 day before Election Day. Missing input is never converted to zero. A checkpoint without eligible generic-ballot evidence remains unscored.

## Frozen contract

Model Lab evaluates the v0.2 prospective coefficients preserved in PROD v1.0. It must not use historical results to tune those coefficients. The builder checks critical production implementation markers before it will score a cycle; model drift blocks scoring until it is explicitly reconciled.

## Admission standard

Before changing a cycle from `awaiting_verified_inputs`, provenance must document the origin, retrieval path, licensing/redistribution basis, coverage and any transformation applied to each source. Structural presidential baselines must be cycle-appropriate and have been known before that election. Final candidate rosters may not be treated as if they were known months earlier.

A beautiful backtest built from future knowledge is still leakage. We publish no Brier score until the corpus clears these gates.
