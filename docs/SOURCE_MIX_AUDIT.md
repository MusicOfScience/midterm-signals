# Pollster and source-mix audit

This diagnostic is an evaluation layer for the frozen `baseline-v1.0-frozen` MIDTERM SIGNALS model. It does not alter live or historical forecast probabilities.

## Question

PR #10 established that final 2022 House race polling had higher mean absolute error and lower winner-call accuracy than 2018, without a comparably large uniform partisan bias. This audit asks whether that extra dispersion is concentrated in observable characteristics of the admitted polling stream.

It does **not** assume that a pollster or source characteristic causes error. Competitive and difficult races attract polling non-randomly, so every comparison here is descriptive.

## Pre-specified source features

All band assignments are made from polling metadata before certified election margins are joined.

### Polling depth

Fixed bands:

- 1 eligible poll;
- 2 eligible polls;
- 3–4 eligible polls;
- 5 or more eligible polls.

### Unique pollsters

Fixed bands:

- 1 pollster;
- 2 pollsters;
- 3 or more pollsters.

Repeated polls from the same pollster do not become multiple independent sources.

### Weighted source concentration

For every race/checkpoint, the audit reconstructs the exact production poll weights. Poll weights are summed within pollster and converted to shares of the race-poll aggregate.

- `single_source`: one pollster supplies all eligible polling;
- `concentrated_multi`: more than one pollster, but the largest source supplies at least two-thirds of exact poll weight;
- `diversified_multi`: more than one pollster and the largest source supplies less than two-thirds.

The two-thirds threshold was fixed before reviewing results.

The audit also reports a Herfindahl-Hirschman-style concentration index, the sum of squared pollster weight shares, as a continuous descriptive quantity.

### Partisan-labelled source share

The historical poll corpus contains a `lean` field. Only explicit `D` or `R` values are classified as partisan-labelled.

`N` and blank values mean **not labelled partisan in the admitted corpus**. They are not asserted to be substantively neutral.

The fixed categories are:

- no partisan-labelled poll weight;
- mixed partisan-labelled and unlabelled poll weight;
- all poll weight partisan-labelled.

### Pollster race-source table

A pollster may have repeated polls in the same race. Those are first combined using the exact production poll weighting, producing one pollster/race/checkpoint signal.

Pollster metrics are published only when a pollster has at least **5 distinct race-source observations** at the selected checkpoint. This threshold was fixed before results were examined.

Pollsters are ordered by sample size and then name. They are **never ranked by error**, which avoids turning a small observational audit into a misleading league table.

## Polling mode is unavailable

The admitted historical files do not contain a reliable polling-mode field. The audit therefore marks mode decomposition as `unavailable_not_in_historical_corpus`. It does not infer mode from pollster names, external memory, or post-hoc lookup.

A future mode analysis would require a separately admitted, provenance-controlled metadata source.

## Exact reconstruction guard

For every scored race/checkpoint the sidecar reconstructs the exact production race-poll eligibility and weighting rules:

- publication/as-of gate;
- 55-day race-poll window;
- candidate matching;
- 13-day half-life;
- quality, sample-size and sponsor weighting;
- freshness adjustment to blend weight.

The diagnostic fails if reconstructed poll count, latest poll date, blend weight, or raw weighted poll margin differs from the already-frozen historical prediction.

## Outcome boundary

Source profiles are built first. Certified D/R result margins are joined only afterward for scoring.

Missing certified D/R margins remain missing and are excluded from margin-error scoring rather than imputed as zero.

## Metrics

For each source band the audit reports the same-race:

- raw poll mean absolute error (MAE);
- raw poll mean signed error, Democratic minus Republican;
- raw poll root mean squared error (RMSE);
- winner-call accuracy;
- frozen prior and full-model margin error for context;
- mean poll count;
- mean unique pollster count;
- mean largest-source weight share;
- source concentration index;
- partisan-labelled weight share.

Positive signed error means the polling signal was too Democratic; negative means too Republican.

## Interpretation boundary

This audit can establish that error is associated with sparse polling, concentrated sources, partisan-labelled source share, or particular pollsters in the admitted sample. It cannot by itself establish that those characteristics caused the error.

Race selection, competitiveness, geography, candidate quality, turnout, electorate change, survey mode and other unobserved factors can confound the comparisons.

No result from this audit may alter the frozen production model without a separately specified future model version and prospective validation plan.
