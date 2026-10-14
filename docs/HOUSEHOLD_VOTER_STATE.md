# US Household & Voter State module

## Purpose

The US Household & Voter State module is a governed economic-political sensor for MIDTERM SIGNALS. It measures household conditions, distribution, expectations, political attribution and electoral transmission without becoming a hidden input to the House or Senate forecast.

The core analytical question is not simply whether the US economy is “strong”. The module asks what is happening, to whom, through which transmission channel, at what speed, with what distributional effect, whether behaviour is changing, whether political attribution is changing, whether partisan loyalty is still absorbing the shock, and whether the process has become electorally consequential.

## Non-negotiable model boundary

The data flow is:

`OBSERVATIONS → DERIVED INDICATORS → ANALYTICAL STATES → POLITICAL INTERPRETATION → ELECTION INFERENCE`

Those layers remain distinct. News commentary, LLM judgment, qualitative state labels, institutional advocacy and polling interpretation do not modify numerical race probabilities.

All module observations and generated outputs carry `forecast_effect: "NONE"`. `scripts/household_state.py` hashes `public/data/forecast.json` before and after its run and fails if the file changes. A future numerical interface requires a registered model version with preregistered variables, historical data, leakage controls, functional form, coefficient estimation, calibration analysis, uncertainty treatment and governance approval.

## Source hierarchy

### Tier 1 — primary measurement

Federal Reserve Board; Federal Reserve Bank of New York; Bureau of Labor Statistics; Bureau of Economic Analysis; US Census Bureau; University of Michigan Surveys of Consumers; Conference Board Consumer Confidence Survey.

### Tier 2 — primary / high-quality public opinion

Pew Research Center; Gallup; AP-NORC; KFF; ANES; Cooperative Election Study; Ipsos KnowledgePanel; NORC AmeriSpeak; USC Understanding America Study; RAND American Life Panel.

### Tier 3 — behavioural / transactional

JPMorgan Chase Institute; Bank of America Institute; Federal Reserve Consumer Credit Panel; documented credit-bureau aggregates; public card-spending data; mortgage/auto delinquency datasets.

### Tier 4 — interpretive

Center for American Progress; Brookings Institution; Economic Policy Institute; American Enterprise Institute; Urban Institute; Harvard Joint Center for Housing Studies.

Tier-4 claims are never ground truth. `data/household/interpretation/policy_claims.json` requires the institution, claim, underlying data, causal mechanism, counterevidence, ideological/policy assumption, assessment and evidence strength to remain explicit.

The full source registry is `data/reference/household_source_registry.json`. Services without a stable redistribution-safe public feed remain `MANUAL` rather than being scraped opportunistically.

## Automated core

The initial automated adapter is the BLS public time-series API. It covers:

- CPI headline/core and selected household necessities;
- separate seasonally adjusted CPI series for momentum and unadjusted series for year-on-year/price-level comparisons;
- nominal and real earnings;
- payroll employment, unemployment, U-6, participation and employment-population ratio;
- JOLTS openings, hires, quits and layoffs/discharges.

BLS requests are chunked conservatively to stay below public-API series limits. Raw payloads are archived before normalisation. Manual primary-release fallbacks for the initial 15 October 2026 build are used only when an automated observation with the same ID is unavailable.

## State rules

### Affordability

Price-level burden and inflation momentum are stored separately. Falling inflation is not treated as restored affordability. A single extreme category cannot by itself force the national affordability state to `ACUTE`; breadth and headline momentum matter.

### Real income

Nominal earnings and real purchasing power remain separate. The initial automated state uses BLS real average hourly earnings and is therefore only moderate-confidence until broader income datasets are admitted.

### Labour market

`EMPLOYMENT RETENTION SECURITY` and `JOB MOBILITY / RE-EMPLOYMENT SECURITY` are separate states. Low unemployment alone cannot produce an overall `HEALTHY` labour-market classification. Overall classification requires unemployment plus recent payroll-growth history; mobility requires comparable JOLTS opportunity/turnover movement and can later be strengthened by NY Fed job-loss/job-finding expectations.

