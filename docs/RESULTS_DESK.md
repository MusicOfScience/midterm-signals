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


## National source recovery / 4 November 2026

The results source defect was confirmed against live AP-backed newsroom coverage:
the original People's Tally results JSON remained empty while House and Senate
results were available elsewhere. GitHub's published workflow history showed
no recorded runs of the standalone results-ingestion workflow after v1/v2 were
merged, so a scheduled trigger alone could not be relied upon for initial
publication. This is a **critical source-pipeline defect**.

The corrected design prioritises civicAPI, using its published 2026 aggregate
House (race ID 87524) and Senate (race ID 87528) records. The civicAPI site
permits both personal and public reuse without a key, with attribution.
Counts and calls are from civicAPI's own decision desk, **not AP**.

The server-side adapter is scripts/refresh_results_civic.py. It validates
the 2026 election, suppresses test data, excludes malformed/negative vote
counts, preserves source and fetch timestamps separately, retains last good
results if one upstream endpoint fails, and prevents wrong special/regular
Senate joins. The workflow now triggers once on a main-branch code merge,
then on a five-minute best-effort GitHub Actions schedule. Snapshot-only
commits do not retrigger the workflow. No model coefficient or forecast
history is changed.

To avoid approving a dashboard that only appears operational, the pull-request
test job verifies actual upstream coverage of at least 150 live House contests
and 10 Senate contests. That threshold is election-night-specific; it does not
mean all other contests have zero votes, and it is distinct from the percentage
of ballots reported. If the live provider cannot meet that minimum, the PR
should **not** be merged based on synthetic tests alone.

The Results Desk also provides external AP-backed national results links. These
are independent newsroom references, not scraped or rebadged AP data. AP's
programmatic election-results feed is paid/licensed; five-minute Github Actions
polling is not equivalent to network real-time reporting. Source freshness is
shown from the provider's timestamps rather than browser reload time.


## Open America API contract audit (4 November 2026)

Rechecked https://openamerica.io/elections/api/ in full. This is a *direct browser* source, not the national live feed. It covers 22 states, with no race calls. Its `counting`, `live`, `stale`, `final`, `as_of` and `counts` fields are now exposed through the source ledger. Critically, `as_of` is the timestamp of the **newest state feed anywhere in the response**; it must never be silently assigned as the refresh time of each race. The adapter now keeps it at feed level only.

Open America updates its state adapters every minute on election night and recommends 60-second polling, respecting its caching and conditional request headers. It supports CORS without credentials. The `pct_in` metric varies by state: counties in GA, ID, MI, UT and WA; localities in VA; towns/cities in RI; and a statewide percentage reused across districts in TX and IN. It therefore never represents a comparable national share of ballots counted. `final` refers to all available precincts reporting, not certification.

Open America asks for permission before repackaging live counts as an independent results service. The dashboard accesses its feed directly in the user's browser with source attribution; it does not store or republish Open America as a wholesale mirror.


## v3: newsroom-grade congressional seat accounting and evidence reconciliation

**2026 election-night holdovers** (only the 35 contested Senate seats are
counted again): 32 Democrats + two independent senators who caucus with
Democrats = 34 Democratic-aligned seats not on the ballot; 31 Republicans.
Evidence: U.S. Senate Daily Press (2026 party lineup), Senate.gov, Ballotpedia
and https://watch.vote/midterms/2026/balance-of-power .
The independent caucus designation is known for the holdovers ONLY; never
assume an incoming independent winner caucuses with Democrats without evidence.

The v3 control board displays the next Congress's **called seat totals**:
- House: all 435 seats contested; 218 called seats needed for majority.
- Senate: 34/31 holdovers + explicitly attributed election-night calls;
  51 Democratic-aligned seats for control; a 50–50 tie is broken by the
  Republican vice-president.
- Uncalled counting leads appear separately, never in the secured seats.
- Calls are *projected winners by civicAPI*, not certified elections, not
  incumbent senators' present chamber composition. Unknown/other candidates
  occupy a separate category; no automatic two-party assignment.
- An incomplete count cannot masquerade as 0 and duplicated race keys are
  excluded from the control tally.
- Seat-band segments always total 435/100 exactly.

**Independent newsroom checkpoint**:
The user provided a Guardian live-results screenshot at 19:38 AEDT
(08:38 UTC), 4 November 2026: House 225 D, 137 R, 362 races called;
Senate 54 Democratic-aligned including independents, 44 Republicans,
33 of 35 contested races called.
These *aggregates only* are stored in
\`public/data/newsroom-checkpoints.json\` with fixed provenance. No Guardian
screenshot image, programme text or AP-proprietary per-race feed is hosted.
An aggregate reconciliation is computed *only* if the civicAPI
\`source_updated_at\` is within 15 minutes of the captured newsroom
reference. Outside that window, the historical figures remain labelled
but numerical deltas are withheld. A difference in total calls alone cannot
identify the races, distinguish calling standards from elapsed time, or
establish which service is correct. No licensed AP feed is available.

**Publishing race hardening**:
Forecast and observed-result GitHub Actions now use the same
\`midterm-publication-main\` concurrency group. Bot commits are followed by
fetch/rebase and bounded push retries rather than a blind push that can
fail when another worker publishes. Conflicts fail closed; the pipeline
never force-pushes or rewrites observed election history.
Results run at a best-effort five-minute schedule. An Actions scheduled
job is not equivalent to a TV newsroom's sub-minute update service.

**Test changes**:
The no-observations browser tests now intercept same-origin source JSON
with a deliberately empty fixture; they must not presume production has no
votes. Dedicated browser tests cover actual non-zero calls, 390px
mobile rendering, semantics and source-time guards.


## 4 November 2026: forecast publisher post-merge incident

The Results Desk v3 merge completed and the live Results Desk validated.
The first forecast-workflow push nevertheless failed at `git rebase` with
`error: cannot rebase: You have unstaged changes`. The forecast computation,
unit tests and publication checks had already passed; only its final push
failed. The shared workflow concurrency group worked, but the forecasting
build left auxiliary worktree files outside its intended publication commit.

The publication workflow now stashes those **local, unpublished** tracked and
untracked files before fetching and rebasing onto the new main branch. It
checks for a clean worktree, never force-pushes, and fails closed on true
merge conflicts. The forecast workflow also excludes changes confined to
`public/data/observed-results.json` from its push trigger. An isolated
Git regression test simulates a competing results push and confirms that
both generated forecast and observed results survive without incorporating
the local auxiliary build files.
