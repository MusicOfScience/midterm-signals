# Historical validation / backtesting

The project reserves infrastructure for leakage-free replay and scoring but does not claim 2018 or 2022 validation metrics yet.

Required future replay discipline:

- reconstruct only information genuinely available at each historical forecast timestamp;
- pin historical poll/race metadata vintages;
- run the contemporaneous model version without post-election edits;
- store replay manifests and hashes;
- score Brier, log loss, calibration, seat error and interval coverage only after reconstruction passes leakage review.

Until then the public Model Health view reports those metrics as **unavailable**, not zero and not estimated from hindsight-contaminated data.
