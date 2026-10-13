#!/usr/bin/env python3
"""Add pre-outcome structural-baseline stability diagnostics to Model Lab.

This sidecar runs only after the frozen historical replay and structural-stage
augmentation exist. It classifies House districts using variation in the three
already-admitted presidential relative leans. Band assignment uses no election
outcome and has no model effect. Outcomes are opened only to score the frozen
structural and published probabilities inside those preassigned bands.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_LAB = ROOT / "public" / "data" / "model-lab.json"
HISTORICAL = ROOT / "historical"
SIGMA_HOUSE = 6.3
PROBABILITY_CLAMP = (0.001, 0.999)
CONFIDENT_MISS_THRESHOLD = 0.80
STABILITY_BANDS = (
    ("stable_0_5", 0.0, 5.0),
    ("moderate_5_10", 5.0, 10.0),
    ("high_10_15", 10.0, 15.0),
    ("very_high_gt_15", 15.0, None),
)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def margin_probability(margin: float) -> float:
    return clamp(normal_cdf(float(margin) / SIGMA_HOUSE), *PROBABILITY_CLAMP)


def number(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def two_major_party_contest(pred: dict) -> bool:
    dem = (pred.get("dem_candidate") or "").strip()
    rep = (pred.get("rep_candidate") or "").strip()
    return bool(
        dem
        and rep
        and not dem.lower().startswith("(no democrat)")
        and not rep.lower().startswith("(no republican)")
    )


def stability_band(range_pp: float) -> str:
    x = float(range_pp)
    if x <= 5.0:
        return "stable_0_5"
    if x <= 10.0:
        return "moderate_5_10"
    if x <= 15.0:
        return "high_10_15"
    return "very_high_gt_15"


def structural_profile(row: dict, national: dict) -> dict:
    """Compute pre-outcome relative-lean stability from admitted inputs only."""
    margins = [number(row.get(k)) for k in ("margin_earliest", "margin_middle", "margin_latest")]
    nationals = [number(national.get(k)) for k in ("earliest", "middle", "latest")]
    if any(v is None for v in margins + nationals):
        raise ValueError(f"Missing structural stability input for {row.get('race_code')}")
    leans = [m - n for m, n in zip(margins, nationals)]
    spread = max(leans) - min(leans)
    trend = leans[-1] - leans[0]
    return {
        "relative_leans_d_minus_r": [round(x, 6) for x in leans],
        "range_pp": round(spread, 6),
        "trend_earliest_to_latest_pp": round(trend, 6),
        "band": stability_band(spread),
    }


def load_structural_rows(year: int) -> dict[str, dict]:
    path = HISTORICAL / str(year) / "races.csv"
    out: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if (row.get("race_type") or "").strip().lower() != "house":
                continue
            code = (row.get("race_code") or "").strip()
            if not code:
                continue
            signature = tuple(number(row.get(k)) for k in ("margin_earliest", "margin_middle", "margin_latest"))
            if any(v is None for v in signature):
                continue
            if code in out:
                previous = tuple(number(out[code].get(k)) for k in ("margin_earliest", "margin_middle", "margin_latest"))
                if any(abs(float(a) - float(b)) > 1e-9 for a, b in zip(previous, signature)):
                    raise ValueError(f"Structural baseline changed across roster versions for {year} {code}")
                continue
            out[code] = row
    return out


def load_cycle(year: int) -> dict:
    return json.loads((HISTORICAL / str(year) / "cycle.json").read_text(encoding="utf-8"))


def load_outcomes(year: int) -> dict[str, int]:
    out = {}
    with (HISTORICAL / str(year) / "results.csv").open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("race_code") or "").strip()
            party = (row.get("winner_party") or "").strip().upper()
            if code and party in {"DEM", "REP"}:
                if code in out:
                    raise ValueError(f"Duplicate result for {year} {code}")
                out[code] = 1 if party == "DEM" else 0
    return out


def brier(probs: list[float], outcomes: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / len(probs)


def log_loss(probs: list[float], outcomes: list[int]) -> float:
    total = 0.0
    for p, y in zip(probs, outcomes):
        q = clamp(float(p), 1e-15, 1 - 1e-15)
        total -= y * math.log(q) + (1 - y) * math.log(1 - q)
    return total / len(probs)


def score(probs: list[float], outcomes: list[int]) -> dict:
    return {
        "brier": round(brier(probs, outcomes), 8),
        "log_loss": round(log_loss(probs, outcomes), 8),
        "accuracy": round(sum((p >= 0.5) == bool(y) for p, y in zip(probs, outcomes)) / len(probs), 6),
    }


def summarize_band(rows: list[dict]) -> dict:
    if not rows:
        return {"state": "unavailable", "n": 0}
    ys = [r["outcome"] for r in rows]
    structural = [r["structural_probability"] for r in rows]
    full = [r["full_probability"] for r in rows]
    sm = score(structural, ys)
    fm = score(full, ys)
    return {
        "state": "scored",
        "n": len(rows),
        "mean_range_pp": round(sum(r["range_pp"] for r in rows) / len(rows), 6),
        "mean_absolute_trend_pp": round(sum(abs(r["trend_pp"]) for r in rows) / len(rows), 6),
        "structural_plus_incumbency": sm,
        "published_full_forecast": fm,
        "brier_delta_full_minus_structural": round(fm["brier"] - sm["brier"], 8),
        "structural_confident_misses": sum(r["winner_probability_structural"] <= 1 - CONFIDENT_MISS_THRESHOLD for r in rows),
        "full_confident_misses": sum(r["winner_probability_full"] <= 1 - CONFIDENT_MISS_THRESHOLD for r in rows),
    }


def checkpoint_stability(checkpoint: dict, outcomes: dict[str, int], structural_rows: dict[str, dict], national: dict) -> dict:
    gcb = number(checkpoint.get("generic_ballot_margin_d_minus_r"))
    if gcb is None:
        return {"state": "unavailable", "reason": "generic_ballot_margin_unavailable", "n": 0}

    rows = []
    for pred in checkpoint.get("predictions") or []:
        if (pred.get("race_type") or "").lower() != "house" or not two_major_party_contest(pred):
            continue
        code = pred.get("race_code")
        if not code or code not in outcomes or code not in structural_rows:
            continue
        profile = structural_profile(structural_rows[code], national)
        structural_margin = float(pred["prior_margin"]) - gcb
        structural_p = margin_probability(structural_margin)
        full_p = float(pred["dem_probability"])
        y = outcomes[code]
        winner_structural = structural_p if y else 1 - structural_p
        winner_full = full_p if y else 1 - full_p
        rows.append({
            "race_code": code,
            "outcome": y,
            "winner": "DEM" if y else "REP",
            "band": profile["band"],
            "range_pp": float(profile["range_pp"]),
            "trend_pp": float(profile["trend_earliest_to_latest_pp"]),
            "relative_leans_d_minus_r": profile["relative_leans_d_minus_r"],
            "structural_probability": structural_p,
            "full_probability": full_p,
            "winner_probability_structural": winner_structural,
            "winner_probability_full": winner_full,
            "poll_count": int(pred.get("poll_count") or 0),
        })

    if not rows:
        return {"state": "unavailable", "reason": "no_eligible_house_two_party_contests", "n": 0}

    bands = []
    for label, lower, upper in STABILITY_BANDS:
        subset = [r for r in rows if r["band"] == label]
        bands.append({
            "band": label,
            "lower_exclusive_pp": None if lower == 0 else lower,
            "upper_inclusive_pp": upper,
            **summarize_band(subset),
        })

    high = [r for r in rows if r["range_pp"] > 10.0]
    top = sorted(rows, key=lambda r: (-r["range_pp"], r["race_code"]))[:15]
    top_rows = [
        {
            "race_code": r["race_code"],
            "winner": r["winner"],
            "band": r["band"],
            "range_pp": round(r["range_pp"], 6),
            "trend_earliest_to_latest_pp": round(r["trend_pp"], 6),
            "relative_leans_d_minus_r": r["relative_leans_d_minus_r"],
            "winner_probability_structural": round(r["winner_probability_structural"], 6),
            "winner_probability_full": round(r["winner_probability_full"], 6),
            "poll_count": r["poll_count"],
        }
        for r in top
    ]
    return {
        "state": "scored",
        "n": len(rows),
        "scope": "house_two_major_party_contests",
        "band_assignment_uses_outcomes": False,
        "fixed_high_instability_threshold_pp": 10.0,
        "high_instability_n": len(high),
        "high_instability_share": round(len(high) / len(rows), 6),
        "bands": bands,
        "top_unstable": top_rows,
        "interpretation": "The stability band is assigned from pre-election variation in the three admitted presidential relative leans on the cycle's own district geography. Outcomes only score frozen probabilities after assignment. High instability can reflect realignment or baseline non-stationarity; it does not by itself identify redistricting as the cause.",
    }


def augment(payload: dict) -> dict:
    for cycle in payload.get("cycles", []):
        if cycle.get("state") != "scored":
            continue
        year = int(cycle["cycle"])
        config = load_cycle(year)
        national = config.get("national_presidential_margins") or {}
        structural_rows = load_structural_rows(year)
        outcomes = load_outcomes(year)
        for cp in cycle.get("checkpoints", []):
            if cp.get("state") != "scored":
                continue
            cp.setdefault("score", {})["baseline_stability"] = checkpoint_stability(cp, outcomes, structural_rows, national)

    payload.setdefault("diagnostic_contract", {})["baseline_stability"] = {
        "scope": "House races with both Democratic and Republican candidates in the admitted fixed sample",
        "inputs": "three already-admitted presidential district margins minus the cycle's frozen national presidential margins",
        "fixed_range_bands_pp": ["0-5", ">5-10", ">10-15", ">15"],
        "high_instability_threshold_pp": 10.0,
        "band_assignment_uses_outcomes": False,
        "model_effect": "NONE",
        "causal_boundary": "Baseline instability may indicate non-stationarity or realignment. It is not a redistricting indicator and must not be interpreted as one without separately admitted boundary-change evidence.",
    }
    payload.setdefault("metric_definitions", {})["baseline_stability_range"] = (
        "Range, in percentage points, of the three pre-election presidential relative leans after subtracting each election's frozen national Democratic-minus-Republican margin. Smaller means the structural history was more internally stable."
    )
    payload.setdefault("leakage_guards", []).append(
        "Baseline-stability bands are assigned from admitted presidential structural inputs before certified outcomes are consulted; outcomes are used only to score already-frozen structural and published probabilities within those bands."
    )
    return payload


def main() -> None:
    payload = json.loads(MODEL_LAB.read_text(encoding="utf-8"))
    MODEL_LAB.write_text(json.dumps(augment(payload), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(MODEL_LAB),
        "cycles": [c.get("cycle") for c in payload.get("cycles", []) if c.get("state") == "scored"],
        "diagnostic": "baseline_stability",
    }))


if __name__ == "__main__":
    main()
