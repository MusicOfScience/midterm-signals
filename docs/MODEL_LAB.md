# MODEL LAB

MODEL LAB is the historical evaluation and calibration subsystem for MIDTERM SIGNALS. It asks whether the frozen production probabilities behave honestly when replayed against elections whose information boundary can be reconstructed.

It is an audit system, not a tuning surface.

## The prohibition

Historical results must never silently alter the live 2026 probabilities. The official evaluation target is `baseline-v1.0-frozen`, the prospective coefficient set carried into PROD v1.0. A future model revision requires a new identifier, documented rationale and separate validation path. Historical scores for the frozen baseline remain immutable evidence about that baseline.

## Admitted cycles

Two cycles are currently admitted:

- **2018:** House and Senate, 470 races at each of the five fixed checkpoints.
- **2022:** House only, 416 races at each checkpoint. Senate is explicitly unavailable because the admitted archive does not supply a sufficiently complete early race-poll stream. Missing Senate evaluation is not zero and is not silently dropped.

For each cycle MODEL LAB creates snapshots exactly 60, 30, 14, 7 and 1 day before Election Day.

At a cutoff:

1. only the latest race/candidate roster version whose `known_date` is on or before the cutoff is visible;
2. a poll is unavailable until its `publication_date`, or its `end_date` when no publication date is supplied;
3. the live model's generic-ballot and race-poll windows, decay, quality weighting, sponsored-poll discount, race-poll blend and uncertainty parameters are preserved;
4. structural baselines use the three presidential elections preceding the historical cycle, with the frozen 5% / 20% / 75% recency weights;
5. missing generic-ballot evidence remains missing rather than becoming neutral zero;
6. predictions for every checkpoint are produced before outcome bytes are opened;
7. outcomes are then passed only to scoring and forensic diagnostic functions.

## Fixed diagnostic contract

Diagnostic thresholds are chosen transparently and are not selected after inspecting results:

- competitiveness windows: **45–55%, 40–60%, 30–70%, 20–80%** Democratic win probability;
- safe-seat complement: probability below 20% or above 80%;
- calibration: fixed 10-percentage-point probability bins;
- strong probability movement: at least 10 percentage points;
- confident miss: the forecast gave the losing side at least 80% probability.

The competitiveness windows are deliberately nested. Their counts therefore do not sum. The 20–80 window plus its safe-seat complement does form a complete partition and is validated as such.

## Diagnostics

Every scored checkpoint publishes:

- **Brier score** and **log loss**;
- **winner-call accuracy** as a secondary descriptive metric;
- mean Democratic probability and actual Democratic win rate;
- signed calibration error;
- fixed-bin reliability data including sample size and calibration residual;
- count-weighted mean absolute bin calibration error;
- logistic calibration intercept and slope;
- the fixed competitiveness-window metrics;
- eligible race-level **polled versus unpolled** partitions;
- **House versus Senate** partitions where admitted;
- wrong-side calls and confident misses.

The polled/unpolled comparison is explicitly **not causal**. Polling is endogenous to competitiveness: hard races are more likely to attract polls. The partition is useful for conditional model diagnostics, not as an estimate of what polling would have caused in an otherwise identical race.

## Forecast movement

For races present at every fixed checkpoint, MODEL LAB records 60→30→14→7→1 movement. Movement is signed toward or away from the eventual winner only after predictions are frozen. The output identifies:

- average absolute movement per transition;
- counts moving toward and away from the eventual winner;
- moves of at least 10 percentage points;
- largest 7→1-day swings;
- strongest 60→1 moves toward and away from the winner;
- final confident misses.

These are forensic labels. They never feed back into the forecast.

## Cross-cycle comparison

The public artefact compares 2018 and 2022 on aggregate trajectory, best Brier checkpoint, final-week Brier movement, race-poll coverage and confident misses. Candidate explanations for the different late-cycle behaviour are tracked with explicit epistemic states.

Currently exposed directly from the admitted replay are generic-ballot movement, polling coverage/composition, safe-seat weighting and late probability movement. Pollster-mix decomposition, structural-only counterfactuals and systematic poll-error decomposition remain follow-up diagnostics rather than asserted explanations.

Cross-cycle differences are descriptive. 2018 includes Senate while 2022 is House-only, and the polling environments differ, so a difference in score is not by itself a causal diagnosis.

## Corpus completeness and invariants

A replay checkpoint is not scored when any replayed race lacks an admitted outcome. Tests assert:

- the fixed checkpoint sequence;
- the 2018 and 2022 scored denominators;
- unique race identifiers;
- calibration-bin counts summing to the scored denominator;
- polled plus unpolled counts summing to the denominator;
- scored chamber partitions summing to the denominator;
- the complete common-race movement sample;
- explicit 2022 Senate unavailability;
- results never entering `race_probability`;
- production contract-marker verification and fingerprint consistency.

## Model-contract drift guard

`scripts/model_lab.py` contains an explicit hashed evaluation contract and verifies critical markers in the production builder before scoring. The guard covers structural recency weights, incumbency, polling windows and half-lives, race-poll blending, uncertainty reduction and probability clamps.

If those production markers change, `model_contract.state` becomes `drift_detected` and historical scoring is blocked. A changed model cannot inherit validation claims under the frozen model identifier.

## Reproducibility

The machine-readable public artefact is `public/data/model-lab.json`. It records the model contract and SHA-256 fingerprint, diagnostic contract, leakage guards, checkpoint definitions, admitted predictions, subgroup diagnostics, movement diagnostics and cross-cycle comparison. The builder is standard-library Python and the validation workflow regenerates the artefact before unit and browser tests.
