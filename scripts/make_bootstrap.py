#!/usr/bin/env python3
"""Build the compact browser bootstrap from the authoritative forecast snapshot.

The public full forecast remains available as forecast.json. bootstrap.json is a
projection optimised for ordinary navigation: it deliberately removes raw poll
rows, duplicated search records and other deep-detail payloads. Race/poll pages
hydrate the full snapshot on demand.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public" / "data"
SOURCE = DATA / "forecast.json"
TARGET = DATA / "bootstrap.json"


def compact_chamber(ch: dict) -> dict:
    # Forecast Centre only needs summary statistics here. Full distributions
    # remain in summary.* and are not triplicated in nowcast/election-day views.
    return {k: v for k, v in ch.items() if k != "distribution"}


def compact_race(race: dict) -> dict:
    # All fields except underlying poll observations remain available to the
    # explorer, map, candidates, scenario lab and election builder.
    return {k: v for k, v in race.items() if k != "polls"}


def build(payload: dict) -> dict:
    out = dict(payload)
    out["__bootstrap"] = True
    races = [compact_race(r) for r in payload.get("races", [])]
    by_code = {r.get("race_code"): r for r in races}
    out["races"] = races

    env = dict(payload.get("national_environment", {}))
    env["recent_polls"] = []
    out["national_environment"] = env
    out["polls"] = []
    out["search_index"] = []

    out["tipping_point_house"] = [by_code.get(r.get("race_code"), compact_race(r)) for r in payload.get("tipping_point_house", [])]
    out["senate_battlegrounds"] = [by_code.get(r.get("race_code"), compact_race(r)) for r in payload.get("senate_battlegrounds", [])]

    summary = payload.get("summary", {})
    out["nowcast"] = {k: compact_chamber(v) for k, v in payload.get("nowcast", summary).items() if isinstance(v, dict)}
    out["election_day_forecast"] = {k: compact_chamber(v) for k, v in payload.get("election_day_forecast", summary).items() if isinstance(v, dict)}

    names = set()
    for poll in payload.get("polls", []) or payload.get("national_environment", {}).get("recent_polls", []):
        if poll.get("pollster"):
            names.add(poll["pollster"])
    for race in payload.get("races", []):
        for poll in race.get("polls", []):
            if poll.get("pollster"):
                names.add(poll["pollster"])
    out["pollster_names"] = sorted(names)
    return out


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit("forecast.json missing; cannot build browser bootstrap")
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    compact = build(payload)
    TARGET.write_text(json.dumps(compact, separators=(",", ":")) + "\n", encoding="utf-8")
    full = SOURCE.stat().st_size
    lite = TARGET.stat().st_size
    reduction = 100 * (1 - lite / full) if full else 0
    print(f"bootstrap.json {lite:,} bytes from {full:,} bytes ({reduction:.1f}% smaller)")


if __name__ == "__main__":
    main()
