# MIDTERM SIGNALS — Polling Error Audit

## Purpose

This diagnostic separates three quantities that were previously entangled in Model Lab:

1. the race-poll margin actually available to the frozen model at a checkpoint;
2. the certified Democratic-minus-Republican two-party election result margin;
3. the margin published by the frozen MIDTERM SIGNALS model after blending the poll signal with its structural + generic-ballot prior.

It is an evaluation system only. It does not tune, recalibrate, override or otherwise change `baseline-v1.0-frozen`.

## Information boundary

Historical checkpoint forecasts and the official scoreability sample are frozen before certified result margins are opened.

The diagnostic reconstructs the race-poll aggregate by calling the same frozen replay function used by the model. That means it preserves the same:

- as-of publication-date gate;
- 55-day race-poll window;
- candidate matching rule;
- 13-day poll half-life;
- pollster-quality weight;
- sample-size weight;
- partisan-sponsor discount;
- freshness adjustment; and
- frozen race-poll blend calculation.

For every included race, the diagnostic asserts that reconstructed poll count, latest poll date and blend weight match the already-frozen checkpoint prediction. A mismatch is a failure, not an invitation to substitute a different polling aggregate.

Only after that reconstruction is fixed does the diagnostic read the separately admitted certified result margin.

## Certified result-margin sidecar

`historical/2018/result-margins.csv` and `historical/2022/result-margins.csv` are evaluation-only outcome files.

Their admission is governed by `scripts/admit_result_margins.py` and the manually dispatched `result-margin-admission.yml` workflow. Normal forecast refresh and validation runs do not fetch the external result sources.

### 2018

The sidecar uses the same pinned MIT Election Data and Science Lab constituency-return sources already recorded in the admitted 2018 cycle manifest. Source bytes are SHA-256 checked before normalization.

Candidate/fusion lines are collapsed within a race and Democratic and Republican votes are summed. Where the historical MEDSL file has an unusable party label, a D/R identity may be inherited only from an unambiguous pre-election roster match or from an identity fallback already admitted and recorded in the 2018 cycle manifest. No new outcome-derived party guess is permitted.

All 470 admitted 2018 result rows have a numeric D/R result margin in the sealed sidecar.

### 2022

The sidecar uses the pinned Federal Election Commission `Federal Elections 2022` workbook and its House-results sheet already admitted in the 2022 cycle manifest. The workbook is SHA-256 checked before normalization.

All 435 House districts must be classified by the FEC source. A numeric two-party result margin is emitted only when both Democratic and Republican certified vote totals exist. If either side is absent, the margin is explicitly unavailable rather than being treated as zero, ±100 by convention, or inferred from the winner.

The sealed admission currently contains:

- 397 numeric D/R result margins;
- 38 explicitly unavailable D/R margins; and
- 435 total FEC districts accounted for.

This distinction is deliberate: missing is not zero.

## Margin definitions

All margins are expressed in percentage points as Democratic minus Republican two-party margin.

`result margin = 100 × (D votes − R votes) / (D votes + R votes)`

`poll error = raw poll aggregate margin − certified result margin`

Therefore:

- positive poll error means the admitted poll aggregate was too Democratic;
- negative poll error means it was too Republican.

The principal magnitude measures are mean absolute error (MAE) and root mean squared error (RMSE). Winner-side call accuracy is shown only as a secondary descriptive measure.

## Same-race decomposition

For every eligible race the audit compares:

1. **Raw race-poll aggregate** — the exact frozen as-of weighted poll margin before the model blend.
2. **Structural + generic-ballot prior** — the frozen prior margin before race polling.
3. **Published full-model margin** — the frozen blended margin.
4. **Certified result margin** — opened only for evaluation after the first three quantities exist.

`Δ full − poll MAE` is the full-model absolute margin error minus the raw-poll absolute margin error on the same races.

- Negative: the frozen blend improved on the raw polling signal.
- Positive: the frozen blend made the margin estimate worse than the raw polling signal.

The corresponding full-versus-prior delta tests whether the full model improved on its no-race-poll prior.

## Scope

The diagnostic includes only races that:

- are in the pre-outcome Model Lab scoreability sample;
- have both a Democratic and Republican candidate in the frozen checkpoint roster;
- have at least one eligible race-level poll under the frozen replay rules; and
- have a lawfully admitted numeric certified D/R result margin.

A polled race without a lawful certified D/R margin is listed as missing from margin scoring and is not assigned a synthetic result margin.

For cross-cycle comparison, the primary one-day comparison is House-only because the 2022 admitted archive does not support an equivalent Senate replay.

## What this can and cannot establish

This audit can establish whether the admitted race-poll stream was, on average, too Democratic or too Republican at a checkpoint, how large its margin errors were, and whether the frozen model blend reduced or amplified those errors on the same races.

It cannot by itself establish *why* the polling error occurred. Pollster composition, mode, likely-voter screens, turnout assumptions, non-response, late campaign movement and other mechanisms require separate diagnostics.

The repository therefore treats `systematic_polling_error` as **diagnostic exposed**, not causally identified.

## Prohibited uses

The historical findings from this audit must not be used to:

- retune the live model because one historical cycle looks worse;
- apply a hidden partisan correction;
- alter the poll half-life, blend scale or uncertainty parameters post hoc;
- select a flattering historical subset using election outcomes; or
- silently impute missing certified margins.

Any future model change would require its own prospective rationale and versioned model contract. This audit has `model_effect: NONE`.
