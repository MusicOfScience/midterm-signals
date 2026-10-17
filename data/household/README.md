# Household module data

This directory is the governed evidence namespace for the MIDTERM SIGNALS US Household & Voter State module.

- `raw/`: immutable source payload snapshots by run date plus a last-known-good BLS cache.
- `normalized/`: schema-normalised observations; generated.
- `revisions/`: detected same-period revisions; generated.
- `manual/`: governed manual observations and the explicit provisional baseline.
- `polling/`: raw/normalised public-opinion inputs when adapters or reviewed imports are added.
- `wealth/`, `credit/`, `consumption/`: domain-specific evidence stores.
- `interpretation/`: Tier-4 policy/causal claims, kept outside empirical observations.

No file in this namespace is a numerical House/Senate forecast input. Every generated observation and state must carry `forecast_effect: "NONE"`.
