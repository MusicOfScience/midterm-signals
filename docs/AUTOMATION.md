# Automation

`validate.yml` runs on push and pull request. It rebuilds the deterministic forecast from checked-in inputs, validates numerical invariants, runs static checks and fails if regenerated forecast artifacts differ from those committed.

`publish-derived.yml` runs when model/input files change. It builds and validates the forecast, then commits changed `public/data` artifacts with the GitHub Actions bot. Its paths filter prevents a derived-only bot commit from recursively retriggering itself.

`source-health.yml` runs daily and performs conservative HTTP availability checks against public source routes. It does **not** alter numerical inputs. Reachability is not evidence that a number changed; parser/source failure must never mutate the forecast.

Until stable licensed machine-readable ingestion is promoted, new numerical observations enter through dated reviewed snapshots. Future adapters must preserve fetch → snapshot → validate → parse → diff → publish gates.
