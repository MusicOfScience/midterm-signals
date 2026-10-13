#!/usr/bin/env python3
"""Final strict entrypoint for the 2022 historical admission.

This layers two admission policies over ``admit_historical_2022``:

1. keep its race-level structural scoreability gates; and
2. admit generic-ballot observations only from the pinned 5 November 2022
   snapshot.  The later retrospective raw-polls archive is deliberately not
   consulted merely to manufacture a poll ending closer to election day.

A 4 November poll that was present in the 5 November snapshot is a legitimate
input to the frozen model's 7 November checkpoint: the live model's generic
window is 35 days, not one day.  Historical evaluation must mirror that rule
rather than imposing a new hindsight-only freshness requirement.
"""
from __future__ import annotations

import json
from datetime import date

import admit_historical_2022 as admission

impl = admission.impl
_ORIGINAL_FETCH = impl.fetch
_RETROSPECTIVE_SUPPLEMENT_LABEL = "FiveThirtyEight 2023 raw-polls late generic supplement"


def strict_fetch(label: str, url: str, *args, **kwargs) -> bytes:
    """Prevent the retrospective generic supplement from entering provenance.

    ``run_historical_2022.main`` still contains the old two-argument call.  We
    return an empty sentinel for that one legacy argument; the patched generic
    normalizer below ignores it.  All real evidence fetches remain unchanged.
    """
    if label == _RETROSPECTIVE_SUPPLEMENT_LABEL:
        return b""
    return _ORIGINAL_FETCH(label, url, *args, **kwargs)


def strict_build_generic(snapshot: bytes, _ignored_supplement: bytes) -> list[dict]:
    """Normalize only the pinned 2022-11-05 generic-ballot snapshot."""
    combined = {}
    for row in impl.csv_rows(snapshot):
        if str(row.get("cycle") or "") != "2022":
            continue
        end = impl.parse_day(row.get("end_date"))
        if not end or end > impl.ELECTION:
            continue
        dem = impl.fnum(row.get("dem"))
        rep = impl.fnum(row.get("rep"))
        if dem is None or rep is None:
            continue
        population = row.get("population_full") or row.get("population") or ""
        key = (row.get("poll_id"), row.get("question_id"), population, end.isoformat())
        combined[key] = row

    out = []
    for row in combined.values():
        end = impl.parse_day(row.get("end_date"))
        dem = impl.fnum(row.get("dem"))
        rep = impl.fnum(row.get("rep"))
        if not end or end > impl.ELECTION or dem is None or rep is None:
            continue
        publication = impl.publication_date(row, end) or end.isoformat()
        pub_day = impl.parse_day(publication)
        if pub_day is None or pub_day > date(2022, 11, 5):
            raise RuntimeError(
                f"generic snapshot contains observation unavailable by snapshot date: {publication}"
            )
        out.append({
            "kind": "generic_ballot",
            "race_code": "",
            "publication_date": publication,
            "end_date": end.isoformat(),
            "pollster": row.get("display_name") or row.get("pollster") or "",
            "rating": impl.grade_score(row.get("fte_grade")),
            "n": impl.fnum(row.get("sample_size"), 800) or 800,
            "lean": impl.party(row.get("partisan")) if impl.party(row.get("partisan")) in {"DEM", "REP"} else "",
            "dem_name": "",
            "rep_name": "",
            "dem": dem,
            "rep": rep,
            "margin": dem - rep,
        })

    if not out:
        raise RuntimeError("pinned 2022-11-05 generic-ballot snapshot normalized zero observations")
    latest_end = max(impl.parse_day(row["end_date"]) for row in out)
    latest_publication = max(impl.parse_day(row["publication_date"]) for row in out)
    if latest_end < date(2022, 11, 4):
        raise RuntimeError(f"pinned generic snapshot unexpectedly stale: latest end date {latest_end}")
    if latest_publication < date(2022, 11, 4):
        raise RuntimeError(
            f"pinned generic snapshot unexpectedly stale: latest publication {latest_publication}"
        )
    return out


impl.fetch = strict_fetch
impl.build_generic = strict_build_generic

if __name__ == "__main__":
    impl.main()

    # The base admission wrapper is imported rather than executed as __main__,
    # so write its structural diagnostics here and replace the obsolete generic
    # provenance description with the policy actually used by this run.
    cfg_path = impl.OUT / "cycle.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    scoreability = cfg.setdefault("scoreability", {})
    scoreability["structural_prior_failures"] = dict(sorted(admission.STRUCTURAL_FAILURES.items()))
    cfg.setdefault("poll_archive_rules", {})["generic_ballot"] = (
        "Pinned 2022-11-05 pre-election snapshot only; latest admitted poll ended "
        "2022-11-04 and was published by 2022-11-04. No retrospective supplement admitted."
    )
    cfg["poll_archive_rules"]["generic_freshness_rule"] = (
        "Replay uses the frozen model's 35-day generic-ballot window. It does not require "
        "a poll to end on election eve."
    )
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
