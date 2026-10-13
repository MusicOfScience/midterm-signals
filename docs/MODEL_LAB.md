# MODEL LAB

MODEL LAB is the historical evaluation and calibration subsystem for MIDTERM SIGNALS. It asks whether the frozen production probabilities behave honestly when replayed against elections whose information boundary can be reconstructed.

It is an audit system, not a tuning surface.

## The prohibition

Historical results must never silently alter the live 2026 probabilities. The official evaluation target is `baseline-v1.0-frozen`, the prospective coefficient set carried into PROD v1.0. A future model revision requires a new identifier, documented rationale and separate validation path. Historical scores for the frozen baseline remain evidence about that baseline; methodological corrections to the scored sample must be disclosed rather than silently presented as the old result.

## Admitted cycles and scoreability

Two cycles are currently admitted:

- **2018:** raw admitted corpus contains 435 House races and 35 Senate contests. The official fixed evaluation sample is **468 races at each checkpoint** after two House races, `LA-06` and `OR-03`, are excluded by the pre-outcome roster-stability gate described below.
- **2022:** House only, **416 races at each checkpoint**. Senate is explicitly unavailable because the admitted archive does not supply a sufficiently complete early race-poll stream. Missing Senate evaluation is not zero and is not silently dropped.

The 2018 correction does not delete or rewrite the raw 470-race corpus. The new movement diagnostics exposed that the archived candidate roster gained a Republican candidate late in `LA-06` and `OR-03`. In `LA-06`, the structural prior was strongly Republican throughout, yet the earlier incomplete roster caused the frozen probability code to interpret the missing Republican name as an effectively unopposed Democratic race. That is a source-completeness problem, not legitimate evidence for a 99.9% Democratic forecast.

Accordingly, official scoring now applies a fixed, outcome-independent scoreability rule before certified results are opened: a race must be present at all five fixed checkpoints and Democratic/Republican candidate **presence** must remain stable across those checkpoint rosters. If presence changes, the archive cannot safely distinguish a genuine contest-status change from an earlier source omission, so the race is excluded from every checkpoint rather than backfilled from hindsight. Candidate identity may change while party presence remains stable.

For each cycle MODEL LAB creates snapshots exactly 60, 30, 14, 7 and 1 day before Election Day.

At a cutoff:

1. only the latest race/candidate roster version whose `known_date` is on or before the cutoff is visible;
2. a poll is unavailable until its `publication_date`, or its `end_date` when no publication date is supplied;
3. the live model's generic-ballot and race-poll windows, decay, quality weighting, sponsored-poll discount, race-poll blend and uncertainty parameters are preserved;
4. structural baselines use the three presidential elections preceding the historical cycle, with the frozen 5% / 20% / 75% recency weights;
5. missing generic-ballot evidence remains missing rather than becoming neutral zero;
6. the fixed scoreability sample is frozen from predictive roster evidence;
7. predictions for every checkpoint are produced;
8. only then are certified outcome bytes opened and passed to scoring and forensic diagnostic functions.

## Fixed diagnostic contract

Diagnostic thresholds are chosen transparently and are not selected after inspecting results:

- competitiveness windows: **45–55%, 40–60%, 30–70%, 20–80%** Democratic win probability;
- safe-seat complement: probability below 20% or above 80%;
- calibration: fixed 10-percentage-point probability bins;
- strong probability movement: at least 10 percentage points;
- confident miss: the forecast gave the losing side at least 80% probability;
- historical scoreability: stable Democratic/Republican candidate presence across all five fixed checkpoint rosters.

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

The headline all-race score must not be read as a competitive-seat skill score. Safe seats are the overwhelming majority of House races and can dominate the aggregate Brier score.

The polled/unpolled comparison is explicitly **not causal**. Polling is endogenous to competitiveness: hard races are more likely to attract polls. The partition is useful for conditional model diagnostics, not as an estimate of what polling would have caused in an otherwise identical race.

MODEL LAB also publishes a paired model-component diagnostic for races with eligible race polls. It compares the published checkpoint probability with that same race's frozen structural + generic-ballot prior before the race-poll blend. Negative Brier or log-loss deltas mean the admitted race-poll component improved those paired forecasts. This is still a model-component diagnostic, not a causal claim about polling in general.

## Forecast movement

For races present in the fixed scoreable sample at every checkpoint, MODEL LAB records 60→30→14→7→1 movement. Movement is signed toward or away from the eventual winner only after predictions are frozen. The output identifies:

- average absolute movement per transition;
- counts moving toward and away from the eventual winner;
- moves of at least 10 percentage points;
- largest 7→1-day swings;
- strongest 60→1 moves toward and away from the winner;
- final confident misses;
- candidate-identity changes that occur while major-party presence remains stable.

These are forensic labels. They never feed back into the forecast.

## Cross-cycle comparison

The public artefact compares 2018 and 2022 on aggregate trajectory, competitive-race performance, calibration, polling coverage, movement and confident misses. Candidate explanations for different late-cycle behaviour are tracked with explicit epistemic states.

Currently exposed directly from the admitted replay are generic-ballot movement, polling coverage/composition, safe-seat weighting, paired race-poll contribution and late probability movement. Pollster-mix decomposition, structural-only counterfactuals and systematic poll-error decomposition remain follow-up diagnostics rather than asserted explanations.

Cross-cycle differences are descriptive. 2018 includes Senate while 2022 is House-only, the scored samples differ, and the polling environments differ, so a difference in score is not by itself a causal diagnosis.

## Corpus completeness and invariants

A replay checkpoint is not scored when any replayed race lacks an admitted outcome. Tests assert:

- the fixed checkpoint sequence;
- raw-corpus and official scored-sample denominators separately;
- the 2018 official scoreability exclusions are exactly the races caught by the general roster-presence rule, not a result-based blacklist;
- the 2022 fixed sample remains 416 and has no roster-presence exclusions;
- scoreability functions accept no result/outcome argument;
- unique race identifiers;
- calibration-bin counts summing to the scored denominator;
- polled plus unpolled counts summing to the denominator;
- scored chamber partitions summing to the denominator;
- the complete common-race movement sample;
- explicit 2022 Senate unavailability;
- results never entering `race_probability`;
- production contract-marker verification and fingerprint consistency.

## Model-contract drift guard

`scripts/model_lab.py` contains the explicit hashed evaluation contract and verifies critical markers in the production builder before scoring. The guard covers structural recency weights, incumbency, polling windows and half-lives, race-poll blending, uncertainty reduction and probability clamps.

`scripts/build_model_lab.py` is the official orchestration layer. It reuses the frozen replay and scoring functions but freezes corpus scoreability before outcome bytes are opened. It does not contain an alternative numerical forecast model.

If production-model markers change, `model_contract.state` becomes `drift_detected` and historical scoring is blocked. A changed model cannot inherit validation claims under the frozen model identifier.

## Reproducibility

The machine-readable public artefact is `public/data/model-lab.json`. It records the model contract and SHA-256 fingerprint, diagnostic contract, scoreability decisions, leakage guards, checkpoint definitions, admitted predictions, subgroup diagnostics, movement diagnostics and cross-cycle comparison. The validation workflow regenerates the artefact, runs unit/browser/accessibility/adversarial checks, and retains the generated JSON as a CI artefact for inspection.
