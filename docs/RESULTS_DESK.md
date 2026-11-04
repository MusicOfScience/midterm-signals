# MIDTERM SIGNALS — 2026 Results Desk (v1)

Public route: https://midterm-signals.pages.dev/results/

## Purpose

Build a mobile-friendly, searchable index covering the 435 US House contests
and the 35 Senate contests in the MIDTERM SIGNALS pre-election model. Contrast
**observations** with the original **forecast** without changing either.

## Data and terms

- **Primary public source:** The People's Tally, https://thepeoplestally.com/open-data/
  (CC BY 4.0, attribution required). The publisher attributes observed counts
  to state election offices and race calls to named external call services.
  Returns may remain unofficial until certified by states.
- **Provider endpoint:** https://thepeoplestally.com/data/results.json
- **Normalised same-origin snapshot:** public/data/observed-results.json
- **Frozen model:** public/data/history/2026-11-03T192932Z.json, created
  3 November 2026 at 19:29:32 UTC. Never backfill observed outcomes into it.
- Secondary source (browser display only): official state election offices via
  Open America, https://openamerica.io/elections/api/ (22 states at initial
  publication; explicit partial coverage, no race calls). The source permits
  direct browser display with attribution; its live feed is NOT repackaged as
  a GitHub-hosted results service.
- GitHub Action runs the People's Tally public-source adapter every 10 minutes while enabled.
  A browser may refresh direct from the public source if CORS is available;
  failed or empty direct fetches never erase the last checked snapshot.
- The source's election-night update cadence does not guarantee complete
  coverage. There is no AP/DDHQ commercial feed or claim of national completeness.

## Semantic safeguards

1. **No votes** is not a zero-vote return. The former is represented as null
   in the UI. A provider-supplied race at zero votes may exist in the JSON but
   is presented as awaiting votes.
2. **Counting leader** is not a **called winner**. A call is displayed only
   when the source marks a winning candidate AND names a caller.
3. Districts and states never mix: House is congressional-district level;
   Senate is statewide. A Senate special and regular contest sharing a state
   are explicitly marked ambiguous instead of being silently merged.
4. **Observed D−R** is 100×(D votes − R votes)/(D votes + R votes), only
   when both parties appear in the candidate list and the denominator is positive.
   Third-party votes are excluded from this two-party statistic.
5. **Gap** is observed two-party D−R minus frozen predicted D−R, in percentage
   points. It is PROVISIONAL during counting; it is not necessarily a swing
   from 2024, and is not a completed forecast-error measure.
6. No live results ever change the forecast model, seat-control simulations,
   polling aggregates or the frozen historical archive.
7. Calls for contested Senate races are not chamber control: 2026 Senate
   holdover seats remain a separate accounting problem.
8. Upstream feed failures leave the last valid snapshot intact. The snapshot
   includes its source timestamp and fetch timestamp; users must not infer
   freshness merely because the page was reloaded.
9. Candidate strings are inserted using textContent, not HTML, and CSV
   export guards against spreadsheet formula injection.

## Deployment

- Merge the PR into main after CI tests and code review.
- Cloudflare Pages publishes the public/ output as a static site.
- The observed-results workflow is scheduled on the default branch; a
  manual workflow_dispatch can seed it immediately after merge.
- No API keys, paid subscriptions or Cloudflare Workers are necessary.
- If GitHub Actions is disabled, the browser tries the licensed feed directly,
  but cross-origin restrictions may leave only the repository snapshot.
- Original pre-election forecast history remains immutable.

## Next research increments

A true congressional-district choropleth, county-to-district attribution,
vote-method batch tracking, complete official certification lineage, 2024
baseline reconciliation following redistricting, and precinct-level analysis
should be separate evidence-backed phases. This first release intentionally
does not pretend to have those inputs.

## Results Desk v2.0: geographic and analytical publication

The v2 interface adds an entirely local geographic state-outline visualisation,
selectable coverage/House/Senate layers, source-status ledger, a provisional
two-party comparison scatterplot, and a candidate-level race inspection lens.
The geometry is PublicaMundi's published US States GeoJSON (originally public
geographic boundary data; 2017 state outline edition), stored locally so the
map is not blocked by third-party scripts or CDN outages.

**Methodological limits, displayed in the UI:**

- State map shading for **coverage** is the share of *tracked contests* with
  at least one published vote. It is *not* the percentage of ballots, precincts
  or voters counted.
- State map **House D−R** sums only known Democratic and Republican votes across
  those congressional districts with published returns. Missing districts
  remain missing. This number does not project statewide or national outcomes.
- State map **Senate D−R** reports only the matched statewide contest. A state
  with overlapping regular and special Senate races but a single model key is
  deliberately withheld pending a contest-specific crosswalk.
- A race's **D−R discrepancy** is (currently reported two-party margin − frozen
  predicted two-party margin). Unfinished counts, differential vote-method
  timing and missing precinct data can produce large provisional gaps.
- The **headline median discrepancy** is withheld unless at least *five*
  comparable races have provider-reported *95% or more reporting units*; even
  then it remains a provisional descriptive statistic, not a Brier score,
  certified result or national swing.
- The scatterplot only plots races with both a known two-party margin and a
  frozen prediction; missing observations are never converted to a zero.
- Data freshness refers to a source result timestamp, not merely the time
  the browser requested a page. Missing or unparseable timestamps are labelled
  unknown.
- The source arbiter preserves all candidate votes from **one** provider per
  race, never averages provider vote totals and never trusts an unsourced call.
  A documented timestamp more than an hour newer can supersede a stale
  counterpart, while explicit called winners retain priority.
- Counts from Open America are a **browser-only** direct read with its required
  original attribution. They are not persisted as a repackaged feed.
- The map represents *states*, not true 2026 congressional district
  boundaries. States with recent redistricting must not be shown against
  incorrect historic district polygons. The district table remains the
  authoritative geographic granularity for each congressional contest.

Safety/quality gates include Node analytics tests, ambiguous-source collision
tests, a mobile Playwright map/race-lens test, a no-observations fallback test,
accessibility checks and the pre-existing production model CI suite.
