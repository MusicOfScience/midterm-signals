# MODEL LAB

MODEL LAB is the historical evaluation and calibration subsystem for MIDTERM SIGNALS. Its purpose is to answer a hard question honestly: when this model assigns a probability, how should that probability be interpreted empirically?

It is an audit system, not a tuning surface.

## The prohibition

Historical results must never be used to silently alter the live 2026 probabilities. The official baseline remains the v0.2 prospective coefficient set preserved in PROD v1.0. Model Lab evaluates that contract. A future model revision must receive a new model identifier, a documented change rationale and a separate validation path.

## Replay protocol

For each admitted historical cycle, MODEL LAB creates snapshots at exactly 60, 30, 14, 7 and 1 day before Election Day.

At a cutoff:

1. only the latest race/candidate roster version whose `known_date` is on or before the cutoff is visible;
2. a poll is unavailable until its `publication_date`, or its `end_date` when no publication date is supplied;
3. the live model's generic-ballot and race-poll windows, decay, quality weighting, sponsored-poll discount, race-poll blend and uncertainty parameters are preserved;
4. structural baselines use the three presidential elections that preceded the historical cycle, with the same 5% / 20% / 75% recency weights;
5. missing generic-ballot evidence remains missing rather than becoming a neutral zero;
6. outcomes are loaded only after replay predictions exist and are passed only to scoring functions.

## Corpus completeness

Scoring a subset can create a flattering answer accidentally or deliberately. For that reason, a replay checkpoint is not scored when any replayed race lacks an admitted outcome. The public artefact reports the blocking reason rather than dropping the race silently.

The 2018 and 2022 corpus directories are intentionally present before their data are admitted. Their `cycle.json` manifests currently declare `awaiting_verified_inputs`. That state is a feature: it makes the absence of leakage-free evidence visible and machine-readable.

## Diagnostics

For each complete checkpoint MODEL LAB computes:

- **Brier score**: mean squared error of the Democratic win probability against the binary result. Lower is better.
- **Log loss**: mean negative log likelihood. It imposes a much larger penalty on confident errors.
- **Reliability / calibration bins**: average forecast probability versus observed Democratic win rate within probability bands.
- **Calibration intercept and slope**: logistic recalibration diagnostics. An ideal calibrated system is near intercept 0 and slope 1. These diagnostics are descriptive only and are never fed back into the production model.
- **Forensic misses**: wrong-side calls ranked by the eventual winner's forecast probability, so confident failures are inspectable rather than buried.
- **Forecast evolution**: race probability at every admitted checkpoint.

## Model-contract drift guard

`scripts/model_lab.py` contains an explicit, hashed evaluation contract and verifies critical markers in the production builder before scoring. The guard covers structural recency weights, incumbency, polling windows and half-lives, race-poll blending, uncertainty reduction and probability clamps.

If those production markers change, `model_contract.state` becomes `drift_detected` and historical scoring is blocked. This prevents a changed model from inheriting old validation claims under the same label.

## Public states

- `unavailable`: corpus or provenance gates are not satisfied; no performance claim is made.
- `partial`: at least one checkpoint is valid but the cycle is not complete.
- `scored`: every fixed checkpoint has a complete replay and complete outcomes.

Top-level Model Lab remains `unscored` until at least one cycle is genuinely scored. The public UI is designed to explain this state rather than replace it with placeholder metrics.

## Reproducibility

The machine-readable public artefact is `public/data/model-lab.json`. It records the model contract, its SHA-256 fingerprint, the leakage guards, checkpoint definitions, cycle states and, when admitted, predictions and diagnostics. The builder is standard-library Python and the metric functions have known-vector tests.
