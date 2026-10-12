# MIDTERM SIGNALS methodology — PROD v1.0

## 30-second version

MIDTERM SIGNALS estimates every 2026 House and Senate contest from a recent-election partisan baseline, the national generic congressional ballot, incumbency and qualifying current race polls. It converts expected two-party margins into race probabilities, then runs correlated Monte Carlo simulations to estimate chamber control and seat distributions.

Qualitative campaign news and LLM interpretation do **not** silently alter numerical probabilities.

## Five-minute version

1. **Partisan baseline.** Each district/state is centred relative to the national presidential vote using 5% of 2016, 20% of 2020 and 75% of 2024. This is the prospectively registered v0.2 baseline and is preserved in v1.0.
2. **National environment.** A 35-day generic-ballot average uses exponential recency decay, sample-size weighting, the upstream source-quality field and a downweight for partisan-sponsored polls.
3. **Incumbency.** House incumbency contributes ±1.0 point. Senate incumbency uses 1.15× that adjustment.
4. **Race polling.** Candidate-matched race polls from the previous 55 days are blended with the prior. Weight grows sub-linearly with poll count, is capped and decays with staleness. Missing race polling stays missing.
5. **Race probability.** Expected margin is converted through a normal-error model. Poll evidence can narrow race uncertainty within documented bounds.
6. **Chamber simulation.** 30,000 simulations include a shared national House error, a shared national Senate error and race-specific error, so many races can move together.
7. **Provenance.** Every production run pins the upstream repository to one commit and records SHA-256 hashes for all input files.

## Technical specification

The production implementation is `scripts/build_forecast.py`. The official v1.0 model keeps the v0.2 numerical coefficients and error scales rather than retuning them to match external forecasters.

### Structural lean

For each district/state:

`relative_lean = 0.05*(2016 margin - national 2016 margin) + 0.20*(2020 margin - national 2020 margin) + 0.75*(2024 margin - national 2024 margin)`

The current national generic-ballot margin and incumbency adjustment are added to form the prior.

### Poll aggregation

Poll weight is proportional to:

- exponential recency decay;
- square-root sample-size scaling;
- the upstream quality field;
- a 0.68 multiplier for partisan-sponsored polls.

The national half-life is 11 days. Race polls use 13 days and must match current major-party nominees.

### Correlated simulation

The production chamber simulation uses:

- House shared national error: σ = 2.7 points;
- Senate shared national error: σ = 2.4 points;
- House race-specific error: σ = 4.7 points;
- Senate race-specific error: σ = 5.0 points;
- deterministic RNG seed `20261103` for reproducible builds.

This is a deliberately simple correlation structure, not a full geographic covariance matrix.

## Nowcast vs election-day forecast

PROD v1.0 exposes both concepts but does not invent a separate time-evolution process. The current production baseline represents election-outcome uncertainty under today’s measured environment. Until a prospectively specified time-evolution component exists, the nowcast and election-day central environment remain the same and this limitation is stated in the UI.

## Historical validation

2018 and 2022 Brier score, log loss, calibration, seat-count error and interval coverage are **unavailable** pending leakage-free retrospective reconstruction. No metric is manufactured from data that may include future information.
