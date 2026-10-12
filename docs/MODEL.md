# MIDTERM SIGNALS model v0.1

**Status:** published provisional baseline  
**Snapshot:** 2026-10-12  
**Election:** 2026-11-03

Model v0.1 is deliberately compact: it gets a reproducible baseline into production without smuggling judgement into probabilities.

## House

Eight post-1990 midterms provide a coarse calibration between national Democratic-minus-Republican House vote margin and Democratic seats: `D seats = alpha + beta × D-R margin + residual error`. Coefficients are fitted from `data/reference/house_midterm_calibration.json`. The current generic ballot is treated as a noisy proxy for eventual national House vote margin with a predeclared 3-point standard deviation.

The current-map leg translates public rating categories to fixed priors: Solid D 99.5%, Likely D 90%, Lean D 70%, Toss Up 50%, Lean R 30%, Likely R 10%, Solid R 0.5%. Its draw has an 8-seat standard deviation.

The chamber forecast is `0.65 × national vote-to-seat draw + 0.35 × current-map draw`. Weights are versioned and are not changed because an output is aesthetically surprising. House race rows in the UI are **categorical map priors**, not individualized district polling probabilities.

## Senate

Each of 35 contests gets a categorical rating prior. Where public polling exists, the Democratic polling margin is converted through a Normal distribution with a 5-point effective margin-error scale; poll evidence weight rises slowly with poll count and is capped at 0.65; prior and poll evidence are combined on the log-odds scale:

`p = logistic[(1-w) × logit(prior) + w × logit(poll evidence)]`

Senate errors share a national latent component with `rho = 0.20`; local error remains dominant. The same national shock affects the House generic-ballot draw, giving joint-control simulations correlated election conditions.

There are 34 Democratic-caucus and 31 Republican seats not up. Democrats need 51 because a 50-50 Senate is treated as Republican control under the Republican vice president's tie-breaking vote. Nebraska independent Dan Osborn receives a published non-Republican upset probability but **zero Democratic-control credit** absent a documented caucus/organization commitment.

## Excluded from v0.1

LLM judgement; qualitative campaign/news text; presidential approval as a numerical input; hidden manual probability adjustments; fundraising/candidate-quality scores; proprietary subscriber-only narrative analysis.

## Reproducibility and next tranche

`python scripts/build_forecast.py` is deterministic for the same input files, seed and model version and stores SHA-256 input hashes. `python scripts/validate_forecast.py` fails on invalid universes, probabilities, hashes or publication rules.

v0.1 is an operational baseline, not the finished system. Priority upgrades are licensed/public district polling with transparent pollster weighting; candidate/incumbency and fundraising inputs; redistricting-adjusted district baselines; full historical district-level replays/calibration; formal model-version comparison before coefficient changes.
