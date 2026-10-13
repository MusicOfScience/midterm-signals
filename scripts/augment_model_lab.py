#!/usr/bin/env python3
"""Add paired polling and movement diagnostics to a generated Model Lab artefact.

This script is deliberately downstream of scripts/model_lab.py. It reads already-
frozen checkpoint predictions and certified outcomes only to evaluate whether the
race-poll blend improved those same forecasts relative to their structural +
generic-ballot prior, and to label roster-state changes in movement forensics.
It never changes a prediction or model coefficient.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_LAB = ROOT / "public" / "data" / "model-lab.json"
HISTORICAL = ROOT / "historical"
PROBABILITY_CLAMP = (0.001, 0.999)
SIGMA = {"house": 6.3, "senate": 7.2}
MOVEMENT_THRESHOLD = 0.10


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def read_results(year: int) -> dict[str, int]:
    path = HISTORICAL / str(year) / "results.csv"
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = csv.DictReader(fh)
        out = {}
        for row in rows:
            code = (row.get("race_code") or "").strip()
            party = (row.get("winner_party") or "").strip().upper()
            if code and party in {"DEM", "REP"}:
                if code in out:
                    raise ValueError(f"Duplicate outcome {year} {code}")
                out[code] = 1 if party == "DEM" else 0
        return out


def log_loss(probs: list[float], outcomes: list[int]) -> float:
    total = 0.0
    for p, y in zip(probs, outcomes):
        q = clamp(p, 1e-15, 1 - 1e-15)
        total -= y * math.log(q) + (1 - y) * math.log(1 - q)
    return total / len(probs)


def brier(probs: list[float], outcomes: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / len(probs)


def prior_probability(pred: dict) -> float:
    chamber = (pred.get("race_type") or "house").lower()
    sigma = SIGMA[chamber]
    p = normal_cdf(float(pred["prior_margin"]) / sigma)
    return clamp(p, *PROBABILITY_CLAMP)


def paired_summary(predictions: list[dict], outcomes: dict[str, int], *, prior_competitive_only: bool = False) -> dict:
    rows = []
    for pred in predictions:
        if int(pred.get("poll_count") or 0) <= 0:
            continue
        code = pred["race_code"]
        if code not in outcomes:
            continue
        prior = prior_probability(pred)
        if prior_competitive_only and not 0.20 <= prior <= 0.80:
            continue
        full = float(pred["dem_probability"])
        y = outcomes[code]
        directed = (1 if y else -1) * (full - prior)
        rows.append((code, prior, full, y, directed))
    if not rows:
        return {"state": "unavailable", "n": 0}
    prior_probs = [r[1] for r in rows]
    full_probs = [r[2] for r in rows]
    ys = [r[3] for r in rows]
    prior_brier = brier(prior_probs, ys)
    full_brier = brier(full_probs, ys)
    prior_ll = log_loss(prior_probs, ys)
    full_ll = log_loss(full_probs, ys)
    toward = sum(r[4] > 0 for r in rows)
    away = sum(r[4] < 0 for r in rows)
    unchanged = len(rows) - toward - away
    return {
        "state": "scored",
        "n": len(rows),
        "prior_brier": round(prior_brier, 8),
        "with_race_polls_brier": round(full_brier, 8),
        "brier_delta_with_polls_minus_prior": round(full_brier - prior_brier, 8),
        "prior_log_loss": round(prior_ll, 8),
        "with_race_polls_log_loss": round(full_ll, 8),
        "log_loss_delta_with_polls_minus_prior": round(full_ll - prior_ll, 8),
        "mean_absolute_probability_change": round(sum(abs(r[2] - r[1]) for r in rows) / len(rows), 6),
        "mean_winner_directed_probability_change": round(sum(r[4] for r in rows) / len(rows), 6),
        "moved_toward_eventual_winner": toward,
        "moved_away_from_eventual_winner": away,
        "unchanged": unchanged,
        "interpretation": "Negative score deltas mean the admitted race-poll blend improved the same frozen forecasts versus their structural + generic-ballot prior. This is a paired model-component diagnostic, not a causal claim about polling generally.",
    }


def transition_partition(previous: dict[str, dict], current: dict[str, dict], outcomes: dict[str, int]) -> dict:
    common = sorted(set(previous) & set(current) & set(outcomes))
    groups = {"later_polled": [], "later_unpolled": [], "newly_polled": []}
    for code in common:
        a, b = previous[code], current[code]
        p0, p1 = float(a["dem_probability"]), float(b["dem_probability"])
        y = outcomes[code]
        directed = (1 if y else -1) * (p1 - p0)
        row = (abs(p1 - p0), directed)
        key = "later_polled" if int(b.get("poll_count") or 0) > 0 else "later_unpolled"
        groups[key].append(row)
        if int(a.get("poll_count") or 0) == 0 and int(b.get("poll_count") or 0) > 0:
            groups["newly_polled"].append(row)

    def summarize(rows: list[tuple[float, float]]) -> dict:
        if not rows:
            return {"state": "unavailable", "n": 0}
        return {
            "state": "scored",
            "n": len(rows),
            "mean_absolute_probability_change": round(sum(r[0] for r in rows) / len(rows), 6),
            "mean_winner_directed_probability_change": round(sum(r[1] for r in rows) / len(rows), 6),
            "toward_eventual_winner": sum(r[1] > 0 for r in rows),
            "away_from_eventual_winner": sum(r[1] < 0 for r in rows),
            "strong_toward_eventual_winner": sum(r[1] >= MOVEMENT_THRESHOLD for r in rows),
            "strong_away_from_eventual_winner": sum(r[1] <= -MOVEMENT_THRESHOLD for r in rows),
        }

    return {key: summarize(rows) for key, rows in groups.items()}


def roster_transitions(previous: dict[str, dict], current: dict[str, dict], outcomes: dict[str, int]) -> dict:
    changes = []
    for code in sorted(set(previous) & set(current) & set(outcomes)):
        a, b = previous[code], current[code]
        before = (a.get("dem_candidate"), a.get("rep_candidate"))
        after = (b.get("dem_candidate"), b.get("rep_candidate"))
        if before == after:
            continue
        p0, p1 = float(a["dem_probability"]), float(b["dem_probability"])
        y = outcomes[code]
        directed = (1 if y else -1) * (p1 - p0)
        changes.append({
            "race_code": code,
            "race_type": b.get("race_type"),
            "before": {"dem_candidate": before[0], "rep_candidate": before[1]},
            "after": {"dem_candidate": after[0], "rep_candidate": after[1]},
            "dem_probability_before": round(p0, 6),
            "dem_probability_after": round(p1, 6),
            "absolute_probability_change": round(abs(p1 - p0), 6),
            "winner_directed_probability_change": round(directed, 6),
            "large_movement": abs(p1 - p0) >= MOVEMENT_THRESHOLD,
        })
    changes.sort(key=lambda r: r["absolute_probability_change"], reverse=True)
    return {
        "count": len(changes),
        "large_movement_count": sum(r["large_movement"] for r in changes),
        "changes": changes,
        "interpretation": "Candidate-roster changes are preserved as historical information-state changes but are labelled separately so they are not mistaken for ordinary polling/news movement.",
    }


def augment(payload: dict) -> dict:
    for cycle in payload.get("cycles", []):
        if cycle.get("state") != "scored":
            continue
        year = int(cycle["cycle"])
        outcomes = read_results(year)
        checkpoints = cycle.get("checkpoints", [])
        for cp in checkpoints:
            if cp.get("score", {}).get("state") != "scored":
                continue
            predictions = cp.get("predictions") or []
            cp["score"]["polling"]["paired_component_test"] = paired_summary(predictions, outcomes)
            cp["score"]["polling"]["paired_component_test_prior_20_80"] = paired_summary(
                predictions, outcomes, prior_competitive_only=True
            )

        by_day = {
            int(cp["days_to_election"]): {p["race_code"]: p for p in (cp.get("predictions") or [])}
            for cp in checkpoints
            if cp.get("state") == "scored"
        }
        movement = cycle.get("movement") or {}
        if movement.get("state") == "scored":
            partitions = []
            roster = []
            days = payload.get("checkpoints_days_to_election") or [60, 30, 14, 7, 1]
            for earlier, later in zip(days, days[1:]):
                if earlier in by_day and later in by_day:
                    partitions.append({
                        "from_days": earlier,
                        "to_days": later,
                        **transition_partition(by_day[earlier], by_day[later], outcomes),
                    })
                    roster.append({
                        "from_days": earlier,
                        "to_days": later,
                        **roster_transitions(by_day[earlier], by_day[later], outcomes),
                    })
            movement["polling_partitions"] = partitions
            movement["roster_transitions"] = roster

    payload.setdefault("metric_definitions", {})["paired_polling_component_test"] = (
        "For races with eligible race-level polls, compares the published checkpoint probability with that same race's frozen structural + generic-ballot prior before the race-poll blend. Negative Brier/log-loss delta means the race-poll component improved the paired forecasts. Outcomes are used only after both probabilities exist."
    )
    payload.setdefault("metric_definitions", {})["roster_transition"] = (
        "A change in the admitted candidate pair between fixed checkpoints. These information-state changes remain in the frozen historical forecast but are labelled separately in movement forensics."
    )
    payload.setdefault("leakage_guards", []).append(
        "Paired polling-component diagnostics are computed only after the published checkpoint probabilities are frozen; certified outcomes are used solely to score the frozen full and prior probabilities."
    )
    payload.setdefault("diagnostic_contract", {})["paired_polling_component_test"] = {
        "counterfactual": "same race, same checkpoint, same structural + generic-ballot prior, race-level poll blend removed",
        "competitive_subset": "prior probability 20-80%",
        "model_effect": "NONE",
    }
    payload.setdefault("diagnostic_contract", {})["roster_transition_policy"] = {
        "rule": "preserve frozen probability; label candidate-pair changes separately in movement diagnostics",
        "model_effect": "NONE",
    }
    return payload


def main() -> None:
    payload = json.loads(MODEL_LAB.read_text(encoding="utf-8"))
    augmented = augment(payload)
    MODEL_LAB.write_text(json.dumps(augmented, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(MODEL_LAB), "cycles": [c.get("cycle") for c in augmented.get("cycles", [])]}))


if __name__ == "__main__":
    main()
