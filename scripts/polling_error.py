#!/usr/bin/env python3
"""Add raw race-poll margin error diagnostics to Model Lab.

The frozen replay and pre-outcome scoreability sample already exist before this
sidecar runs. This module reconstructs the exact race-poll aggregate seen by the
frozen model at each checkpoint, then opens separately admitted certified D/R
result margins solely for evaluation. It never changes a forecast probability.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import model_lab as core

ROOT = Path(__file__).resolve().parents[1]
MODEL_LAB = ROOT / "public" / "data" / "model-lab.json"
HISTORICAL = ROOT / "historical"
PROVENANCE = HISTORICAL / "result-margin-provenance.json"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_result_margins(year: int) -> dict[str, float]:
    path = HISTORICAL / str(year) / "result-margins.csv"
    if not path.is_file():
        return {}
    out = {}
    for row in read_csv(path):
        code = (row.get("race_code") or "").strip()
        try:
            margin = float(row.get("margin_d_minus_r") or "")
        except ValueError:
            continue
        if code:
            if code in out:
                raise ValueError(f"Duplicate certified result margin {year} {code}")
            out[code] = margin
    return out


def two_major_party_prediction(pred: dict) -> bool:
    dem = (pred.get("dem_candidate") or "").strip()
    rep = (pred.get("rep_candidate") or "").strip()
    return bool(
        dem and rep
        and not dem.lower().startswith("(no democrat)")
        and not rep.lower().startswith("(no republican)")
    )


def error_metrics(rows: list[dict], key: str) -> dict:
    if not rows:
        return {"state": "unavailable", "n": 0}
    errors = [float(r[key]) - float(r["result_margin_d_minus_r"]) for r in rows]
    abs_errors = [abs(e) for e in errors]
    squared = [e * e for e in errors]
    calls = []
    for row in rows:
        result = float(row["result_margin_d_minus_r"])
        estimate = float(row[key])
        if result == 0 or estimate == 0:
            continue
        calls.append((result > 0) == (estimate > 0))
    return {
        "state": "scored",
        "n": len(rows),
        "mean_error_d_minus_r_pp": round(sum(errors) / len(errors), 6),
        "mae_pp": round(sum(abs_errors) / len(abs_errors), 6),
        "rmse_pp": round(math.sqrt(sum(squared) / len(squared)), 6),
        "winner_call_accuracy": round(sum(calls) / len(calls), 6) if calls else None,
        "winner_call_n": len(calls),
        "too_democratic_n": sum(e > 0 for e in errors),
        "too_republican_n": sum(e < 0 for e in errors),
        "exact_n": sum(e == 0 for e in errors),
    }


def comparison_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"state": "unavailable", "n": 0}
    poll_abs = [abs(r["raw_poll_margin_d_minus_r"] - r["result_margin_d_minus_r"]) for r in rows]
    prior_abs = [abs(r["prior_margin_d_minus_r"] - r["result_margin_d_minus_r"]) for r in rows]
    full_abs = [abs(r["full_model_margin_d_minus_r"] - r["result_margin_d_minus_r"]) for r in rows]
    delta_full_poll = [f - p for f, p in zip(full_abs, poll_abs)]
    delta_full_prior = [f - p for f, p in zip(full_abs, prior_abs)]
    return {
        "state": "scored",
        "n": len(rows),
        "mae_delta_full_minus_raw_poll_pp": round(sum(delta_full_poll) / len(rows), 6),
        "mae_delta_full_minus_prior_pp": round(sum(delta_full_prior) / len(rows), 6),
        "full_closer_than_raw_poll_n": sum(d < 0 for d in delta_full_poll),
        "raw_poll_closer_than_full_n": sum(d > 0 for d in delta_full_poll),
        "equal_full_vs_poll_n": sum(d == 0 for d in delta_full_poll),
        "full_closer_than_prior_n": sum(d < 0 for d in delta_full_prior),
        "prior_closer_than_full_n": sum(d > 0 for d in delta_full_prior),
        "equal_full_vs_prior_n": sum(d == 0 for d in delta_full_prior),
        "interpretation": "Negative MAE deltas mean the frozen full model was closer to the certified two-party result margin than the comparison signal on the same races.",
    }


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"state": "unavailable", "n": 0}
    return {
        "state": "scored",
        "n": len(rows),
        "raw_race_poll_aggregate": error_metrics(rows, "raw_poll_margin_d_minus_r"),
        "structural_plus_generic_prior": error_metrics(rows, "prior_margin_d_minus_r"),
        "published_full_model_margin": error_metrics(rows, "full_model_margin_d_minus_r"),
        "model_comparison": comparison_metrics(rows),
    }


def forensic_rows(rows: list[dict]) -> dict:
    cooked = []
    for row in rows:
        poll_error = row["raw_poll_margin_d_minus_r"] - row["result_margin_d_minus_r"]
        full_error = row["full_model_margin_d_minus_r"] - row["result_margin_d_minus_r"]
        prior_error = row["prior_margin_d_minus_r"] - row["result_margin_d_minus_r"]
        cooked.append({
            **row,
            "raw_poll_error_d_minus_r_pp": round(poll_error, 6),
            "full_model_error_d_minus_r_pp": round(full_error, 6),
            "prior_error_d_minus_r_pp": round(prior_error, 6),
            "full_abs_error_minus_poll_abs_error_pp": round(abs(full_error) - abs(poll_error), 6),
        })
    return {
        "largest_raw_poll_errors": sorted(cooked, key=lambda r: abs(r["raw_poll_error_d_minus_r_pp"]), reverse=True)[:15],
        "largest_model_rescues_vs_poll": sorted(cooked, key=lambda r: r["full_abs_error_minus_poll_abs_error_pp"])[:15],
        "largest_model_worsenings_vs_poll": sorted(cooked, key=lambda r: r["full_abs_error_minus_poll_abs_error_pp"], reverse=True)[:15],
    }


def checkpoint_polling_error(
    checkpoint: dict,
    races: list[dict],
    polls: list[dict],
    result_margins: dict[str, float],
) -> dict:
    cutoff = core.parse_day(checkpoint.get("cutoff"))
    if not cutoff:
        return {"state": "unavailable", "reason": "invalid_checkpoint_cutoff", "n": 0}
    active = {r["race_code"]: r for r in core.select_race_versions(races, cutoff)}
    rows = []
    missing_result_margin = []
    for pred in checkpoint.get("predictions") or []:
        if int(pred.get("poll_count") or 0) <= 0 or not two_major_party_prediction(pred):
            continue
        code = pred.get("race_code")
        race = active.get(code)
        if not code or race is None:
            raise ValueError(f"Polling-error race roster missing at checkpoint: {code}")
        raw_poll, blend, count, latest = core.race_poll_average(polls, race, cutoff)
        if raw_poll is None or count <= 0:
            raise ValueError(f"Frozen prediction says polled but exact aggregate is unavailable: {code}")
        if count != int(pred.get("poll_count") or 0):
            raise ValueError(f"Poll-count reconstruction drift {code}: {count} != {pred.get('poll_count')}")
        if abs(float(blend) - float(pred.get("poll_weight") or 0.0)) > 0.00002:
            raise ValueError(f"Poll-weight reconstruction drift {code}: {blend} != {pred.get('poll_weight')}")
        if latest != pred.get("latest_race_poll"):
            raise ValueError(f"Latest-poll reconstruction drift {code}: {latest} != {pred.get('latest_race_poll')}")
        if code not in result_margins:
            missing_result_margin.append(code)
            continue
        rows.append({
            "race_code": code,
            "race_type": pred.get("race_type"),
            "raw_poll_margin_d_minus_r": float(raw_poll),
            "prior_margin_d_minus_r": float(pred["prior_margin"]),
            "full_model_margin_d_minus_r": float(pred["forecast_margin_d_minus_r"]),
            "result_margin_d_minus_r": float(result_margins[code]),
            "poll_count": count,
            "poll_weight": round(float(blend), 6),
            "latest_race_poll": latest,
        })
    if not rows:
        return {
            "state": "unavailable",
            "reason": "no_polled_two_major_party_races_with_certified_margin",
            "n": 0,
            "missing_result_margin_races": sorted(set(missing_result_margin)),
        }
    house = [r for r in rows if (r.get("race_type") or "").lower() == "house"]
    senate = [r for r in rows if (r.get("race_type") or "").lower() == "senate"]
    return {
        "state": "scored",
        "n": len(rows),
        "scope": "scoreable polled two-major-party races with admitted certified D/R result margin",
        "outcome_margin_used_only_for_scoring": True,
        "missing_result_margin_races": sorted(set(missing_result_margin)),
        "all_polled": summarize(rows),
        "house_only": summarize(house),
        "senate_only": summarize(senate),
        "forensics": forensic_rows(rows),
        "interpretation": "Raw poll error compares the exact frozen as-of race-poll aggregate with the certified D-R two-party result margin. Positive mean error means polls were too Democratic on average; negative means too Republican. This evaluates the admitted polling stream and the frozen blend separately, but does not establish why the polls erred.",
    }


def cross_cycle(payload: dict) -> dict:
    rows = []
    for cycle in payload.get("cycles", []):
        if cycle.get("state") != "scored":
            continue
        cp = next((c for c in cycle.get("checkpoints", []) if int(c.get("days_to_election") or -1) == 1), None)
        diag = (cp or {}).get("score", {}).get("polling_error")
        house = (diag or {}).get("house_only")
        if not house or house.get("state") != "scored":
            continue
        rows.append({
            "cycle": cycle["cycle"],
            "n": house["n"],
            "raw_poll_mae_pp": house["raw_race_poll_aggregate"]["mae_pp"],
            "raw_poll_bias_d_minus_r_pp": house["raw_race_poll_aggregate"]["mean_error_d_minus_r_pp"],
            "prior_mae_pp": house["structural_plus_generic_prior"]["mae_pp"],
            "full_model_mae_pp": house["published_full_model_margin"]["mae_pp"],
            "full_minus_poll_mae_pp": house["model_comparison"]["mae_delta_full_minus_raw_poll_pp"],
            "poll_call_accuracy": house["raw_race_poll_aggregate"]["winner_call_accuracy"],
            "full_call_accuracy": house["published_full_model_margin"]["winner_call_accuracy"],
        })
    return {
        "state": "scored" if len(rows) >= 2 else "partial",
        "checkpoint_days_to_election": 1,
        "scope": "House-only scoreable polled two-major-party races with certified D/R result margin",
        "cycles": rows,
        "interpretation": "House-only final-checkpoint comparison holds chamber scope constant across cycles. It is descriptive and does not identify pollster, mode, turnout or sampling mechanisms.",
    }


def augment(payload: dict) -> dict:
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8")) if PROVENANCE.is_file() else None
    if not provenance or provenance.get("evaluation_only") is not True or provenance.get("model_effect") != "NONE":
        raise RuntimeError("Certified result-margin provenance contract missing or invalid")

    for cycle in payload.get("cycles", []):
        if cycle.get("state") != "scored":
            continue
        year = int(cycle["cycle"])
        cycle_dir = HISTORICAL / str(year)
        races = read_csv(cycle_dir / "races.csv")
        polls = read_csv(cycle_dir / "polls.csv")
        result_margins = load_result_margins(year)
        if not result_margins:
            raise RuntimeError(f"No admitted result margins for {year}")
        for checkpoint in cycle.get("checkpoints", []):
            if checkpoint.get("state") != "scored":
                continue
            checkpoint.setdefault("score", {})["polling_error"] = checkpoint_polling_error(
                checkpoint, races, polls, result_margins
            )

    payload.setdefault("diagnostic_contract", {})["polling_error_decomposition"] = {
        "scope": "scoreable races with eligible race-level polls and separately admitted certified D/R two-party result margins",
        "raw_poll_signal": "exact frozen as-of race_poll_average using the production window, candidate matching, quality/sample/sponsor weights and half-life",
        "result_margin_source": "historical/result-margin-provenance.json",
        "outcomes_visible_only_after_forecasts": True,
        "model_effect": "NONE",
        "causal_boundary": "Observed poll error does not by itself identify pollster, sampling, turnout, mode or electorate causes.",
    }
    payload.setdefault("metric_definitions", {})["poll_margin_error"] = (
        "Estimated Democratic-minus-Republican two-party margin minus certified D-R two-party result margin. Positive values are too Democratic; negative values are too Republican."
    )
    payload.setdefault("metric_definitions", {})["poll_margin_mae"] = (
        "Mean absolute error in percentage points between the exact frozen race-poll aggregate and certified D-R two-party result margin."
    )
    payload.setdefault("leakage_guards", []).append(
        "Certified result margins are admitted in a separate evaluation-only sidecar and are opened only after checkpoint predictions and the exact as-of poll aggregates are frozen; they cannot enter forecast generation."
    )
    payload["polling_error_cross_cycle"] = cross_cycle(payload)
    for hypothesis in payload.get("cross_cycle", {}).get("hypotheses", []):
        if hypothesis.get("id") == "systematic_polling_error":
            hypothesis["state"] = "diagnostic_exposed"
            hypothesis["evidence"] = "checkpoint polling_error raw poll margin versus certified result margin"
    return payload


def main() -> None:
    payload = json.loads(MODEL_LAB.read_text(encoding="utf-8"))
    payload = augment(payload)
    MODEL_LAB.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(MODEL_LAB),
        "diagnostic": "polling_error_decomposition",
        "cross_cycle_state": payload.get("polling_error_cross_cycle", {}).get("state"),
    }))


if __name__ == "__main__":
    main()
