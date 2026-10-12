"""Compact forecast-history metadata for MIDTERM SIGNALS.

The immutable full snapshots remain the source of truth. This module maintains
small derivative indices so public history/race pages do not download dozens
of full snapshots merely to draw timelines.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _summary(snapshot: dict, filename: str) -> dict:
    house = snapshot.get("summary", {}).get("house", {})
    senate = snapshot.get("summary", {}).get("senate", {})
    env = snapshot.get("national_environment", {})
    prov = snapshot.get("provenance", {})
    change = snapshot.get("change_summary", {})
    return {
        "file": filename,
        "generated_at": snapshot.get("generated_at"),
        "house": house.get("dem_control_probability"),
        "senate": senate.get("dem_control_probability"),
        "house_seats": house.get("expected_dem_seats"),
        "senate_seats": senate.get("expected_dem_seats"),
        "generic_ballot_d_minus_r": env.get("generic_ballot_d_minus_r"),
        "model": snapshot.get("model"),
        "upstream_commit": prov.get("upstream_commit"),
        "input_sha256": prov.get("input_sha256"),
        "changed_inputs": change.get("changed_inputs", []),
    }


def merge_history_summaries(index_path: Path, current: dict, filename: str, limit: int = 240) -> list[dict]:
    """Return compact summaries including current, newest first."""
    index = _read_json(index_path, {})
    existing = [x for x in index.get("summaries", []) if isinstance(x, dict)]
    if not existing:
        hist_dir = index_path.parent
        for path in sorted((p for p in hist_dir.glob("*.json") if p.name not in {"index.json", "race-series.json"}), reverse=True)[:36]:
            snap = _read_json(path, None)
            if isinstance(snap, dict):
                existing.append(_summary(snap, path.name))
    merged: dict[str, dict] = {x.get("file"): x for x in existing if x.get("file")}
    merged[filename] = _summary(current, filename)
    rows = sorted(merged.values(), key=lambda x: (x.get("generated_at") or "", x.get("file") or ""), reverse=True)
    return rows[:limit]


def _seed_race_series(hist_dir: Path, max_snapshots: int = 36) -> dict[str, list[dict]]:
    series: dict[str, list[dict]] = {}
    paths = sorted((p for p in hist_dir.glob("*.json") if p.name not in {"index.json", "race-series.json"}), key=lambda p: p.name)[-max_snapshots:]
    for path in paths:
        snap = _read_json(path, None)
        if not isinstance(snap, dict):
            continue
        generated_at = snap.get("generated_at")
        for race in snap.get("races", []):
            p = race.get("dem_probability")
            if race.get("race_type") != "senate" and not (isinstance(p, (int, float)) and 0.02 <= p <= 0.98):
                continue
            code = race.get("race_code")
            if not code:
                continue
            series.setdefault(code, []).append({
                "generated_at": generated_at,
                "dem_probability": p,
                "margin": race.get("forecast_margin_d_minus_r"),
                "poll_count": race.get("poll_count"),
                "rating": race.get("rating"),
            })
    return series


def write_history_artifacts(hist_dir: Path, current: dict, filename: str, summaries: list[dict], *, snapshot_limit: int = 240, race_point_limit: int = 180) -> None:
    """Write compact index and race series without altering full snapshots."""
    hist_dir.mkdir(parents=True, exist_ok=True)
    snapshots = sorted([p.name for p in hist_dir.glob("*.json") if p.name not in {"index.json", "race-series.json"}], reverse=True)[:snapshot_limit]
    index = {
        "schema_version": 2,
        "generated_at": current.get("generated_at"),
        "snapshots": snapshots,
        "summaries": summaries[:snapshot_limit],
        "note": "Full snapshot files are immutable; summaries are derivative navigation metadata.",
    }
    (hist_dir / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    series_path = hist_dir / "race-series.json"
    previous = _read_json(series_path, {})
    races: dict[str, list[dict]] = previous.get("races", {}) if isinstance(previous, dict) else {}
    if not races:
        races = _seed_race_series(hist_dir)

    generated_at = current.get("generated_at")
    for race in current.get("races", []):
        code = race.get("race_code")
        p = race.get("dem_probability")
        if not code:
            continue
        already_tracked = code in races
        should_track = race.get("race_type") == "senate" or already_tracked or (isinstance(p, (int, float)) and 0.02 <= p <= 0.98)
        if not should_track:
            continue
        point = {
            "generated_at": generated_at,
            "dem_probability": p,
            "margin": race.get("forecast_margin_d_minus_r"),
            "poll_count": race.get("poll_count"),
            "rating": race.get("rating"),
        }
        points = [x for x in races.get(code, []) if x.get("generated_at") != generated_at]
        points.append(point)
        points.sort(key=lambda x: x.get("generated_at") or "")
        races[code] = points[-race_point_limit:]

    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "races": races,
        "note": "Compact derivative series; immutable full snapshots remain authoritative.",
    }
    series_path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
