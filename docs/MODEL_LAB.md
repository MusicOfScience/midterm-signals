# MODEL LAB

MODEL LAB is the historical evaluation and calibration subsystem for MIDTERM SIGNALS. Its purpose is to answer a hard question honestly: when this model assigns a probability, how should that probability be interpreted empirically?

It is an audit system, not a tuning surface.

## The prohibition

Historical results must never be used to silently alter the live 2026 probabilities. The official baseline remains `baseline-v1.0-frozen`, the prospective coefficient set preserved in PROD v1.0. Model Lab evaluates that contract. A future model revision must receive a new model identifier, a documented change rationale and a separate validation path.

## Replay protocol

For each admitted historical cycle, MODEL LAB creates snapshots at exactly 60, 30, 14, 7 and 1 day before Election Day.

At a cutoff:

1. only the latest race/candidate roster version whose `known_date` is on or before the cutoff is visible;
2. a poll is unavailable until its `publication_date`, or its `end_date` when no publication date is supplied;
3. the live model's generic-ballot and race-poll windows, decay, quality weighting, sponsored-poll discount, race-poll blend and uncertainty parameters are preserved;
4. structural baselines use the three presidential elections that preceded the historical cycle, with the same 5% / 20% / 75% recency weights;
5. missing generic-ballot evidence remains missing rather than becoming a neutral zero;
6. outcomes are loaded only after replay predictions exist and are passed only to scoring functions.

## Admitted historical scope

Two cycles are currently admitted and scored under the frozen contract:

- **2018:** 435 House races and 35 Senate contests, scored at all five checkpoints.
- **2022:** House-only. The fixed admitted sample is 416 House races at every checkpoint. Nineteen House races remain explicit scoreability exclusions. The 35 Senate contests are unavailable for scoring because the admitted retrospective Senate poll stream is not complete enough at the early checkpoints.

Missing chamber evidence is always reported as unavailable, never zero.

## Corpus completeness

Scoring an opportunistic subset can produce a flattering answer accidentally or deliberately. A replay checkpoint is therefore not scored when any race in its fixed admitted sample lacks an admitted outcome. Race identifiers are canonicalized before scoreability, and checkpoint sample denominators are invariants.

Historical results are outcome labels only. They are opened after checkpoint predictions have been generated and may not enter predictive code or the model contract.

## Fixed diagnostic contract

Diagnostic thresholds are fixed before inspecting their results. They are not model coefficients and do not change the live forecast.

### Competitive-seat windows

The public artefact reports four nested probability windows using Democratic win probability: 45–55%, 40–60%, 30–70% and 20–80%. It also reports the complement outside 20–80% as `safe-outside-20-80`. Because the competitive windows are nested, their counts are not additive. The 20–80 window plus its safe complement must equal the full scored checkpoint denominator.

For each fixed window MODEL LAB reports n, Brier score, log loss, winner-call rate, mean Democratic probability, actual Democratic win rate and calibration error.

### Calibration

Reliability uses fixed 10-percentage-point probability bins. Empty bins are omitted from display, but every scored race must belong to exactly one occupied bin and the bin counts must sum to the checkpoint denominator. For each occupied bin the artefact records the mean forecast probability, actual Democratic win frequency, n and calibration residual (`actual - forecast`).

The existing logistic calibration intercept and slope are retained. Ideal values are 0 and 1 respectively. Small-sample instability is exposed through n rather than hidden by adaptive binning.

### Polled versus unpolled

At every checkpoint races are partitioned by whether at least one eligible race-level poll contributes to that race at that cutoff. Both subsets receive the same proper-score and calibration summary. This is a conditional comparison, **not a causal A/B test**: races are polled partly because they are competitive.

Forecast movement is also partitioned by polling status at the later checkpoint of each transition. Those movement partitions must sum to the common race sample.

### Forecast movement

For races present at all five checkpoints, MODEL LAB measures movement across 60→30, 30→14, 14→7 and 7→1 days. Certified outcomes are used only after probabilities are frozen to give movement a forensic sign: positive movement is toward the eventual winner, negative movement is away.

A **strong move** is fixed at 10 percentage points. A **confident miss** is a wrong-side call where the model assigned at least 80% to the losing side. These thresholds are diagnostic only.

### Chamber scope

House and Senate metrics are computed separately whenever an admitted complete chamber replay exists. The 2022 Senate state remains explicitly unavailable. No metric silently drops missing chamber evidence.

### Cross-cycle comparison

Cross-cycle output is descriptive, not causal. The artefact reports aggregate trajectory, competitive-seat performance, polling partitions, calibration, confident misses and both 14→1 and true final-week 7→1 Brier changes. Candidate explanations such as late generic-ballot movement, polling composition, pollster mix, redistricting priors, systematic polling error and late overreaction remain hypotheses unless the admitted evidence identifies them.

## Model-contract drift guard

`scripts/model_lab.py` contains an explicit, hashed evaluation contract and verifies critical markers in the production builder before scoring. If those production markers change, `model_contract.state` becomes `drift_detected` and historical scoring is blocked.

## Public states

- `unavailable`: corpus or provenance gates are not satisfied; no performance claim is made.
- `partial`: at least one checkpoint is valid but the cycle is not complete.
- `scored`: every fixed checkpoint has a complete replay and complete outcomes.

## Reproducibility

The machine-readable public artefact is `public/data/model-lab.json`. It records the model contract and fingerprint, diagnostic thresholds, leakage guards, checkpoint definitions, cycle states, fixed predictions and all derived diagnostics. Tests assert fixed denominators, calibration-bin counts, polled/unpolled and chamber partitions, all-checkpoint movement samples and contract integrity.
