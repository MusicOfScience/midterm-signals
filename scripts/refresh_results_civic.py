#!/usr/bin/env python3
"""Import real 2026 House/Senate counts from the licensed, public civicAPI feed.

The 2026 national civicAPI records are the House and Senate aggregate races.
Do not mistake a forecast for a result, a lead for a call, or the time of
download for the time an election authority last published the count.

civicAPI terms: https://www.civicapi.org/faq (attribution required).
Source IDs: https://civicapi.org/api/v2/race/87524 (House),
            https://civicapi.org/api/v2/race/87528 (Senate).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.refresh_results import TARGET, model_code, publish

RACES = {
    "house": ("87524", "https://civicapi.org/api/v2/race/87524"),
    "senate": ("87528", "https://civicapi.org/api/v2/race/87528"),
}
VALID_PARTIES = {"D", "R", "I", "L", "G", "C", "W", "?"}
MAX_RESPONSE_BYTES = 10_000_000
BASE = Path(__file__).resolve().parents[1]


def party(value: Any) -> str:
    p = str(value or "").strip().casefold()
    if p.startswith(("democrat", "democratic")) or p in {"d", "dem"}:
        return "D"
    if p.startswith(("republican", "gop")) or p in {"r", "rep"}:
        return "R"
    if p.startswith(("independent", "unaffiliated")) or p in {"i", "ind"}:
        return "I"
    if p in {"libertarian", "l"}:
        return "L"
    if p in {"green", "g"}:
        return "G"
    return "?"


def iso_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        if parsed.year < 2026 or parsed.year > 2027:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def race_key(seat: str, office: str) -> tuple[str, str, str] | None:
    key = str(seat).upper().strip()
    if office == "house":
        if not re.fullmatch(r"[A-Z]{2}-(?:\d{1,2}|AL)", key):
            return None
        value = model_code("H-" + key)
        return value if value else None
    if office == "senate":
        if not re.fullmatch(r"[A-Z]{2}(?:-(?:SP|SPECIAL))?", key):
            return None
        value = model_code("S-" + key)
        return value if value else None
    return None


def count_value(value: Any) -> int | None:
    if type(value) is int and 0 <= value <= 500_000_000:
        return value
    return None


def normalise_office(document: dict, office: str) -> list[dict]:
    if not isinstance(document, dict) or document.get("test_data") is True:
        raise ValueError(f"{office}: test data or invalid response rejected")
    if "year" in document and str(document["year"]) != "2026":
        raise ValueError(f"{office}: unexpected election year")
    if "election_date" in document and not str(document["election_date"]).startswith("2026-11-03"):
        raise ValueError(f"{office}: unexpected election date")
    regions = document.get("region_results")
    if not isinstance(regions, dict):
        raise ValueError(f"{office}: missing region_results dictionary")
    if len(regions) > 900:
        raise ValueError(f"{office}: unreasonable number of regions")
    parent_at = iso_date(document.get("last_updated"))
    results = []
    for seat, value in regions.items():
        key = race_key(str(seat), office)
        if not key or not isinstance(value, dict) or not isinstance(value.get("candidates"), list):
            continue
        if len(value["candidates"]) > 40:
            continue
        candidates = []
        for entry in value["candidates"]:
            if not isinstance(entry, dict):
                continue
            votes = count_value(entry.get("votes"))
            if votes is None:
                continue
            candidates.append({
                "name": str(entry.get("name") or "").strip()[:180],
                "party": party(entry.get("party")),
                "votes": votes,
                "winner": entry.get("winner") is True,
            })
        if not candidates:
            continue
        total = sum(c["votes"] for c in candidates)
        if total > 500_000_000:
            continue
        winners = [c for c in candidates if c["winner"]]
        winner = winners[0] if len(winners) == 1 else None
        leader = max(candidates, key=lambda c: c["votes"]) if total else None
        pc = value.get("percent_reporting")
        reporting_pct = float(pc) if type(pc) in (float, int) and 0 <= pc <= 100 else None
        results.append({
            "race_id": ("H-" if office == "house" else "S-") + str(seat).upper(),
            "model_code": key[0],
            "chamber": key[1],
            "state": key[2],
            "candidates": candidates,
            "votes_total": total,
            "leader": leader,
            "called": bool(winner),
            "winner": winner,
            "called_by": "civicAPI decision desk" if winner else None,
            "source_name": "civicAPI",
            "source_url": RACES[office][1],
            "source_updated_at": iso_date(value.get("last_updated")) or parent_at,
            "reporting_unit_pct": reporting_pct,
        })
    return results


def fetch_json(url: str, attempts: int = 3) -> dict:
    last = None
    for i in range(attempts):
        try:
            request = urllib.request.Request(
                url, headers={
                    "User-Agent": "MIDTERM-SIGNALS results desk (MusicOfScience/midterm-signals)",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                })
            with urllib.request.urlopen(request, timeout=22) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise ValueError("Exceeded maximum response size")
            return json.loads(payload.decode("utf-8"))
        except (ValueError, urllib.error.URLError, TimeoutError, OSError) as error:
            last = error
            if i < attempts - 1:
                time.sleep((i + 1) * 3)
    raise RuntimeError(f"civicAPI fetch unavailable for {url}: {last}")


def consolidate(documents: dict[str, dict], previous: dict | None = None, fetched_at: str | None = None) -> dict:
    previous = previous or {}
    collected: dict[str, list[dict]] = {}
    for office, doc in documents.items():
        for result in normalise_office(doc, office):
            collected.setdefault(result["model_code"], []).append(result)

    # Never map an ambiguous Senate special/regular pair to one model contest.
    ambiguous = set(previous.get("ambiguous_keys") or [])
    for key, entries in collected.items():
        if len(entries) > 1:
            ambiguous.add(key)
    fresh = {k: v[0] for k, v in collected.items() if len(v) == 1 and k not in ambiguous}
    old = {r["model_code"]: r for r in previous.get("races", []) if isinstance(r, dict) and r.get("model_code")}
    final = {}
    for k, row in old.items():
        if k not in ambiguous:
            final[k] = row
    for k, row in fresh.items():
        old_item = final.get(k)
        if old_item:
            old_at = iso_date(old_item.get("source_updated_at"))
            new_at = iso_date(row.get("source_updated_at"))
            # Do not regress a newer count to an older provider snapshot.
            if old_at and new_at and new_at < old_at:
                continue
            if old_at and not new_at and old_item.get("votes_total", 0) > 0:
                continue
        final[k] = row

    for key in ambiguous:
        final.pop(key, None)
    records = [final[k] for k in sorted(final)]
    updated = sorted(
        (iso_date(r.get("source_updated_at")) for r in records),
        key=lambda x: x or "", reverse=True
    )
    latest = updated[0] if updated else None
    when = fetched_at or datetime.now(timezone.utc).isoformat()
    count = sum(r.get("votes_total", 0) > 0 for r in records)
    return {
        "schema_version": 1,
        "source": "civicAPI",
        "source_title": "civicAPI 2026 US House and Senate returns",
        "source_url": "https://civicapi.org/",
        "source_licence": "Free reuse with attribution",
        "source_updated_at": latest,
        "fetched_at": when,
        "state": "reporting" if count else "awaiting_results",
        "races": records,
        "ambiguous_keys": sorted(ambiguous),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Inspect public source without changing repository data")
    parser.add_argument("--strict-live", action="store_true", help="Fail when no 2026 vote counts exist")
    parser.add_argument("--min-house", type=int, default=0, help="Require this many freshly sourced House contests")
    parser.add_argument("--min-senate", type=int, default=0, help="Require this many freshly sourced Senate contests")
    parser.add_argument("--fixture-house", type=Path)
    parser.add_argument("--fixture-senate", type=Path)
    args = parser.parse_args()
    documents: dict[str, dict] = {}
    errors = {}
    for office, (_, url) in RACES.items():
        try:
            fixture = args.fixture_house if office == "house" else args.fixture_senate
            doc = json.loads(fixture.read_text(encoding="utf-8")) if fixture else fetch_json(url)
            # Validate before accepting this upstream document.
            normalise_office(doc, office)
            documents[office] = doc
        except Exception as error:
            errors[office] = str(error)
            print(f"Source degraded: {office}: {error}", file=sys.stderr)

    if not documents:
        raise SystemExit("No usable civicAPI feeds. Keep the last good stored snapshot.")
    previous = json.loads(TARGET.read_text(encoding="utf-8")) if TARGET.exists() else None
    payload = consolidate(documents, previous)
    reporting = sum(r.get("votes_total", 0) > 0 for r in payload["races"])
    house = sum(r["chamber"] == "house" and r.get("votes_total", 0) > 0 for r in payload["races"])
    senate = sum(r["chamber"] == "senate" and r.get("votes_total", 0) > 0 for r in payload["races"])
    called = sum(bool(r.get("called")) for r in payload["races"])
    print(json.dumps({
        "status": "live dry run" if args.dry_run else "publisher run",
        "reporting_house": house,
        "reporting_senate": senate,
        "reported_races": reporting,
        "called_civicapi": called,
        "provider_updated_at": payload["source_updated_at"],
        "missing_provider": list(errors),
        "ambiguous": payload["ambiguous_keys"],
    }))
    if args.strict_live and reporting == 0:
        raise SystemExit("Critical: licensed national provider returned zero published votes; refuse live claim.")
    source_house = sum(r["votes_total"] > 0 for r in normalise_office(documents["house"], "house")) if "house" in documents else 0
    source_senate = sum(r["votes_total"] > 0 for r in normalise_office(documents["senate"], "senate")) if "senate" in documents else 0
    if source_house < args.min_house or source_senate < args.min_senate:
        raise SystemExit(f"Source coverage below minimum: {source_house} House and {source_senate} Senate; required {args.min_house}/{args.min_senate}")

    if not args.dry_run:
        print("Snapshot:", publish(payload))


if __name__ == "__main__":
    main()
