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
COMPETITIVE_BANDS = (
    ("45-55", 0.45, 0.55),
    ("40-60", 0.40, 0.60),
    ("30-70", 0.30, 0.70),
    ("20-80", 0.20, 0.80),
)
MOVEMENT_THRESHOLD = 0.10
CONFIDENT_MISS_THRESHOLD = 0.80

MODEL_CONTRACT = {
    "id": "baseline-v1.0-frozen",
    "origin": "v0.2 prospective coefficients, carried unchanged into PROD v1.0",
    "structural_weights": [0.05, 0.20, 0.75],
    "incumbency_margin": {"house": 1.0, "senate": 1.15},
    "generic_ballot": {"window_days": 35, "half_life_days": 11.0},
    "race_polls": {"window_days": 55, "half_life_days": 13.0, "blend_scale": 0.27, "blend_min": 0.20, "blend_max": 0.86, "freshness_days": 28.0},
    "sigma": {"house": 6.3, "senate": 7.2, "poll_reduction": 0.42, "floor": 3.1},
    "probability_clamp": [0.001, 0.999],
    "rule": "No replay result may alter this contract or the live forecast.",
}

PRODUCTION_MARKERS = (
    'return 0.05 * m16 + 0.20 * m20 + 0.75 * m24',
    'inc_adj = 1.0 if inc == "DEM" else -1.0 if inc == "REP" else 0.0',
    'inc_adj *= 1.15',
    '(asof - d).days <= 35',
    'poll_weight(r, latest, 11.0)',
    '(asof - d).days > 55',
    'poll_weight(r, latest, 13.0)',
    'blend = clamp(0.27 * math.sqrt(len(chosen)), 0.20, 0.86)',
    'base_sigma = 6.3 if race.get("race_type") == "house" else 7.2',
    'base_sigma * (1 - 0.42 * pweight)',
    'clamp(normal_cdf(margin / sigma), 0.001, 0.999)',
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
    return sum(w * (m - n) for w, m, n in zip(MODEL_CONTRACT["structural_weights"], margins, nationals))


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
        if idx:
            mean_p = sum(probabilities[j] for j in idx) / len(idx)
            actual = sum(outcomes[j] for j in idx) / len(idx)
            bins.append({
                "lower": round(lo, 3),
                "upper": round(hi, 3),
                "count": len(idx),
                "mean_probability": round(mean_p, 6),
                "observed_rate": round(actual, 6),
                "calibration_residual": round(actual - mean_p, 6),
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


def metric_summary(predictions: list[dict], results: dict[str, int]) -> dict:
    if not predictions:
        return {"state": "unavailable", "n": 0}
    codes = [p["race_code"] for p in predictions]
    missing = sorted(set(codes) - set(results))
    if missing:
        return {"state": "unscored", "n": len(codes), "reason": "outcomes_incomplete", "missing_outcomes": missing}
    probs = [float(p["dem_probability"]) for p in predictions]
    outcomes = [int(results[c]) for c in codes]
    cal = calibration_logistic(probs, outcomes)
    mean_p = sum(probs) / len(probs)
    actual = sum(outcomes) / len(outcomes)
    accuracy = sum((p >= 0.5) == bool(y) for p, y in zip(probs, outcomes)) / len(probs)
    bins = calibration_bins(probs, outcomes)
    ece = sum(b["count"] * abs(b["calibration_residual"]) for b in bins) / len(probs)
    return {
        "state": "scored",
        "n": len(probs),
        "brier": round(brier_score(probs, outcomes), 8),
        "log_loss": round(log_loss(probs, outcomes), 8),
        "accuracy": round(accuracy, 6),
        "mean_dem_probability": round(mean_p, 6),
        "actual_dem_win_rate": round(actual, 6),
        "calibration_error": round(actual - mean_p, 6),
        "mean_absolute_bin_calibration_error": round(ece, 6),
        "calibration": bins,
        "calibration_intercept": cal["intercept"],
        "calibration_slope": cal["slope"],
        "calibration_fit_state": cal["state"],
    }


def competitive_diagnostics(predictions: list[dict], results: dict[str, int]) -> list[dict]:
    out = []
    for label, lo, hi in COMPETITIVE_BANDS:
        selected = [p for p in predictions if lo <= float(p["dem_probability"]) <= hi]
        out.append({"band": label, "lower": lo, "upper": hi, "definition": "nested", **metric_summary(selected, results)})
    safe = [p for p in predictions if float(p["dem_probability"]) < 0.20 or float(p["dem_probability"]) > 0.80]
    out.append({"band": "safe-outside-20-80", "lower": None, "upper": None, "definition": "complement", **metric_summary(safe, results)})
    return out


def polling_partitions(predictions: list[dict], results: dict[str, int]) -> dict:
    polled = [p for p in predictions if int(p.get("poll_count") or 0) > 0]
    unpolled = [p for p in predictions if int(p.get("poll_count") or 0) == 0]
    return {
        "interpretation": "conditional comparison; polling is endogenous to race competitiveness and this partition is not a causal estimate",
        "polled": metric_summary(polled, results),
        "unpolled": metric_summary(unpolled, results),
    }


def chamber_partitions(predictions: list[dict], results: dict[str, int]) -> dict:
    out = {}
    for chamber in ("house", "senate"):
        selected = [p for p in predictions if (p.get("race_type") or "").lower() == chamber]
        if selected:
            out[chamber] = metric_summary(selected, results)
        else:
            out[chamber] = {"state": "unavailable", "n": 0, "reason": "no_admitted_races_at_checkpoint"}
    return out


def score_checkpoint(predictions: list[dict], results: dict[str, int]) -> dict:
    codes = [p["race_code"] for p in predictions]
    if len(codes) != len(set(codes)):
        raise ValueError("Duplicate race prediction in checkpoint")
    base = metric_summary(predictions, results)
    if base["state"] != "scored":
        return base
    misses = []
    for pred in predictions:
        y = int(results[pred["race_code"]])
        winner_p = float(pred["dem_probability"]) if y == 1 else float(pred["rep_probability"])
        picked_correctly = (float(pred["dem_probability"]) >= 0.5) == bool(y)
        if not picked_correctly:
            predicted_winner_p = 1.0 - winner_p
            misses.append({
                "race_code": pred["race_code"],
                "race_type": pred.get("race_type"),
                "predicted_dem_probability": pred["dem_probability"],
                "winner": "DEM" if y else "REP",
                "winner_probability": round(winner_p, 6),
                "predicted_winner_probability": round(predicted_winner_p, 6),
                "surprise": round(1 - winner_p, 6),
                "confident_miss": predicted_winner_p >= CONFIDENT_MISS_THRESHOLD,
            })
    misses.sort(key=lambda r: r["surprise"], reverse=True)
    return {
        **base,
        "competitive_bands": competitive_diagnostics(predictions, results),
        "polling": polling_partitions(predictions, results),
        "chambers": chamber_partitions(predictions, results),
        "misses": misses[:25],
        "confident_miss_threshold": CONFIDENT_MISS_THRESHOLD,
        "confident_miss_count": sum(m["confident_miss"] for m in misses),
    }


def movement_diagnostics(replay_checkpoints: list[dict], results: dict[str, int]) -> dict:
    scored = [cp for cp in replay_checkpoints if cp.get("state") == "scored" and cp.get("predictions")]
    by_day = {int(cp["days_to_election"]): {p["race_code"]: p for p in cp["predictions"]} for cp in scored}
    if any(day not in by_day for day in CHECKPOINT_DAYS):
        return {"state": "unavailable", "reason": "all_fixed_checkpoints_required"}
    common = set.intersection(*(set(by_day[day]) for day in CHECKPOINT_DAYS))
    transitions = []
    race_rows = []
    for earlier, later in zip(CHECKPOINT_DAYS, CHECKPOINT_DAYS[1:]):
        vals = []
        toward = away = strong_toward = strong_away = 0
        for code in sorted(common):
            y = results[code]
            p0 = float(by_day[earlier][code]["dem_probability"])
            p1 = float(by_day[later][code]["dem_probability"])
            directed = (1 if y == 1 else -1) * (p1 - p0)
            vals.append(abs(p1 - p0))
            if directed > 0:
                toward += 1
            elif directed < 0:
                away += 1
            if directed >= MOVEMENT_THRESHOLD:
                strong_toward += 1
            elif directed <= -MOVEMENT_THRESHOLD:
                strong_away += 1
        transitions.append({
            "from_days": earlier,
            "to_days": later,
            "n": len(common),
            "mean_absolute_probability_change": round(sum(vals) / len(vals), 6) if vals else None,
            "toward_eventual_winner": toward,
            "away_from_eventual_winner": away,
            "strong_toward_eventual_winner": strong_toward,
            "strong_away_from_eventual_winner": strong_away,
        })
    for code in sorted(common):
        y = results[code]
        points = []
        for day in CHECKPOINT_DAYS:
            pred = by_day[day][code]
            points.append({
                "days_to_election": day,
                "dem_probability": pred["dem_probability"],
                "poll_count": pred.get("poll_count", 0),
            })
        p60 = float(by_day[60][code]["dem_probability"])
        p1 = float(by_day[1][code]["dem_probability"])
        p7 = float(by_day[7][code]["dem_probability"])
        directed = (1 if y == 1 else -1) * (p1 - p60)
        late_directed = (1 if y == 1 else -1) * (p1 - p7)
        final_pred = by_day[1][code]
        final_winner_p = float(final_pred["dem_probability"]) if y == 1 else float(final_pred["rep_probability"])
        race_rows.append({
            "race_code": code,
            "race_type": final_pred.get("race_type"),
            "winner": "DEM" if y else "REP",
            "points": points,
            "winner_directed_change_60_to_1": round(directed, 6),
            "winner_directed_change_7_to_1": round(late_directed, 6),
            "late_absolute_change": round(abs(p1 - p7), 6),
            "strong_toward_winner": directed >= MOVEMENT_THRESHOLD,
            "strong_away_from_winner": directed <= -MOVEMENT_THRESHOLD,
            "large_late_swing": abs(p1 - p7) >= MOVEMENT_THRESHOLD,
            "final_winner_probability": round(final_winner_p, 6),
            "final_confident_miss": final_winner_p <= 1 - CONFIDENT_MISS_THRESHOLD,
        })
    strongest_toward = sorted(race_rows, key=lambda r: r["winner_directed_change_60_to_1"], reverse=True)[:15]
    strongest_away = sorted(race_rows, key=lambda r: r["winner_directed_change_60_to_1"])[:15]
    late_swings = sorted([r for r in race_rows if r["large_late_swing"]], key=lambda r: r["late_absolute_change"], reverse=True)[:20]
    confident = sorted([r for r in race_rows if r["final_confident_miss"]], key=lambda r: r["final_winner_probability"])[:20]
    return {
        "state": "scored",
        "common_race_count": len(common),
        "movement_threshold": MOVEMENT_THRESHOLD,
        "confident_miss_threshold": CONFIDENT_MISS_THRESHOLD,
        "transitions": transitions,
        "strongest_toward_eventual_winner": strongest_toward,
        "strongest_away_from_eventual_winner": strongest_away,
        "large_late_swings": late_swings,
        "final_confident_misses": confident,
    }


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def cycle_blockers(cycle_dir: Path, config: dict, contract: dict) -> list[str]:
    blockers = []
    if contract["blocking"]:
        blockers.append("production_model_contract_drift")
    if config.get("corpus_state") != "admitted":
        blockers.append("corpus_not_admitted")
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

    # Outcome bytes are not opened until every checkpoint prediction exists.
    outcomes = load_results(read_csv(cycle_dir / "results.csv"))
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

    evolution = [
        {"race_code": code, "points": [{"cutoff": r["cutoff"], "dem_probability": r["dem_probability"]} for r in rows]}
        for code, rows in sorted(predictions_by_code.items())
    ]
    movement = movement_diagnostics(replay_checkpoints, outcomes) if not any_unscored else {"state": "unavailable", "reason": "complete_scored_cycle_required"}
    chamber_scope = {}
    for chamber in ("house", "senate"):
        counts = [
            sum(1 for p in (cp.get("predictions") or []) if (p.get("race_type") or "").lower() == chamber)
            for cp in replay_checkpoints
        ]
        chamber_scope[chamber] = {
            "state": "scored" if counts and min(counts) > 0 and not any_unscored else "unavailable",
            "race_counts_by_checkpoint": counts,
            "reason": None if counts and min(counts) > 0 and not any_unscored else "no_admitted_complete_chamber_replay",
        }
    return {
        **base,
        "state": "partial" if any_unscored else "scored",
        "blocking_reasons": [],
        "checkpoints": replay_checkpoints,
        "forecast_evolution": evolution,
        "movement": movement,
        "chamber_scope": chamber_scope,
    }


def cross_cycle_comparison(cycles: list[dict]) -> dict:
    scored = [c for c in cycles if c.get("state") == "scored"]
    rows = []
    for cycle in scored:
        cps = {int(cp["days_to_election"]): cp for cp in cycle["checkpoints"] if cp.get("score", {}).get("state") == "scored"}
        if not cps:
            continue
        best_day = min(cps, key=lambda d: cps[d]["score"]["brier"])
        final_week_delta = cps[1]["score"]["brier"] - cps[14]["score"]["brier"] if 1 in cps and 14 in cps else None
        rows.append({
            "cycle": cycle["cycle"],
            "best_brier_checkpoint_days": best_day,
            "best_brier": cps[best_day]["score"]["brier"],
            "brier_60d": cps.get(60, {}).get("score", {}).get("brier"),
            "brier_14d": cps.get(14, {}).get("score", {}).get("brier"),
            "brier_1d": cps.get(1, {}).get("score", {}).get("brier"),
            "brier_change_14d_to_1d": round(final_week_delta, 8) if final_week_delta is not None else None,
            "final_week_direction": "improved" if final_week_delta is not None and final_week_delta < 0 else "weakened" if final_week_delta is not None and final_week_delta > 0 else "flat_or_unavailable",
            "polled_races_1d": cps.get(1, {}).get("score", {}).get("polling", {}).get("polled", {}).get("n"),
            "unpolled_races_1d": cps.get(1, {}).get("score", {}).get("polling", {}).get("unpolled", {}).get("n"),
            "confident_misses_1d": cps.get(1, {}).get("score", {}).get("confident_miss_count"),
        })
    return {
        "state": "scored" if len(rows) >= 2 else "partial",
        "cycles": rows,
        "interpretation": "Cross-cycle contrasts are descriptive. Differences in race mix, chamber coverage and polling availability prevent simple causal attribution.",
        "hypotheses": [
            {"id": "late_generic_ballot_movement", "state": "diagnostic_exposed", "evidence": "checkpoint generic_ballot_margin_d_minus_r"},
            {"id": "race_poll_composition", "state": "diagnostic_exposed", "evidence": "checkpoint polling partitions and poll_count"},
            {"id": "pollster_mix", "state": "not_yet_decomposed", "evidence": "requires source-mix diagnostic"},
            {"id": "structural_priors_redistricting", "state": "not_yet_identified", "evidence": "requires structural-only counterfactual comparison"},
            {"id": "systematic_polling_error", "state": "not_yet_identified", "evidence": "requires poll-margin error decomposition"},
            {"id": "safe_seat_weighting", "state": "diagnostic_exposed", "evidence": "fixed competitive bands versus safe complement"},
            {"id": "late_overreaction", "state": "diagnostic_exposed_not_causal", "evidence": "7d-to-1d winner-directed movement and large late swings"},
            {"id": "changing_race_coverage", "state": "diagnostic_exposed", "evidence": "polled/unpolled counts by checkpoint"},
        ],
    }


def build() -> dict:
    contract = production_contract_state()
    cycles = []
    for year in (2018, 2022):
        cycle_dir = HISTORICAL / str(year)
        config_path = cycle_dir / "cycle.json"
        if not config_path.is_file():
            cycles.append({"cycle": year, "state": "unavailable", "blocking_reasons": ["missing:cycle.json"], "checkpoints": []})
            continue
        cycles.append(run_cycle(cycle_dir, json.loads(config_path.read_text()), contract))
    scored = sum(c.get("state") == "scored" for c in cycles)
    return {
        "schema_version": "1.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "product": "MIDTERM SIGNALS MODEL LAB",
        "evaluation_only": True,
        "retuning_allowed": False,
        "model_contract": {**MODEL_CONTRACT, **contract},
        "checkpoints_days_to_election": list(CHECKPOINT_DAYS),
        "diagnostic_contract": {
            "competitive_bands": [{"label": label, "lower": lo, "upper": hi, "nested": True} for label, lo, hi in COMPETITIVE_BANDS],
            "safe_definition": "p_dem < 0.20 or p_dem > 0.80",
            "calibration_bin_width": 0.10,
            "movement_threshold": MOVEMENT_THRESHOLD,
            "confident_miss_threshold": CONFIDENT_MISS_THRESHOLD,
            "rule": "Thresholds are fixed before reviewing diagnostic results and are not model coefficients.",
        },
        "metric_definitions": {
            "brier": "Mean squared error of Democratic win probability against binary outcome; lower is better.",
            "log_loss": "Mean negative log likelihood; strongly penalises confident errors; lower is better.",
            "accuracy": "Share of races where the side at or above 50% won; secondary to proper scoring rules.",
            "calibration": "Within fixed 10-point probability bins, compares mean forecast probability with observed Democratic win rate.",
            "calibration_residual": "Observed Democratic win rate minus mean forecast probability. Positive means Democratic wins were more frequent than forecast.",
            "mean_absolute_bin_calibration_error": "Count-weighted mean absolute calibration residual across occupied fixed bins.",
            "calibration_slope_intercept": "Logistic recalibration diagnostic; ideal intercept 0 and slope 1. Diagnostic only, never fed back into the model.",
            "polling_partitions": "Conditional performance among races with versus without eligible race-level polls at a checkpoint; not a causal estimate of polling value.",
            "winner_directed_movement": "Probability change signed so positive movement is toward the eventual winner. Outcomes are used only after predictions are frozen.",
        },
        "leakage_guards": [
            "Corpus state must be explicitly admitted before replay or scoring can run.",
            "Polls are eligible only when publication_date (or end_date if publication_date is absent) is on or before the checkpoint.",
            "Candidate/race roster rows are versioned by known_date; the latest row known by the checkpoint is selected.",
            "Structural presidential baselines must pre-date the cycle and be admitted with provenance.",
            "Election outcome bytes are not opened until every checkpoint prediction has been produced; outcomes are then passed only to scoring functions.",
            "A checkpoint is not scored if any replayed race lacks an outcome.",
            "Missing generic-ballot input is missing, never zero.",
            "Replay output cannot mutate the live forecast or model contract.",
            "Competitive, polling and chamber diagnostics reuse the frozen checkpoint predictions; they do not create alternative forecasts.",
        ],
        "cycles": cycles,
        "cross_cycle": cross_cycle_comparison(cycles),
        "summary": {
            "state": "scored" if scored == len(cycles) else "unscored" if scored == 0 else "partial",
            "scored_cycles": scored,
            "requested_cycles": len(cycles),
            "message": "Historical performance remains unpublished until each cycle passes the leakage-free corpus gates." if scored < len(cycles) else "All admitted historical cycles passed replay and scoring gates.",
        },
    }


def main() -> None:
    payload = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "state": payload["summary"]["state"], "contract": payload["model_contract"]["state"]}))


if __name__ == "__main__":
    main()