### K-shaped economy

A K-shaped classification cannot become evidence-derived without observations from at least two independent domains, for example spending plus credit or wealth plus sentiment.

### Partisan deflection

`BREAKING` or `BROKEN` cannot become evidence-derived from one cross-sectional poll. At least two independent Tier-1/Tier-2 high-quality sources are required unless a separately registered longitudinal-plus-cross-sectional rule is implemented. Repeated observations from the same source count once for source triangulation.

### Composites

The Household Economic Stress Composite and Political Economic Pressure Composite are descriptive only. A precise published score is withheld when evidence-derived weight coverage is below 60%; a provisional component score may be retained for diagnostic transparency. Neither composite is a forecasting coefficient.

## Freshness and revision policy

Observation freshness is:

- `FRESH`: 31 days or less;
- `RECENT`: 32–90 days;
- `AGING`: 91–180 days;
- `STALE`: over 180 days.

Reference period, fieldwork dates, publication date and retrieval timestamp remain separate fields. Annual structural datasets may remain useful while explicitly stale.

Revisable series retain the previous published value when the same reference period changes. Revision output records the initial value, latest revised value and magnitude. Historical raw observations are not silently overwritten.

## Provisional 15 October 2026 baseline

`data/household/manual/provisional_baseline_2026-10-15.json` preserves the specification’s initial labels as hypotheses. They are not observations and cannot satisfy triangulation. Fresh evidence-derived states replace them only where classification rules are met. This prevents a hand-authored baseline from acquiring false empirical authority merely because it is machine-readable.

## Machine-readable layout

Inputs and evidence:

```text
data/household/
  raw/
  normalized/
  revisions/
  manual/
  polling/raw/
  polling/normalized/
  wealth/
  credit/
  consumption/
  interpretation/
data/reference/household_source_registry.json
```

Current generated state:

```text
generated/
  household_state.json
  voter_state.json
  partisan_deflection.json
  household_dashboard.json
  contradictions.json
  watchlist.json
  source_health.json
  monthly_change_log.json
  distributional_state.json
  policy_interpretation.json
  report.md
```

Public copies are written to `public/data/household/`, with a human-readable dashboard at `/household/`.

Immutable date snapshots are written to:

```text
archive/YYYY-MM-DD/
  household_state.json
  voter_state.json
  dashboard.json
  report.md
```

## Manual observation contract

A manual observation must provide (or be normalised to) all of:

- source and source type;
- data reference period;
- fieldwork start/end where applicable;
- publication date;
- retrieval timestamp;
- geography;
- population/sample;
- methodology notes;
- freshness;
- revision status;
- transformation method;
- confidence;
- `forecast_effect: "NONE"`.

Observations that fail the contract stop the build rather than being published partially.

For subgroup analysis, `population_group` may be one of the governed groups (high-income/high-asset, middle-income, lower-income, homeowner, renter, under-35, 55+, Republican, Democrat, Independent). Unsupported groups are omitted rather than inferred from national data.

For a K-shaped observation, add a `domain` such as `spending`, `credit`, `wealth`, `housing`, `sentiment` or `labour`.

For a governed survey/panel state, add `state_contribution`; the builder de-duplicates repeated observations by source before evaluating triangulation.

## Validation

`tests/test_household_state.py` covers the model-safety and classification edge cases, including:

- freshness boundaries;
- the single-category affordability-spike guard;
- real-income classification;
- retention vs mobility separation;
- no “healthy labour market” from low unemployment alone;
- two-source requirement for partisan deflection `BREAKING/BROKEN`;
- preservation of source disagreement;
- two-domain K-shaped rule;
- composite precision withholding;
- rejection of any observation with non-`NONE` forecast effect;
- source staleness;
- BLS request chunking.

The module is also run in CI. Forecast validation remains a separate step after generation.
