#!/usr/bin/env python3
"""Verify a first-party FiveThirtyEight archive of the 2022 polling inputs.

The 2023 pollster-ratings archive is retrospective, so this probe explicitly
uses only fields that existed before the 2022 election. It separately pins the
2021 pollster ratings for any quality weighting; 2022 outcomes/ratings are not
allowed into the replay inputs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.request
from collections import Counter
from datetime import datetime

UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"
FTE_COMMIT = "4c1ff5e3aef1816ae04af63218015066e186c147"
RAW_POLLS = f"https://raw.githubusercontent.com/fivethirtyeight/data/{FTE_COMMIT}/pollster-ratings/2023/raw-polls.csv"
PRE2022_RATINGS = f"https://raw.githubusercontent.com/fivethirtyeight/data/{FTE_COMMIT}/pollster-ratings/2021/pollster-ratings.csv"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if not data:
        raise RuntimeError(f"empty response: {url}")
    return data


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def main() -> None:
    raw = fetch(RAW_POLLS)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="strict")))
    required = {
        "pollno", "race", "year", "location", "type_simple", "pollster",
        "methodology", "partisan", "polldate", "samplesize",
        "cand1_name", "cand1_party", "cand1_pct",
        "cand2_name", "cand2_party", "cand2_pct", "margin_poll",
        "electiondate",
    }
    missing = sorted(required - set(reader.fieldnames or []))
    if missing:
        raise RuntimeError(f"first-party raw-polls archive missing columns: {missing}")

    buckets: dict[str, list[dict]] = {"Sen-G": [], "House-G": [], "House-G-US": []}
    for row in reader:
        if str(row.get("year") or "").strip() != "2022":
            continue
        kind = (row.get("type_simple") or "").strip()
        if kind in buckets:
            buckets[kind].append(row)

    diagnostics = {}
    for kind, rows in buckets.items():
        if not rows:
            raise RuntimeError(f"first-party raw-polls archive contains no 2022 {kind} rows")
        dates = [parse_date(r.get("polldate", "")) for r in rows]
        dates = [d for d in dates if d is not None]
        if not dates:
            raise RuntimeError(f"2022 {kind} rows have no parseable poll dates")
        diagnostics[kind] = {
            "rows": len(rows),
            "unique_polls": len({r.get("pollno") for r in rows}),
            "min_polldate": min(dates).strftime("%Y-%m-%d"),
            "max_polldate": max(dates).strftime("%Y-%m-%d"),
            "locations": len({r.get("location") for r in rows}),
            "pollsters": len({r.get("pollster") for r in rows}),
            "candidate_party_pairs": Counter(
                f"{r.get('cand1_party','')}|{r.get('cand2_party','')}" for r in rows
            ).most_common(8),
            "sample": [
                {k: r.get(k) for k in (
                    "pollno", "race", "location", "type_simple", "pollster",
                    "polldate", "samplesize", "cand1_name", "cand1_party",
                    "cand1_pct", "cand2_name", "cand2_party", "cand2_pct",
                    "margin_poll", "electiondate",
                )}
                for r in rows[-3:]
            ],
        }

    # Race-specific archives must reach election week. Generic ballot may end a
    # day or two earlier; anything before November is rejected.
    for kind in ("Sen-G", "House-G"):
        if diagnostics[kind]["max_polldate"] < "2022-11-01":
            raise RuntimeError(f"2022 {kind} archive is truncated before election week: {diagnostics[kind]['max_polldate']}")
    if diagnostics["House-G-US"]["max_polldate"] < "2022-11-01":
        raise RuntimeError(f"2022 generic-ballot archive is truncated: {diagnostics['House-G-US']['max_polldate']}")

    ratings = fetch(PRE2022_RATINGS)
    rr = csv.DictReader(io.StringIO(ratings.decode("utf-8-sig", errors="strict")))
    rcols = set(rr.fieldnames or [])
    if not {"Pollster", "538 Grade"}.issubset(rcols):
        raise RuntimeError(f"pre-2022 rating file missing expected columns: {sorted(rcols)}")
    rating_rows = [r for r in rr if (r.get("Pollster") or "").strip()]
    grade_by_name = {(r.get("Pollster") or "").strip(): (r.get("538 Grade") or "").strip() for r in rating_rows}
    all_pollsters = {r.get("pollster") for rows in buckets.values() for r in rows if r.get("pollster")}
    matched = {p for p in all_pollsters if p in grade_by_name and grade_by_name[p]}

    print(json.dumps({
        "source": {
            "repository": "fivethirtyeight/data",
            "commit": FTE_COMMIT,
            "raw_polls_url": RAW_POLLS,
            "raw_polls_sha256": sha(raw),
            "raw_polls_bytes": len(raw),
            "pre2022_ratings_url": PRE2022_RATINGS,
            "pre2022_ratings_sha256": sha(ratings),
            "pre2022_ratings_bytes": len(ratings),
        },
        "2022": diagnostics,
        "pre2022_quality": {
            "pollsters_in_2022_archive": len(all_pollsters),
            "matched_to_2021_grade": len(matched),
            "unmatched": sorted(all_pollsters - matched)[:50],
            "unmatched_count": len(all_pollsters - matched),
            "rule": "Only 2021 FiveThirtyEight grades may weight 2022 replay polls; no post-election pollster grade is used.",
        },
        "forbidden_retrospective_fields": ["cand1_actual", "cand2_actual", "margin_actual", "error", "bias", "rightcall"],
    }, indent=2))


if __name__ == "__main__":
    main()
