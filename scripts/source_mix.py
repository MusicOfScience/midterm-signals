#!/usr/bin/env python3
"""Add pollster/source-mix diagnostics to the MIDTERM SIGNALS Model Lab.

This sidecar is evaluation-only. It reconstructs the exact race-poll rows used by
frozen historical checkpoints, assigns source-mix bands using polling metadata
only, and only then opens certified D/R result margins for scoring. It never
changes a forecast probability or production-model coefficient.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import model_lab as core
import polling_error as pe

ROOT = Path(__file__).resolve().parents[1]
MODEL_LAB = ROOT / "public" / "data" / "model-lab.json"
HISTORICAL = ROOT / "historical"
TOP_SOURCE_CONCENTRATION_THRESHOLD = 2.0 / 3.0
POLLSTER_MIN_RACE_SOURCES = 5

DEPTH_BANDS = (
    ("one_poll", lambda n: n == 1),
    ("two_polls", lambda n: n == 2),
    ("three_four_polls", lambda n: 3 <= n <= 4),
    ("five_plus_polls", lambda n: n >= 5),
)
SOURCE_COUNT_BANDS = (
    ("one_pollster", lambda n: n == 1),
    ("two_pollsters", lambda n: n == 2),
    ("three_plus_pollsters", lambda n: n >= 3),
)
CONCENTRATION_BANDS = ("single_source", "concentrated_multi", "diversified_multi")
SPONSOR_BANDS = ("no_partisan_labeled", "mixed_partisan_labeled", "all_partisan_labeled")


def poll_margin(row: dict) -> float:
    margin = core.number(row, "margin")
    if margin is not None:
        return float(margin)
    dem = core.number(row, "dem", 0.0) or 0.0
    rep = core.number(row, "rep", 0.0) or 0.0
    return float(dem - rep)


def eligible_race_poll_rows(polls: list[dict], race: dict, cutoff) -> list[dict]:
    """Return the exact pre-outcome race-poll rows eligible under the frozen model."""
    usable = []
    for row in core.rows_known_by(polls, cutoff):
        if (row.get("kind") or "").lower() not in {"race", "race_poll"}:
            continue
        if row.get("race_code") != race.get("race_code"):
            continue
        end = core.parse_day(row.get("end_date"))
        if not end or end > cutoff or (cutoff - end).days > core.MODEL_CONTRACT["race_polls"]["window_days"]:
            continue
        if race.get("dem_name") and not core.candidate_match(row.get("dem_name"), race.get("dem_name")):
            continue
        if race.get("rep_name") and not core.candidate_match(row.get("rep_name"), race.get("rep_name")):
            continue
        usable.append(row)
    return usable


def band_for(value: int, definitions) -> str:
    for label, predicate in definitions:
        if predicate(int(value)):
            return label
    raise ValueError(f"No source-mix band for value {value}")


def source_profile(pred: dict, race: dict, polls: list[dict], cutoff) -> dict:
    """Assign source-mix features using predictive polling metadata only."""
    usable = eligible_race_poll_rows(polls, race, cutoff)
    if not usable:
        raise ValueError(f"No eligible source rows for polled race {pred.get('race_code')}")

    latest = max(core.parse_day(r.get("end_date")) for r in usable if core.parse_day(r.get("end_date")))
    weighted = [(core.poll_weight(r, latest, core.MODEL_CONTRACT["race_polls"]["half_life_days"]), r) for r in usable]
    den = sum(w for w, _ in weighted)
    if den <= 0:
        raise ValueError(f"Non-positive source weight for {pred.get('race_code')}")

    raw_margin = sum(w * poll_margin(r) for w, r in weighted) / den
    cfg = core.MODEL_CONTRACT["race_polls"]
    blend = core.clamp(cfg["blend_scale"] * math.sqrt(len(usable)), cfg["blend_min"], cfg["blend_max"])
    blend *= 0.75 + 0.25 * math.exp(-max(0, (cutoff - latest).days) / cfg["freshness_days"])

    expected_count = int(pred.get("poll_count") or 0)
    if len(usable) != expected_count:
        raise ValueError(f"Source-mix poll-count drift {pred.get('race_code')}: {len(usable)} != {expected_count}")
    if abs(float(blend) - float(pred.get("poll_weight") or 0.0)) > 0.00002:
        raise ValueError(f"Source-mix blend drift {pred.get('race_code')}: {blend} != {pred.get('poll_weight')}")
    if latest.isoformat() != pred.get("latest_race_poll"):
        raise ValueError(f"Source-mix latest-poll drift {pred.get('race_code')}")
    frozen_raw, _, _, _ = core.race_poll_average(polls, race, cutoff)
    if frozen_raw is None or abs(float(frozen_raw) - raw_margin) > 1e-9:
        raise ValueError(f"Source-mix raw aggregate drift {pred.get('race_code')}")

    by_pollster: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    partisan_weight = 0.0
    weighted_rating_num = 0.0
    for weight, row in weighted:
        pollster = (row.get("pollster") or "").strip() or "(unknown pollster)"
        by_pollster[pollster].append((weight, row))
        if (row.get("lean") or "").strip().upper() in {"D", "R"}:
            partisan_weight += weight
        rating = core.number(row, "rating", 1.3)
        weighted_rating_num += weight * float(1.3 if rating is None else rating)

    source_signals = []
    for pollster, items in sorted(by_pollster.items()):
        source_weight = sum(w for w, _ in items)
        source_signals.append({
            "pollster": pollster,
            "poll_count": len(items),
            "weight_share": round(source_weight / den, 9),
            "margin_d_minus_r": round(sum(w * poll_margin(r) for w, r in items) / source_weight, 9),
            "mean_rating": round(sum(w * float(core.number(r, "rating", 1.3) or 1.3) for w, r in items) / source_weight, 6),
            "partisan_labeled_weight_share": round(sum(w for w, r in items if (r.get("lean") or "").strip().upper() in {"D", "R"}) / source_weight, 9),
        })

    shares = [float(s["weight_share"]) for s in source_signals]
    unique_pollsters = len(source_signals)
    top_share = max(shares)
    if unique_pollsters == 1:
        concentration_band = "single_source"
    elif top_share >= TOP_SOURCE_CONCENTRATION_THRESHOLD:
        concentration_band = "concentrated_multi"
    else:
        concentration_band = "diversified_multi"

    partisan_share = partisan_weight / den
    if partisan_share <= 1e-12:
        sponsor_band = "no_partisan_labeled"
    elif partisan_share >= 1 - 1e-12:
        sponsor_band = "all_partisan_labeled"
    else:
        sponsor_band = "mixed_partisan_labeled"

    top_source = max(source_signals, key=lambda s: (s["weight_share"], s["pollster"]))
    return {
        "race_code": pred["race_code"],
        "race_type": pred.get("race_type"),
        "raw_poll_margin_d_minus_r": round(raw_margin, 9),
        "prior_margin_d_minus_r": float(pred["prior_margin"]),
        "full_model_margin_d_minus_r": float(pred["forecast_margin_d_minus_r"]),
        "poll_count": len(usable),
        "poll_depth_band": band_for(len(usable), DEPTH_BANDS),
        "unique_pollsters": unique_pollsters,
        "source_count_band": band_for(unique_pollsters, SOURCE_COUNT_BANDS),
        "top_source_weight_share": round(top_share, 9),
        "source_hhi": round(sum(s * s for s in shares), 9),
        "concentration_band": concentration_band,
        "partisan_labeled_weight_share": round(partisan_share, 9),
        "sponsor_band": sponsor_band,
        "weighted_mean_rating": round(weighted_rating_num / den, 6),
        "top_source_pollster": top_source["pollster"],
        "top_source_pollster_weight_share": top_source["weight_share"],
        "source_signals": source_signals,
    }


def score_rows(rows: list[dict]) -> dict:
    if not rows:
        return {"state": "unavailable", "n": 0}
    return {
        "state": "scored",
        "n": len(rows),
        "mean_poll_count": round(sum(r["poll_count"] for r in rows) / len(rows), 6),
        "mean_unique_pollsters": round(sum(r["unique_pollsters"] for r in rows) / len(rows), 6),
        "mean_top_source_weight_share": round(sum(r["top_source_weight_share"] for r in rows) / len(rows), 6),
        "mean_source_hhi": round(sum(r["source_hhi"] for r in rows) / len(rows), 6),
        "mean_partisan_labeled_weight_share": round(sum(r["partisan_labeled_weight_share"] for r in rows) / len(rows), 6),
        "raw_poll": pe.error_metrics(rows, "raw_poll_margin_d_minus_r"),
        "prior": pe.error_metrics(rows, "prior_margin_d_minus_r"),
        "full_model": pe.error_metrics(rows, "full_model_margin_d_minus_r"),
    }


def grouped(rows: list[dict], key: str, labels: tuple[str, ...]) -> list[dict]:
    return [{"band": label, **score_rows([r for r in rows if r.get(key) == label])} for label in labels]


def pollster_table(rows: list[dict]) -> dict:
    by_pollster: dict[str, list[dict]] = defaultdict(list)
    all_pollsters = set()
    for row in rows:
        result = float(row["result_margin_d_minus_r"])
        for signal in row.get("source_signals") or []:
            pollster = signal["pollster"]
            all_pollsters.add(pollster)
            by_pollster[pollster].append({
                "pollster": pollster,
                "race_code": row["race_code"],
                "source_margin_d_minus_r": float(signal["margin_d_minus_r"]),
                "result_margin_d_minus_r": result,
                "weight_share": float(signal["weight_share"]),
                "mean_rating": float(signal["mean_rating"]),
                "partisan_labeled_weight_share": float(signal["partisan_labeled_weight_share"]),
            })

    reported = []
    for pollster, signals in by_pollster.items():
        if len(signals) < POLLSTER_MIN_RACE_SOURCES:
            continue
        metrics = pe.error_metrics(signals, "source_margin_d_minus_r")
        reported.append({
            "pollster": pollster,
            "n_race_sources": len(signals),
            "mean_model_weight_share": round(sum(s["weight_share"] for s in signals) / len(signals), 6),
            "mean_rating": round(sum(s["mean_rating"] for s in signals) / len(signals), 6),
            "mean_partisan_labeled_weight_share": round(sum(s["partisan_labeled_weight_share"] for s in signals) / len(signals), 6),
            "source_margin_error": metrics,
        })
    reported.sort(key=lambda r: (-r["n_race_sources"], r["pollster"].lower()))
    return {
        "minimum_distinct_race_sources": POLLSTER_MIN_RACE_SOURCES,
        "reported_pollsters": reported,
        "reported_pollster_count": len(reported),
        "all_pollster_count": len(all_pollsters),
        "suppressed_small_sample_pollster_count": len(all_pollsters) - len(reported),
        "ordering": "sample size descending, then pollster name; never ranked by error",
    }


def checkpoint_source_mix(checkpoint: dict, races: list[dict], polls: list[dict], result_margins: dict[str, float]) -> dict:
    cutoff = core.parse_day(checkpoint.get("cutoff"))
    if not cutoff:
        return {"state": "unavailable", "reason": "invalid_checkpoint_cutoff", "n": 0}
    active = {r["race_code"]: r for r in core.select_race_versions(races, cutoff)}

    profiles = []
    for pred in checkpoint.get("predictions") or []:
        if int(pred.get("poll_count") or 0) <= 0 or not pe.two_major_party_prediction(pred):
            continue
        race = active.get(pred.get("race_code"))
        if race is None:
            raise ValueError(f"Source-mix active roster missing {pred.get('race_code')}")
        profiles.append(source_profile(pred, race, polls, cutoff))

    # Outcome margins are joined only after every source-mix feature above is frozen.
    rows = []
    missing = []
    for profile in profiles:
        code = profile["race_code"]
        if code not in result_margins:
            missing.append(code)
            continue
        rows.append({**profile, "result_margin_d_minus_r": float(result_margins[code])})

    if not rows:
        return {"state": "unavailable", "reason": "no_source_mix_rows_with_certified_margin", "n": 0, "missing_result_margin_races": sorted(set(missing))}

    house = [r for r in rows if (r.get("race_type") or "").lower() == "house"]
    senate = [r for r in rows if (r.get("race_type") or "").lower() == "senate"]

    def scope_block(scope_rows: list[dict]) -> dict:
        if not scope_rows:
            return {"state": "unavailable", "n": 0}
        return {
            "state": "scored",
            "n": len(scope_rows),
            "overall": score_rows(scope_rows),
            "by_poll_depth": grouped(scope_rows, "poll_depth_band", tuple(label for label, _ in DEPTH_BANDS)),
            "by_unique_pollsters": grouped(scope_rows, "source_count_band", tuple(label for label, _ in SOURCE_COUNT_BANDS)),
            "by_source_concentration": grouped(scope_rows, "concentration_band", CONCENTRATION_BANDS),
            "by_partisan_label_share": grouped(scope_rows, "sponsor_band", SPONSOR_BANDS),
            "pollsters": pollster_table(scope_rows),
        }

    return {
        "state": "scored",
        "n": len(rows),
        "scope": "scoreable polled two-major-party races with admitted certified D/R result margin",
        "feature_assignment_uses_outcomes": False,
        "missing_result_margin_races": sorted(set(missing)),
        "all_polled": scope_block(rows),
        "house_only": scope_block(house),
        "senate_only": scope_block(senate),
        "interpretation": "Source-mix bands are assigned entirely from the exact polling rows and weights available at the checkpoint. Outcome margins are joined only afterward for scoring. Differences are descriptive and can reflect race selection, competitiveness, geography or source availability rather than a causal pollster effect.",
    }


def cross_cycle(payload: dict) -> dict:
    rows = []
    for cycle in payload.get("cycles", []):
        if cycle.get("state") != "scored":
            continue
        cp = next((c for c in cycle.get("checkpoints", []) if int(c.get("days_to_election") or -1) == 1), None)
        block = (cp or {}).get("score", {}).get("source_mix", {}).get("house_only")
        if not block or block.get("state") != "scored":
            continue
        rows.append({
            "cycle": cycle["cycle"],
            "n": block["n"],
            "by_poll_depth": block["by_poll_depth"],
            "by_unique_pollsters": block["by_unique_pollsters"],
            "by_source_concentration": block["by_source_concentration"],
            "by_partisan_label_share": block["by_partisan_label_share"],
            "reported_pollsters": block["pollsters"]["reported_pollsters"],
        })
    return {
        "state": "scored" if len(rows) >= 2 else "partial",
        "checkpoint_days_to_election": 1,
        "scope": "House-only same checkpoint; source bands assigned pre-outcome",
        "cycles": rows,
        "interpretation": "Cross-cycle source-mix contrasts are descriptive. Different races attract different polling depth and pollsters, so these tables do not estimate causal source effects.",
    }


def augment(payload: dict) -> dict:
    for cycle in payload.get("cycles", []):
        if cycle.get("state") != "scored":
            continue
        year = int(cycle["cycle"])
        cycle_dir = HISTORICAL / str(year)
        races = pe.read_csv(cycle_dir / "races.csv")
        polls = pe.read_csv(cycle_dir / "polls.csv")
        result_margins = pe.load_result_margins(year)
        if not result_margins:
            raise RuntimeError(f"No admitted result margins for source-mix audit {year}")
        for checkpoint in cycle.get("checkpoints", []):
            if checkpoint.get("state") != "scored":
                continue
            checkpoint.setdefault("score", {})["source_mix"] = checkpoint_source_mix(checkpoint, races, polls, result_margins)

    payload.setdefault("diagnostic_contract", {})["source_mix"] = {
        "scope": "scoreable races with eligible race-level polls and admitted certified D/R result margins",
        "poll_depth_bands": ["1", "2", "3-4", "5+"],
        "unique_pollster_bands": ["1", "2", "3+"],
        "top_source_concentration_threshold": TOP_SOURCE_CONCENTRATION_THRESHOLD,
        "partisan_label_rule": "lean D/R counts as partisan-labelled; N or blank is not claimed to be neutral, only not labelled partisan",
        "pollster_minimum_distinct_race_sources": POLLSTER_MIN_RACE_SOURCES,
        "pollster_table_ordering": "sample size descending, then name; never error-ranked",
        "polling_mode": "unavailable_not_in_historical_corpus",
        "feature_assignment_uses_outcomes": False,
        "model_effect": "NONE",
        "causal_boundary": "Depth, concentration, sponsor labels and pollster identity are observational characteristics of the admitted polling stream, not randomized treatments.",
    }
    payload.setdefault("metric_definitions", {})["source_concentration"] = (
        "Share of the exact model poll weight contributed by the largest pollster within a race/checkpoint; multi-source races at or above two-thirds are labelled concentrated."
    )
    payload.setdefault("metric_definitions", {})["pollster_race_source"] = (
        "One pollster's weighted aggregate within one race/checkpoint. Repeated polls by the same pollster in the same race count as one race-source observation in pollster tables."
    )
    payload.setdefault("leakage_guards", []).append(
        "Poll-depth, source-count, concentration and partisan-label bands are frozen from predictive poll metadata before certified outcome margins are joined; pollster tables use a fixed minimum of five distinct race-source observations and are never ranked by outcome error."
    )
    payload["source_mix_cross_cycle"] = cross_cycle(payload)
    for hypothesis in payload.get("cross_cycle", {}).get("hypotheses", []):
        if hypothesis.get("id") == "pollster_mix":
            hypothesis["state"] = "diagnostic_exposed"
            hypothesis["evidence"] = "checkpoint source_mix depth, source-count, concentration, partisan-label and pollster-race diagnostics"
    return payload


def main() -> None:
    payload = json.loads(MODEL_LAB.read_text(encoding="utf-8"))
    payload = augment(payload)
    MODEL_LAB.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(MODEL_LAB),
        "diagnostic": "source_mix",
        "cross_cycle_state": payload.get("source_mix_cross_cycle", {}).get("state"),
    }))


if __name__ == "__main__":
    main()
