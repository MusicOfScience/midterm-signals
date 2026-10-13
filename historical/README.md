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

## 2022 admitted House replay

The 2022 House corpus is admitted on a **fixed 416-race sample** at all five checkpoints. Nineteen House districts are excluded rather than approximated; all 35 Senate races remain unscored because the admitted retrospective Senate poll stream does not reach the early replay checkpoints.

The generic-ballot input is the pinned 5 November 2022 pre-election snapshot only. Its latest admitted poll ended on 4 November. The replay retains the frozen model's 35-day generic-ballot window instead of imposing a hindsight-only requirement for an election-eve poll.

Structural priors reconstruct 2012, 2016 and 2020 presidential two-party margins on 2022 congressional boundaries. Two source failures remain explicit in the scoreability ledger: Montana lacks a recoverable 2012 presidential layer on 2020 blocks, and the pinned New Jersey DRA block-data URL is unavailable. Those gaps exclude affected races; they do not trigger statewide or adjacent-geography substitutions.

Certified outcomes come from the Federal Election Commission's *Federal Elections 2022* workbook, pinned by SHA-256. Outcome data are fetched only after predictive inputs and scoreability decisions have been constructed. Fusion-party ballot lines are collapsed to the certified candidate before the final Democratic/Republican control outcome is assigned.

The first admitted replay scores are:

| Days before election | Brier | Log loss | N |
| ---: | ---: | ---: | ---: |
| 60 | 0.03320394 | 0.10876627 | 416 |
| 30 | 0.03159977 | 0.10479628 | 416 |
| 14 | 0.03099197 | 0.10139739 | 416 |
| 7 | 0.03178037 | 0.10222631 | 416 |
| 1 | 0.03305647 | 0.10467615 | 416 |

These all-race scores are not, by themselves, evidence that the model is well calibrated in competitive seats. Safe and deterministic districts dominate the House universe. Competitive-subset, probability-band and polled-versus-unpolled diagnostics should be read alongside the headline scores before drawing conclusions about forecast skill.
