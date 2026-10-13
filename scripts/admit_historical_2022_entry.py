#!/usr/bin/env python3
"""Final strict entrypoint for 2022 historical corpus admission.

This layer keeps the admission-policy guards from ``admit_historical_2022``
and corrects the schema adapter for FiveThirtyEight's retrospective raw-polls
archive. The archive identifies the election cycle with ``year`` rather than
``cycle``; only pre-election national House-G rows are admitted as the late
generic-ballot supplement.
"""
from __future__ import annotations

import json

import admit_historical_2022 as strict

impl = strict.impl


def strict_build_generic(base: bytes, supplement: bytes) -> list[dict]:
    """Build the 2022 generic-ballot stream with an election-eve fail-closed gate."""
    combined = {}

    # Preserved 5 November 2022 snapshot of FiveThirtyEight's live generic
    # ballot file. This source uses ``cycle``.
    for row in impl.csv_rows(base):
        if str(row.get("cycle") or "").strip() != "2022":
            continue
        end = impl.parse_day(row.get("end_date"))
        if not end or end > impl.ELECTION:
            continue
        combined[(
            row.get("poll_id"),
            row.get("question_id"),
            row.get("population_full") or row.get("population"),
            end.isoformat(),
        )] = row

    # Retrospective first-party raw-polls archive. This source uses ``year``.
    # Admit only national generic-ballot rows after the dated snapshot, never
    # district races, post-election rows, or outcome-derived columns.
    supplement_rows = 0
    for row in impl.csv_rows(supplement, errors="replace"):
        if str(row.get("year") or "").strip() != "2022":
            continue
        if str(row.get("type_simple") or "").strip() != "House-G":
            continue
        if str(row.get("location") or "").strip().upper() != "US":
            continue
        end = impl.parse_day(row.get("polldate") or row.get("end_date"))
        election = impl.parse_day(row.get("electiondate") or row.get("election_date"))
        if not end or end <= impl.date(2022, 11, 4) or end > impl.ELECTION or election != impl.ELECTION:
            continue

        p1 = impl.party(row.get("cand1_party"))
        p2 = impl.party(row.get("cand2_party"))
        if p1 == "DEM" and p2 == "REP":
            dem, rep = impl.fnum(row.get("cand1_pct")), impl.fnum(row.get("cand2_pct"))
        elif p2 == "DEM" and p1 == "REP":
            dem, rep = impl.fnum(row.get("cand2_pct")), impl.fnum(row.get("cand1_pct"))
        else:
            continue
        if dem is None or rep is None:
            continue

        adapted = {
            "poll_id": row.get("poll_id") or row.get("pollno"),
            "question_id": row.get("question_id") or row.get("race"),
            "population": row.get("population") or "",
            "display_name": row.get("pollster") or "",
            "fte_grade": "",
            "sample_size": row.get("samplesize") or "",
            "partisan": "",
            "end_date": end.isoformat(),
            # No separate publication timestamp is exposed in this historical
            # archive. For these election-eve rows, the poll date is the only
            # admitted availability timestamp; this is disclosed in cycle.json.
            "created_at": end.isoformat(),
            "dem": dem,
            "rep": rep,
        }
        combined[(
            adapted["poll_id"],
            adapted["question_id"],
            adapted["population"],
            end.isoformat(),
        )] = adapted
        supplement_rows += 1

    if supplement_rows == 0:
        raise RuntimeError("raw-polls archive supplied zero national 2022 election-eve generic-ballot rows")

    out = []
    for row in combined.values():
        end = impl.parse_day(row.get("end_date") or row.get("polldate"))
        dem, rep = impl.fnum(row.get("dem")), impl.fnum(row.get("rep"))
        if not end or end > impl.ELECTION or dem is None or rep is None:
            continue
        out.append({
            "kind": "generic_ballot",
            "race_code": "",
            "publication_date": impl.publication_date(row, end) or end.isoformat(),
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

    if not out or max(impl.parse_day(row["end_date"]) for row in out) < impl.date(2022, 11, 6):
        raise RuntimeError("generic-ballot composite does not reach election eve")
    return out


impl.build_generic = strict_build_generic

if __name__ == "__main__":
    impl.main()
    # Preserve state-level structural evidence failures in the manifest. They
    # are diagnostics; row-level admission was frozen before outcomes loaded.
    cfg_path = impl.OUT / "cycle.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg.setdefault("scoreability", {})["structural_prior_failures"] = dict(sorted(strict.STRUCTURAL_FAILURES.items()))
    cfg.setdefault("poll_archive_rules", {})["late_generic_availability"] = (
        "FiveThirtyEight retrospective raw-polls House-G US rows use year=2022; "
        "poll date is the admitted availability timestamp where no separate publication timestamp exists."
    )
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
