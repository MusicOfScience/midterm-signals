# Data sources

MIDTERM SIGNALS prefers public, stable and attributable sources. Raw observations are dated and source-controlled before they can affect a forecast.

## Current numerical inputs

- **Track the Vote — generic congressional ballot**: https://www.trackthevote.net/generic-ballot. Snapshot 2026-10-12: D 49.3%, R 40.7%, D+8.7; 11 polls in current average. Used as a national House vote proxy.
- **Track the Vote — Senate polling**: https://www.trackthevote.net/senate. Snapshot 2026-10-12. Public Senate polling margins; qualitative site text is not ingested.
- **Track the Vote — presidential approval**: https://www.trackthevote.net/. Snapshot 2026-10-12: net approval −22.5. Descriptive only; model coefficient is zero.
- **Cook Political Report — House ratings**: https://www.cookpolitical.com/ratings/house-race-ratings. Snapshot 2026-10-09. Public category counts and non-Solid race list form the current-map prior. No automated Cook scraping, subscriber-only analysis or all-seat proprietary PVI product is reproduced.
- **Cook Political Report — Senate ratings**: https://www.cookpolitical.com/ratings/senate-race-ratings. Snapshot 2026-10-06. Public category information provides race priors.
- **U.S. House historical election statistics**: https://history.house.gov/Institution/Election-Statistics/Election-Statistics/. Used for coarse historical House vote-to-seat calibration.

A failed source check must never become a new observation. The last valid immutable snapshot remains identifiable and materially stale data becomes a publication warning rather than a silent zero.
