# Source status semantics

MIDTERM SIGNALS exposes source health publicly and uses the same states everywhere:

- **CURRENT** — retrieved successfully and within the source-specific freshness threshold;
- **STALE** — last-known-good observation is retained but older than the current threshold;
- **UNAVAILABLE** — no valid observation/feed is available or the adapter is not configured;
- **DEGRADED** — retrieval or validation is failing but a last-known-good deployment remains intact;
- **RESTRICTED** — access is intentionally not automated because of licensing/access restrictions.

A failed source never becomes zero. A failed refresh cannot overwrite the last healthy Cloudflare deployment because GitHub Actions commits new forecast artifacts only after build and validation succeed.

PROD v1.0 source states are machine-readable at `/data/source-status.json` after each production run.
