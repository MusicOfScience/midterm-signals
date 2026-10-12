#!/usr/bin/env python3
"""Fail-closed validation for published MIDTERM SIGNALS artifacts."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORECAST = ROOT / "public" / "data" / "forecast.json"
STATUS = ROOT / "public" / "data" / "status.json"

def load(path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

def assert_prob(value, label):
    if not 0 <= float(value) <= 1:
        raise AssertionError(f"{label} outside [0,1]: {value}")

f = load(FORECAST)
s = load(STATUS)
assert f["election_date"] == "2026-11-03"
assert f["publication_state"] == "published_provisional"
assert s["production_forecast"] == "published"
assert f["house"]["total_seats"] == 435
assert sum(f["house"]["rating_counts"].values()) == 435
assert f["house"]["competitive_race_count"] == 76
assert len(f["house"]["competitive_races"]) == 76
assert f["house"]["solid_races_aggregated"] == 359
assert f["senate"]["total_seats"] == 100
assert f["senate"]["contested_seats"] == 35
assert len(f["senate"]["races"]) == 35
assert f["senate"]["not_up"]["democratic_caucus"] + f["senate"]["not_up"]["republican"] == 65
assert_prob(f["house"]["democratic_control_probability"], "House D control")
assert_prob(f["senate"]["democratic_control_probability"], "Senate D control")
for k, v in f["joint_control"].items(): assert_prob(v, f"joint {k}")
if abs(sum(f["joint_control"].values()) - 1) > 0.001: raise AssertionError("joint control probabilities do not sum to 1")
house_ids = [r["race_id"] for r in f["house"]["competitive_races"]]
if len(set(house_ids)) != len(house_ids): raise AssertionError("duplicate House race ID")
senate_states = [r["state"] for r in f["senate"]["races"]]
if len(set(senate_states)) != 35: raise AssertionError("duplicate/missing Senate states")
for row in f["house"]["competitive_races"]: assert_prob(row["map_prior_probability_dem"], f"House {row['race_id']}")
for row in f["senate"]["races"]:
    assert_prob(row["forecast_probability_dem_or_non_r"], f"Senate {row['state']}")
    assert_prob(row["democratic_control_credit_probability"], f"Senate control {row['state']}")
if f["national_environment"]["presidential_approval"]["model_coefficient"] != 0.0: raise AssertionError("presidential approval must remain descriptive in v0.1")
for name, digest in f["input_sha256"].items():
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest): raise AssertionError(f"invalid SHA-256 for {name}")
print("MIDTERM SIGNALS forecast validation passed.")
