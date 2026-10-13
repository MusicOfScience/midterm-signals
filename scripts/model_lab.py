#!/usr/bin/env python3
"""Build the MIDTERM SIGNALS Model Lab audit artefact.

Historical replay is evaluation, never tuning. A cycle is scored only when its
as-of corpus passes completeness and leakage gates. Missing or unverified data
remain explicitly unscored.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "historical"
OUT = ROOT / "public" / "data" / "model-lab.json"
PARTS = ROOT / "scripts" / "build_forecast_parts"
CHECKPOINT_DAYS = (60, 30, 14, 7, 1)
REQUIRED_FILES = ("races.csv", "polls.csv", "results.csv")

MODEL_CONTRACT = {
    "id": "baseline-v1.0-frozen",
    "origin": "v0.2 prospective coefficients, carried unchanged into PROD v1.0",
    "structural_weights": [0.05, 0.20, 0.75],
    "incumbency_margin": {"house": 1.0, "senate": 1.15},
    "generic_ballot": {"window_days": 35, "half_life_days": 11.0},
    "race_polls": {
        "window_days": 55,
        "half_life_days": 13.0,
        "blend_scale": 0.27,
        "blend_min": 0.20,
        "blend_max": 0.86,
        "freshness_days": 28.0,
    },
    "sigma": {"house": 6.3, "senate": 7.2, "poll_reduction": 0.42, "floor": 3.1},
    "probability_clamp": [0.001, 0.999],
    "rule": "No replay result may alter this contract or the live forecast.",
}

PRODUCTION_MARKERS = (
    "return 0.05 * m16 + 0.20 * m20 + 0.75 * m24",
    "inc_adj = 1.0 if inc == \"DEM\" else -1.0 if inc == \"REP\" else 0.0",
    "inc_adj *= 1.15",
    "(asof - d).days <= 35",
    "poll_weight(r, latest, 11.0)",
    "(asof - d).days > 55",
    "poll_weight(r, latest, 13.0)",
    "blend = clamp(0.27 * math.sqrt(len(chosen)), 0.20, 0.86)",
    "base_sigma = 6.3 if race.get(\"race_type\") == \"house\" else 7.2",
    "base_sigma * (1 - 0.42 * pweight)",
    "clamp(normal_cdf(margin / sigma), 0.001, 0.999)",
)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def contract_fingerprint() -> str:
    return hashlib.sha256(canonical(MODEL_CONTRACT).encode()).hexdigest()


def production_contract_state() -> dict:
    source = "".join(p.read_text() for p in sorted(PARTS.glob("*.pyfrag"), key=lambda p: int(p.stem)))
    missing = [marker for marker in PRODUCTION_MARKERS if marker not in source]
    return {
        "state": "verified" if not missing else "drift_detected",
        "contract_fingerprint_sha256": contract_fingerprint(),
        "checked_markers": len(PRODUCTION_MARKERS),
        "missing_markers": missing,
        "blocking": bool(missing),
    }


def parse_day(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except Exception:
        return None


def number(row: dict, key: str, default: float | None = None) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def surname(name: str | None) -> str:
    bits = [b.strip(".,'") for b in (name or "").lower().replace("-", " ").split()]
    return bits[-1] if bits else ""


def candidate_match(poll_name: str | None, race_name: str | None) -> bool:
    if not poll_name or not race_name:
        return False
    if "generic" in poll_name.lower():
        return True
    s = surname(race_name)
    return bool(s and s in poll_name.lower())


def available_date(row: dict) -> date | None:
    # A poll cannot be used before it was public. publication_date wins over
    # fieldwork end date when supplied; otherwise end_date is the conservative
    # available-date proxy required by the corpus schema.
    return parse_day(row.get("publication_date")) or parse_day(row.get("end_date"))


def rows_known_by(rows: list[dict], cutoff: date) -> list[dict]:
    return [r for r in rows if (available_date(r) is not None and available_date(r) <= cutoff)]


def select_race_versions(rows: list[dict], cutoff: date) -> list[dict]:
    grouped: dict[str, list[tuple[date, dict]]] = defaultdict(list)
    for row in rows:
        known = parse_day(row.get("known_date"))
        code = (row.get("race_code") or "").strip()
        if code and known and known <= cutoff:
            grouped[code].append((known, row))
    return [max(items, key=lambda item: item[0])[1] for _, items in sorted(grouped.items())]


def poll_weight(row: dict, latest: date, half_life: float) -> float:
    d = parse_day(row.get("end_date"))
    if not d:
        return 0.0
    age = max(0, (latest - d).days)
    quality = clamp(number(row, "rating", 1.3) or 1.3, 0.75, 3.0)
    n = max(250.0, number(row, "n", 800.0) or 800.0)
    sponsor = (row.get("lean") or "").strip().upper()
    sponsor_mult = 0.68 if sponsor in {"D", "R"} else 1.0
    return math.exp(-math.log(2) * age / half_life) * (quality / 1.5) ** 1.15 * math.sqrt(n / 1000.0) * sponsor_mult


def aggregate_generic(rows: list[dict], cutoff: date) -> tuple[float | None, int, str | None]:
    usable = []
    for row in rows_known_by(rows, cutoff):
        if (row.get("kind") or "").lower() not in {"generic", "generic_ballot"}:
            continue
        end = parse_day(row.get("end_date"))
        if end and end <= cutoff and (cutoff - end).days <= MODEL_CONTRACT["generic_ballot"]["window_days"]:
            usable.append(row)
    if not usable:
        return None, 0, None
    latest = max(parse_day(r.get("end_date")) for r in usable if parse_day(r.get("end_date")))
    weighted = [(poll_weight(r, latest, MODEL_CONTRACT["generic_ballot"]["half_life_days"]), r) for r in usable]
    den = sum(w for w, _ in weighted)
    if den <= 0:
        return None, 0, None
    margin = sum(w * ((number(r, "dem", 0.0) or 0.0) - (number(r, "rep", 0.0) or 0.0)) for w, r in weighted) / den
    return margin, len(usable), latest.isoformat()


def race_poll_average(rows: list[dict], race: dict, cutoff: date) -> tuple[float | None, float, int, str | None]:
    usable = []
    for row in rows_known_by(rows, cutoff):
        if (row.get("kind") or "").lower() not in {"race", "race_poll"}:
            continue
        if row.get("race_code") != race.get("race_code"):
            continue
        end = parse_day(row.get("end_date"))
        if not end or end > cutoff or (cutoff - end).days > MODEL_CONTRACT["race_polls"]["window_days"]:
            continue
        if race.get("dem_name") and not candidate_match(row.get("dem_name"), race.get("dem_name")):
            continue
        if race.get("rep_name") and not candidate_match(row.get("rep_name"), race.get("rep_name")):
            continue
        usable.append(row)
    if not usable:
        return None, 0.0, 0, None
    latest = max(parse_day(r.get("end_date")) for r in usable if parse_day(r.get("end_date")))
    weighted = [(poll_weight(r, latest, MODEL_CONTRACT["race_polls"]["half_life_days"]), r) for r in usable]
    den = sum(w for w, _ in weighted)
    if den <= 0:
        return None, 0.0, 0, None
    avg = sum(w * (number(r, "margin", (number(r, "dem", 0.0) or 0.0) - (number(r, "rep", 0.0) or 0.0)) or 0.0) for w, r in weighted) / den
    cfg = MODEL_CONTRACT["race_polls"]
    blend = clamp(cfg["blend_scale"] * math.sqrt(len(usable)), cfg["blend_min"], cfg["blend_max"])
    blend *= 0.75 + 0.25 * math.exp(-max(0, (cutoff - latest).days) / cfg["freshness_days"])
    return avg, blend, len(usable), latest.isoformat()


def relative_lean_cycle(race: dict, national: dict) -> float:
    margins = [number(race, key) for key in ("margin_earliest", "margin_middle", "margin_latest")]
    nationals = [national.get(key) for key in ("earliest", "middle", "latest")]
    if any(v is None for v in margins + nationals):
        raise ValueError(f"Missing structural baseline for {race.get('race_code')}")
    weights = MODEL_CONTRACT["structural_weights"]
    return sum(w * (m - n) for w, m, n in zip(weights, margins, nationals))


def race_probability(race: dict, polls: list[dict], gcb: float, cutoff: date, national: dict) -> dict:
    lean = relative_lean_cycle(race, national)
    inc = (race.get("incumbent_party") or "").upper()
    inc_adj = 1.0 if inc == "DEM" else -1.0 if inc == "REP" else 0.0
    if (race.get("race_type") or "").lower() == "senate":
        inc_adj *= MODEL_CONTRACT["incumbency_margin"]["senate"]
    prior = lean + gcb + inc_adj
    poll_margin, pweight, pcount, plast = race_poll_average(polls, race, cutoff)
    margin = prior if poll_margin is None else (1 - pweight) * prior + pweight * poll_margin
    same_party = (race.get("same_party") or "").upper()
    dem_name, rep_name = race.get("dem_name") or "", race.get("rep_name") or ""
    base_sigma = MODEL_CONTRACT["sigma"][(race.get("race_type") or "house").lower()]
    sigma = max(MODEL_CONTRACT["sigma"]["floor"], base_sigma * (1 - MODEL_CONTRACT["sigma"]["poll_reduction"] * pweight))
    if same_party == "DEM":
        p_dem = 0.999
    elif same_party == "REP":
        p_dem = 0.001
    elif not dem_name or dem_name.startswith("(No Democrat)"):
        p_dem = 0.001
    elif not rep_name or rep_name.startswith("(No Republican)"):
        p_dem = 0.999
    else:
        lo, hi = MODEL_CONTRACT["probability_clamp"]
        p_dem = clamp(normal_cdf(margin / sigma), lo, hi)
    return {
        "race_code": race["race_code"],
        "race_type": race.get("race_type"),
        "state": race.get("state"),
        "district": race.get("district") or None,
        "dem_candidate": dem_name or None,
        "rep_candidate": rep_name or None,
        "dem_probability": round(p_dem, 6),
        "rep_probability": round(1 - p_dem, 6),
        "forecast_margin_d_minus_r": round(margin, 3),
        "prior_margin": round(prior, 3),
        "poll_weight": round(pweight, 5),
        "poll_count": pcount,
        "latest_race_poll": plast,
        "cutoff": cutoff.isoformat(),
    }


def brier_score(probabilities: list[float], outcomes: list[int]) -> float:
    if not probabilities or len(probabilities) != len(outcomes):
        raise ValueError("Brier score requires equal non-empty probability/outcome vectors")
    return sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / len(probabilities)


def log_loss(probabilities: list[float], outcomes: list[int], eps: float = 1e-15) -> float:
    if not probabilities or len(probabilities) != len(outcomes):
        raise ValueError("Log loss requires equal non-empty probability/outcome vectors")
    total = 0.0
    for p, y in zip(probabilities, outcomes):
        q = clamp(float(p), eps, 1 - eps)
        total -= y * math.log(q) + (1 - y) * math.log(1 - q)
    return total / len(probabilities)


def calibration_bins(probabilities: list[float], outcomes: list[int], width: float = 0.1) -> list[dict]:
    bins = []
    steps = int(round(1 / width))
    for i in range(steps):
        lo, hi = i * width, (i + 1) * width
        idx = [j for j, p in enumerate(probabilities) if (lo <= p < hi) or (i == steps - 1 and p == 1)]
        if not idx:
            continue
        bins.append({
            "lower": round(lo, 3),
            "upper": round(hi, 3),
            "count": len(idx),
            "mean_probability": round(sum(probabilities[j] for j in idx) / len(idx), 6),
            "observed_rate": round(sum(outcomes[j] for j in idx) / len(idx), 6),
        })
    return bins


def calibration_logistic(probabilities: list[float], outcomes: list[int]) -> dict:
    if len(probabilities) < 8 or len(set(outcomes)) < 2:
        return {"intercept": None, "slope": None, "state": "insufficient_variation"}
    xs = [math.log(clamp(p, 1e-6, 1 - 1e-6) / (1 - clamp(p, 1e-6, 1 - 1e-6))) for p in probabilities]
    a, b = 0.0, 1.0
    for _ in range(40):
        fitted = [1 / (1 + math.exp(-clamp(a + b * x, -30, 30))) for x in xs]
        w = [max(1e-9, p * (1 - p)) for p in fitted]
        g0 = sum(y - p for y, p in zip(outcomes, fitted))
        g1 = sum((y - p) * x for y, p, x in zip(outcomes, fitted, xs))
        h00 = -sum(w)
        h01 = -sum(wi * x for wi, x in zip(w, xs))
        h11 = -sum(wi * x * x for wi, x in zip(w, xs))
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            return {"intercept": None, "slope": None, "state": "singular"}
        da = (h11 * g0 - h01 * g1) / det
        db = (-h01 * g0 + h00 * g1) / det
        a -= da
        b -= db
        if max(abs(da), abs(db)) < 1e-8:
            break
    return {"intercept": round(a, 6), "slope": round(b, 6), "state": "estimated"}


def score_checkpoint(predictions: list[dict], results: dict[str, int]) -> dict:
    codes = [p["race_code"] for p in predictions]
    if len(codes) != len(set(codes)):
        raise ValueError("Duplicate race prediction in checkpoint")
    missing = sorted(set(codes) - set(results))
    if missing:
        return {"state": "unscored", "reason": "outcomes_incomplete", "missing_outcomes": missing}
    probs = [float(p["dem_probability"]) for p in predictions]
    outcomes = [int(results[code]) for code in codes]
    cal = calibration_logistic(probs, outcomes)
    misses = []
    for pred, y in zip(predictions, outcomes):
        p = pred["dem_probability"] if y == 1 else pred["rep_probability"]
        picked_correctly = (pred["dem_probability"] >= 0.5) == bool(y)
        if not picked_correctly:
            misses.append({
                "race_code": pred["race_code"],
                "predicted_dem_probability": pred["dem_probability"],
                "winner": "DEM" if y else "REP",
                "winner_probability": round(p, 6),
                "surprise": round(1 - p, 6),
            })
    misses.sort(key=lambda r: r["surprise"], reverse=True)
    return {
        "state": "scored",
        "n": len(probs),
        "brier": round(brier_score(probs, outcomes), 8),
        "log_loss": round(log_loss(probs, outcomes), 8),
        "calibration": calibration_bins(probs, outcomes),
        "calibration_intercept": cal["intercept"],
        "calibration_slope": cal["slope"],
        "calibration_fit_state": cal["state"],
        "misses": misses[:25],
    }


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def cycle_blockers(cycle_dir: Path, config: dict, contract: dict) -> list[str]:
    blockers = []
    if contract["blocking"]:
        blockers.append("production_model_contract_drift")
    for name in REQUIRED_FILES:
        if not (cycle_dir / name).is_file():
            blockers.append(f"missing:{name}")
    national = config.get("national_presidential_margins") or {}
    if any(national.get(k) is None for k in ("earliest", "middle", "latest")):
        blockers.append("unverified_national_presidential_margins")
    if not config.get("provenance"):
        blockers.append("provenance_not_admitted")
    return blockers


def load_results(rows: list[dict]) -> dict[str, int]:
    outcomes = {}
    for row in rows:
        code = (row.get("race_code") or "").strip()
        winner = (row.get("winner_party") or "").strip().upper()
        if code and winner in {"DEM", "REP"}:
            if code in outcomes:
                raise ValueError(f"Duplicate result for {code}")
            outcomes[code] = 1 if winner == "DEM" else 0
    return outcomes


def run_cycle(cycle_dir: Path, config: dict, contract: dict) -> dict:
    year = int(config["cycle"])
    election = parse_day(config.get("election_date"))
    base = {
        "cycle": year,
        "election_date": config.get("election_date"),
        "corpus_state": config.get("corpus_state", "unknown"),
        "provenance": config.get("provenance", []),
        "checkpoints": [],
    }
    if not election:
        return {**base, "state": "unavailable", "blocking_reasons": ["invalid_election_date"]}
    blockers = cycle_blockers(cycle_dir, config, contract)
    if blockers:
        return {**base, "state": "unavailable", "blocking_reasons": blockers}

    races = read_csv(cycle_dir / "races.csv")
    polls = read_csv(cycle_dir / "polls.csv")
    # Results are deliberately loaded only after all replay inputs. They are
    # never accepted by race_probability or any upstream modelling function.
    results_rows = read_csv(cycle_dir / "results.csv")
    national = config["national_presidential_margins"]
    predictions_by_code: dict[str, list[dict]] = defaultdict(list)

    replay_checkpoints = []
    for days in CHECKPOINT_DAYS:
        cutoff = election - timedelta(days=days)
        active = select_race_versions(races, cutoff)
        gcb, gcb_count, gcb_latest = aggregate_generic(polls, cutoff)
        checkpoint = {
            "days_to_election": days,
            "cutoff": cutoff.isoformat(),
            "race_count": len(active),
            "generic_ballot_poll_count": gcb_count,
            "generic_ballot_latest": gcb_latest,
            "generic_ballot_margin_d_minus_r": round(gcb, 4) if gcb is not None else None,
        }
        if not active:
            checkpoint.update({"state": "unscored", "reason": "no_race_roster_known_by_cutoff"})
            replay_checkpoints.append(checkpoint)
            continue
        if gcb is None:
            checkpoint.update({"state": "unscored", "reason": "no_eligible_generic_ballot_input"})
            replay_checkpoints.append(checkpoint)
            continue
        predictions = [race_probability(r, polls, gcb, cutoff, national) for r in active]
        for p in predictions:
            predictions_by_code[p["race_code"]].append(p)
        checkpoint["predictions"] = predictions
        checkpoint["state"] = "replayed_unscored"
        replay_checkpoints.append(checkpoint)

    outcomes = load_results(results_rows)
    any_unscored = False
    for checkpoint in replay_checkpoints:
        predictions = checkpoint.get("predictions") or []
        if not predictions:
            any_unscored = True
            continue
        score = score_checkpoint(predictions, outcomes)
        checkpoint["score"] = score
        checkpoint["state"] = score["state"]
        if score["state"] != "scored":
            any_unscored = True
        # Predictions remain inspectable, but outcomes live only inside score.
    evolution = []
    for code, rows in sorted(predictions_by_code.items()):
        evolution.append({"race_code": code, "points": [{"cutoff": r["cutoff"], "dem_probability": r["dem_probability"]} for r in rows]})
    return {
        **base,
        "state": "partial" if any_unscored else "scored",
        "blocking_reasons": [],
        "checkpoints": replay_checkpoints,
        "forecast_evolution": evolution,
    }


def build() -> dict:
    contract = production_contract_state()
    cycles = []
    for year in (2018, 2022):
        cycle_dir = HISTORICAL / str(year)
        config_path = cycle_dir / "cycle.json"
        if not config_path.is_file():
            cycles.append({
                "cycle": year,
                "state": "unavailable",
                "blocking_reasons": ["missing:cycle.json"],
                "checkpoints": [],
            })
            continue
        config = json.loads(config_path.read_text())
        cycles.append(run_cycle(cycle_dir, config, contract))
    scored = sum(c.get("state") == "scored" for c in cycles)
    payload = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "product": "MIDTERM SIGNALS MODEL LAB",
        "evaluation_only": True,
        "retuning_allowed": False,
        "model_contract": {**MODEL_CONTRACT, **contract},
        "checkpoints_days_to_election": list(CHECKPOINT_DAYS),
        "metric_definitions": {
            "brier": "Mean squared error of Democratic win probability against binary outcome; lower is better.",
            "log_loss": "Mean negative log likelihood; strongly penalises confident errors; lower is better.",
            "calibration": "Within probability bins, compares mean forecast probability with observed Democratic win rate.",
            "calibration_slope_intercept": "Logistic recalibration diagnostic; ideal intercept 0 and slope 1. Diagnostic only, never fed back into the model.",
        },
        "leakage_guards": [
            "Polls are eligible only when publication_date (or end_date if publication_date is absent) is on or before the checkpoint.",
            "Candidate/race roster rows are versioned by known_date; the latest row known by the checkpoint is selected.",
            "Structural presidential baselines must pre-date the cycle and be admitted with provenance.",
            "Election outcomes are loaded only after replay predictions are produced and are passed only to scoring functions.",
            "A checkpoint is not scored if any replayed race lacks an outcome.",
            "Missing generic-ballot input is missing, never zero.",
            "Replay output cannot mutate the live forecast or model contract.",
        ],
        "cycles": cycles,
        "summary": {
            "state": "scored" if scored == len(cycles) else "unscored" if scored == 0 else "partial",
            "scored_cycles": scored,
            "requested_cycles": len(cycles),
            "message": "Historical performance remains unpublished until each cycle passes the leakage-free corpus gates." if scored < len(cycles) else "All admitted historical cycles passed replay and scoring gates.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return payload


if __name__ == "__main__":
    payload = build()
    print(f"MODEL LAB: {payload['summary']['state']} · contract {payload['model_contract']['state']} · {payload['summary']['scored_cycles']}/{payload['summary']['requested_cycles']} cycles scored")
