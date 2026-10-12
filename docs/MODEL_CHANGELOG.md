# Model changelog

## baseline-v1.0 — 2026-10-13

**Numerical coefficients preserved from v0.2.** PROD v1.0 does not retune the forecast to match Cook, Silver Bulletin, DDHQ or conventional wisdom.

Publication/model-output additions:

- full House and Senate seat distributions;
- median and modal seats;
- 50%, 80%, 90% and 95% seat intervals;
- joint House/Senate control probabilities from the same simulations;
- current-seat net-change fields;
- race-level underlying poll records and model weights;
- immutable input-file hashes;
- race-level change fields against the previous snapshot;
- source-health states;
- run warnings for large unexplained probability movement;
- explicit `unavailable` historical-validation state for 2018/2022.

The shared/random error scales, partisan baseline, poll-weight formula, incumbency coefficients, race-poll blend and 30,000-simulation baseline are unchanged from v0.2.

## baseline-v0.2

First all-race live production baseline: 435 House districts, 2026 Senate contests, weighted generic ballot, candidate-matched race polls and correlated chamber simulations.
