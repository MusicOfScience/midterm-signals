#!/usr/bin/env python3
"""Build a reproducible, strictly separated observation layer for 2026 results.

The People's Tally publishes a public CC BY 4.0 JSON feed compiled from official
state returns and named call services. Counts are unofficial until certification.
Missing results are not zero; a counting lead is not a call. Forecast files are
never opened for writing by this adapter.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "public/data/observed-results.json"
URL = "https://thepeoplestally.com/data/results.json"
AT_LARGE = {"AK", "DE", "ND", "SD", "VT", "WY"}
MAX_BYTES = 15_000_000


def model_code(source_id: str) -> tuple[str, str, str] | None:
    house = re.fullmatch(r"H-([A-Z]{2})-(\d{1,2}|AL)", source_id.upper())
    if house:
        state, district = house.groups()
        if district in {"AL", "00"}:
            if state not in AT_LARGE:
                return None
            district = "01"  # Model codes its at-large districts as 01.
        elif int(district) < 1 or int(district) > 53:
            return None
        return (state + "-" + district.zfill(2), "house", state)
    senate = re.fullmatch(r"S-([A-Z]{2})(?:-(SP|SPECIAL))?", source_id.upper())
    if senate:
        state = senate.group(1)
        return (state + "-SEN", "senate", state)
    return None


def party(value: Any) -> str:
    code = str(value or "").upper().strip()
    if code in {"D", "DEM", "DEMOCRATIC"}:
        return "D"
    if code in {"R", "REP", "REPUBLICAN"}:
        return "R"
    return code or "?"


def nonnegative_int(value: Any) -> int:
    # bool is deliberately excluded: True is not a valid vote total.
    if type(value) is int and 0 <= value <= 500_000_000:
        return value
    return 0


def normalize(raw: dict, fetched_at: str) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("races"), dict):
        raise ValueError("Provider response must include a races object.")
    if len(raw["races"]) > 2000:
        raise ValueError("Unreasonable race count: refuse source payload.")
    races = []
    for source_id, record in sorted(raw["races"].items()):
        identity = model_code(source_id)
        if not identity or not isinstance(record, dict):
            continue
        candidates = record.get("cands")
        if not isinstance(candidates, list) or len(candidates) > 100:
            continue
        cands = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            cands.append({
                "name": str(candidate.get("name") or "").strip()[:180],
                "party": party(candidate.get("party")),
                "votes": nonnegative_int(candidate.get("votes")),
                "winner": candidate.get("winner") is True,
            })
        if not cands:
            continue
        total = sum(c["votes"] for c in cands)
        if total > 500_000_000:
            raise ValueError("Unreasonable per-contest vote count.")
        leader = max(cands, key=lambda c: c["votes"]) if total else None
        called_by = record.get("called_by")
        called_by = called_by.strip()[:140] if isinstance(called_by, str) else ""
        winner = next((c for c in cands if c["winner"]), None) if called_by else None
        url = record.get("url")
        url = url if isinstance(url, str) and url.startswith("https://") else None
        source_name = record.get("src")
        source_name = source_name[:160] if isinstance(source_name, str) else None
        races.append({
            "race_id": source_id,
            "model_code": identity[0],
            "chamber": identity[1],
            "state": identity[2],
            "votes_total": total,
            "candidates": cands,
            "leader": leader,
            "called": bool(winner),
            "winner": winner,
            "called_by": called_by if winner else None,
            "source_name": source_name or "The People's Tally",
            "source_url": url,
            "source_updated_at": record.get("asof") if isinstance(record.get("asof"), str) else None,
        })
    timestamp = raw.get("generated_at")
    return {
        "schema_version": 1,
        "source": "thepeoplestally",
        "source_title": "The People's Tally, 2026 US midterms",
        "source_url": "https://thepeoplestally.com/open-data/",
        "source_licence": "CC BY 4.0",
        "source_updated_at": timestamp if isinstance(timestamp, str) else None,
        "fetched_at": fetched_at,
        "state": "reporting" if any(r["votes_total"] > 0 for r in races) else "awaiting_results",
        "races": races,
    }


def fetch_data(url: str = URL) -> dict:
    request = urllib.request.Request(
        url, headers={"User-Agent": "MIDTERM-SIGNALS/1.0 (github.com/MusicOfScience/midterm-signals)",
                      "Accept": "application/json", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=25) as response:
        content = response.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError("Results payload exceeds size limit.")
    return json.loads(content.decode("utf-8"))


def publish(new: dict, path: Path = TARGET) -> str:
    old = None
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
    old_count = sum(bool(r.get("votes_total")) for r in (old or {}).get("races", []))
    new_count = sum(bool(r.get("votes_total")) for r in new["races"])
    if old_count > new_count:
        raise ValueError("Provider regression removed reporting races. Keep last good snapshot.")
    # Preserve the original fetch timestamp when no substantive source data changed.
    def substantive(value):
        return {k: v for k, v in value.items() if k != "fetched_at"}
    if old is not None and substantive(old) == substantive(new):
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(new, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return "updated"


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a checked election results snapshot.")
    parser.add_argument("--fixture", type=Path, help="Local fixture JSON instead of fetching the public feed")
    args = parser.parse_args()
    raw = json.loads(args.fixture.read_text(encoding="utf-8")) if args.fixture else fetch_data()
    payload = normalize(raw, datetime.now(timezone.utc).isoformat())
    outcome = publish(payload)
    print("Election results:", outcome, "; reporting races:", sum(r["votes_total"] > 0 for r in payload["races"]),
          "; provider races:", len(payload["races"]), "; state:", payload["state"])


if __name__ == "__main__":
    main()
