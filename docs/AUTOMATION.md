# Automation

`forecast.yml` runs twice daily, on manual dispatch, and after relevant pushes to `main`. It pins the upstream input repository to one Git commit, builds the full forecast, validates numerical invariants, then commits only the derived `public/data` forecast/status/history artifacts. Derived-only commits are excluded from retriggering the forecast workflow.

`validate.yml` checks Python/JavaScript syntax and the static publication contract on every push and pull request.

`source-health.yml` checks the four public upstream input routes daily. A source failure does not mutate the forecast; it causes the forecast refresh to fail closed and leaves the last valid published snapshot intact.
