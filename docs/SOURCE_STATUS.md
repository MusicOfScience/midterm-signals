# Source status semantics

MIDTERM SIGNALS exposes source health publicly and keeps operational failures distinct from deliberate access/licensing boundaries.

- **CURRENT** — retrieved successfully and within the source-specific freshness threshold;
- **STALE** — last-known-good observation is retained but older than the current threshold;
- **UNAVAILABLE** — no valid observation/feed is currently available;
- **DEGRADED** — retrieval or validation is failing but a last-known-good deployment remains intact;
- **RESTRICTED** — automation/redistribution is intentionally not performed because of licensing, subscription or access restrictions;
- **MANUAL** — a public source is tracked and linked, but production ingestion remains an explicit manual/import boundary until a documented redistribution-safe machine source is available.

`RESTRICTED` and `MANUAL` are **access constraints, not data-pipeline failures**. The public health indicator therefore reports stale/unavailable/degraded operational data separately from known manual/licensing boundaries.

A failed source never becomes zero. Where an adapter has a defensible last-known-good record, that record can remain visible as `STALE` with its original timestamp. Failed refreshes cannot overwrite the last healthy Cloudflare deployment because GitHub Actions commits new publication artifacts only after build and validation succeed.

The current production source states are machine-readable at `/data/source-status.json`. External-forecaster details are additionally published at `/data/external-forecasters.json`; official FEC adapter output at `/data/fec.json`; and structured campaign signals at `/data/signals.json`.
