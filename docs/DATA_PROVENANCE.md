# Data provenance

Every production forecast records four questions at the point of use:

1. **Where did this come from?**
2. **When was it retrieved/published?**
3. **How was it transformed?**
4. **Which model version used it?**

## Production quantitative input mirror

Current numerical runs consume the public `ElectIndex/26_us_forecast_data` GitHub repository. Each run first resolves `main` to an immutable commit SHA, then fetches:

- `races.csv`
- `historical.csv`
- `gcb_polls.csv`
- `race_polls.csv`

The model stores the upstream commit, one SHA-256 hash per file, a combined input SHA-256 and the retrieval timestamp in `public/data/forecast.json`.

MIDTERM SIGNALS consumes factual/curated election inputs from that repository, not another forecast probability series.

## Derived public data

The production run emits:

- `/data/forecast.json` — complete current model snapshot;
- `/data/races.csv` — race-level model outputs;
- `/data/polls.csv` — public poll observations used by the current adapter;
- `/data/source-status.json` — source-health states;
- `/data/search.json` — navigation index;
- `/data/history/index.json` and timestamped snapshots;
- `/data/run-report.json` — run checks/warnings.

## External forecasters

Cook Political Report, Inside Elections, Sabato’s Crystal Ball, Silver Bulletin and Decision Desk HQ are separate external forecast layers. PROD v1.0 does not claim licensed automated access. Their adapters remain explicitly `unavailable` until a legally permitted feed or documented manual import exists.

No mathematically meaningless cross-forecaster probability average is created.

## FEC

The FEC is the intended authoritative campaign-finance source. PROD v1.0 has the schema/UI boundary but no configured current API feed, so money is shown as `unavailable`, never zero.

## Qualitative signals

Campaign Signals is a separate data layer. The default model effect is `NONE`. A signal can affect the numerical forecast only if a future model version explicitly consumes a documented quantitative variable.

## Results

Results are a separate post-election layer. No live result is implied until an authoritative/licensed adapter is configured. The final pre-election forecast archive must remain immutable after observed results arrive.
