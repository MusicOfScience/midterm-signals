#!/usr/bin/env python3
"""Add paired polling, structural-stage and movement diagnostics to Model Lab.

This script is deliberately downstream of scripts/model_lab.py. It reads already-
frozen checkpoint predictions and certified outcomes only to evaluate model
components after the fact. It never changes a prediction or model coefficient.
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
CONFIDENT_MISS_THRESHOLD = 0.80


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


def margin_probability(margin: float, chamber: str) -> float:
    sigma = SIGMA[(chamber or "house").lower()]
    return clamp(normal_cdf(float(margin) / sigma), *PROBABILITY_CLAMP)


def prior_probability(pred: dict) -> float:
    return margin_probability(float(pred["prior_margin"]), pred.get("race_type") or "house")


def two_major_party_contest(pred: dict) -> bool:
    dem = (pred.get("dem_candidate") or "").strip()
    rep = (pred.get("rep_candidate") or "").strip()
    return bool(
        dem
        and rep
        and not dem.lower().startswith("(no democrat)")
        and not rep.lower().startswith("(no republican)")
    )


def stage_metrics(probs: list[float], outcomes: list[int]) -> dict:
    return {
        "brier": round(brier(probs, outcomes), 8),
        "log_loss": round(log_loss(probs, outcomes), 8),
        "accuracy": round(sum((p >= 0.5) == bool(y) for p, y in zip(probs, outcomes)) / len(probs), 6),
    }


def structural_decomposition(
    predictions: list[dict],
    outcomes: dict[str, int],
    generic_ballot_margin: float | None,
    *,
    structural_competitive_only: bool = False,
) -> dict:
    """Score structural -> generic -> full stages on the same frozen races.

    ``prior_margin`` is the frozen structural+incumbency margin plus the checkpoint
    generic ballot. Subtracting the checkpoint generic ballot reconstructs the
    structural+incumbency stage without opening any new historical source. The
    calculation is evaluation-only and deliberately excludes no-opponent races so
    production's mechanical 0.001/0.999 branches cannot dominate the comparison.
    """
    if generic_ballot_margin is None:
        return {"state": "unavailable", "n": 0, "reason": "generic_ballot_margin_unavailable"}

    rows = []
    gcb = float(generic_ballot_margin)
    for pred in predictions:
        code = pred.get("race_code")
        if not code or code not in outcomes or not two_major_party_contest(pred):
            continue
        structural_margin = float(pred["prior_margin"]) - gcb
        structural = margin_probability(structural_margin, pred.get("race_type") or "house")
        if structural_competitive_only and not 0.20 <= structural <= 0.80:
            continue
        prior = prior_probability(pred)
        full = float(pred["dem_probability"])
        y = outcomes[code]
        sign = 1 if y else -1
        rows.append({
            "race_code": code,
            "race_type": pred.get("race_type"),
            "winner": "DEM" if y else "REP",
            "structural_margin_d_minus_r": structural_margin,
            "structural_probability": structural,
            "prior_probability": prior,
            "full_probability": full,
            "generic_winner_directed_change": sign * (prior - structural),
            "poll_winner_directed_change": sign * (full - prior),
            "total_winner_directed_change": sign * (full - structural),
        })

    if not rows:
        return {"state": "unavailable", "n": 0, "reason": "no_eligible_two_major_party_contests"}

    ys = [outcomes[r["race_code"]] for r in rows]
    structural_probs = [r["structural_probability"] for r in rows]
    prior_probs = [r["prior_probability"] for r in rows]
    full_probs = [r["full_probability"] for r in rows]
    structural_metrics = stage_metrics(structural_probs, ys)
    prior_metrics = stage_metrics(prior_probs, ys)
    full_metrics = stage_metrics(full_probs, ys)

    confident_misses = []
    for row in rows:
        y = outcomes[row["race_code"]]
        winner_probability = row["structural_probability"] if y else 1 - row["structural_probability"]
        if winner_probability > 1 - CONFIDENT_MISS_THRESHOLD:
            continue
        confident_misses.append({
            "race_code": row["race_code"],
            "race_type": row["race_type"],
            "winner": row["winner"],
            "winner_probability_structural": round(winner_probability, 6),
            "dem_probability_structural": round(row["structural_probability"], 6),
            "dem_probability_after_generic": round(row["prior_probability"], 6),
            "dem_probability_full": round(row["full_probability"], 6),
            "structural_margin_d_minus_r": round(row["structural_margin_d_minus_r"], 3),
            "generic_winner_directed_change": round(row["generic_winner_directed_change"], 6),
            "poll_winner_directed_change": round(row["poll_winner_directed_change"], 6),
            "total_winner_directed_change": round(row["total_winner_directed_change"], 6),
        })
    confident_misses.sort(key=lambda r: r["winner_probability_structural"])

    def direction_counts(key: str) -> dict:
        values = [r[key] for r in rows]
        return {
            "toward_eventual_winner": sum(v > 0 for v in values),
            "away_from_eventual_winner": sum(v < 0 for v in values),
            "unchanged": sum(v == 0 for v in values),
            "mean_winner_directed_probability_change": round(sum(values) / len(values), 6),
        }

    return {
        "state": "scored",
        "n": len(rows),
        "sample": "structural_20_80" if structural_competitive_only else "two_major_party_contests",
        "structural_plus_incumbency": structural_metrics,
        "structural_plus_generic_ballot": prior_metrics,
        "published_full_forecast": full_metrics,
        "brier_delta_generic_minus_structural": round(prior_metrics["brier"] - structural_metrics["brier"], 8),
        "brier_delta_full_minus_prior": round(full_metrics["brier"] - prior_metrics["brier"], 8),
        "brier_delta_full_minus_structural": round(full_metrics["brier"] - structural_metrics["brier"], 8),
        "log_loss_delta_generic_minus_structural": round(prior_metrics["log_loss"] - structural_metrics["log_loss"], 8),
        "log_loss_delta_full_minus_prior": round(full_metrics["log_loss"] - prior_metrics["log_loss"], 8),
        "log_loss_delta_full_minus_structural": round(full_metrics["log_loss"] - structural_metrics["log_loss"], 8),
        "generic_ballot_effect": direction_counts("generic_winner_directed_change"),
        "race_poll_effect": direction_counts("poll_winner_directed_change"),
        "total_information_effect": direction_counts("total_winner_directed_change"),
        "confident_structural_miss_threshold": CONFIDENT_MISS_THRESHOLD,
        "confident_structural_misses": confident_misses,
        "interpretation": "Negative score deltas mean the later stage improved the same frozen race sample. Structural means the admitted presidential relative-lean baseline plus the frozen incumbency term; generic ballot and race-poll stages are added sequentially. This exposes model-component performance but does not identify redistricting as a cause.",
    }


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
            gcb = cp.get("generic_ballot_margin_d_minus_r")
            cp["score"]["structural_decomposition"] = structural_decomposition(predictions, outcomes, gcb)
            cp["score"]["structural_decomposition_20_80"] = structural_decomposition(
                predictions, outcomes, gcb, structural_competitive_only=True
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
    payload.setdefault("metric_definitions", {})["structural_decomposition"] = (
        "On the same two-major-party race sample, scores the admitted structural presidential relative-lean plus incumbency stage, then the structural + generic-ballot prior, then the published full forecast. The structural stage is reconstructed as prior_margin minus the checkpoint generic-ballot margin. Negative deltas mean the later stage improved the same sample."
    )
    payload.setdefault("metric_definitions", {})["roster_transition"] = (
        "A change in the admitted candidate pair between fixed checkpoints. These information-state changes remain in the frozen historical forecast but are labelled separately in movement forensics."
    )
    payload.setdefault("leakage_guards", []).append(
        "Paired polling-component diagnostics are computed only after the published checkpoint probabilities are frozen; certified outcomes are used solely to score the frozen full and prior probabilities."
    )
    payload.setdefault("leakage_guards", []).append(
        "Structural-stage diagnostics reconstruct structural+incumbency probability only from already-frozen checkpoint prior_margin and generic-ballot margin; no post-election district or result field enters the predictive stage."
    )
    payload.setdefault("diagnostic_contract", {})["paired_polling_component_test"] = {
        "counterfactual": "same race, same checkpoint, same structural + generic-ballot prior, race-level poll blend removed",
        "competitive_subset": "prior probability 20-80%",
        "model_effect": "NONE",
    }
    payload.setdefault("diagnostic_contract", {})["structural_decomposition"] = {
        "stages": ["structural presidential relative lean + incumbency", "+ checkpoint generic ballot", "+ admitted race-poll blend / published full forecast"],
        "sample": "two-major-party contests only",
        "competitive_subset": "structural-stage Democratic probability 20-80%",
        "confident_miss_threshold": CONFIDENT_MISS_THRESHOLD,
        "redistricting_identified": False,
        "model_effect": "NONE",
    }
    payload.setdefault("diagnostic_contract", {})["roster_transition_policy"] = {
        "rule": "preserve frozen probability; label candidate-pair changes separately in movement diagnostics",
        "model_effect": "NONE",
    }

    for hypothesis in payload.get("cross_cycle", {}).get("hypotheses", []):
        if hypothesis.get("id") == "structural_priors_redistricting":
            hypothesis["state"] = "structural_component_exposed_redistricting_not_identified"
            hypothesis["evidence"] = (
                "Structural+incumbency, generic-ballot and full-forecast stages are now scored on the same frozen two-major-party races, including a fixed structural 20-80 subset and confident structural misses. This can diagnose structural weakness; it does not by itself identify redistricting as the cause."
            )
    return payload


def main() -> None:
    payload = json.loads(MODEL_LAB.read_text(encoding="utf-8"))
    augmented = augment(payload)
    MODEL_LAB.write_text(json.dumps(augmented, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(MODEL_LAB), "cycles": [c.get("cycle") for c in augmented.get("cycles", [])]}))


if __name__ == "__main__":
    main()
