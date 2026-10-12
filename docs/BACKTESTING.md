# Backtesting status

Model v0.1 has a coarse national House seat-vote calibration but **has not yet completed full historical district-level replays**. That limitation is published in the UI and forecast JSON.

The current baseline is allowed to publish because the model is simple, versioned, deterministic and its uncertainty is explicit. It should not be described as fully calibrated.

The next validation tranche should freeze historical district universes, race ratings/polls at fixed pre-election cutoffs and Senate candidate/rating/poll states, then score Brier score, log loss, calibration, seat-distribution coverage and chamber-control accuracy. No parameter should be retuned merely because 2026 outputs look surprising.
