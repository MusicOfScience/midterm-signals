#!/usr/bin/env python3
"""Audit whether polling sparsity interacts with pre-poll race difficulty/geography.

Evaluation only. Sparsity, difficulty and geography are assigned from information
available before outcomes are joined. Certified result margins are used only for
scoring after the interaction cells are frozen.
"""
from __future__ import annotations

import json
from pathlib import Path

import model_lab as core
import polling_error as pe
import source_mix as sm

ROOT = Path(__file__).resolve().parents[1]
MODEL_LAB = ROOT / "public" / "data" / "model-lab.json"
HISTORICAL = ROOT / "historical"

PRIOR_DIFFICULTY_BANDS = (
    ("within_5pp", 0.0, 5.0),
    ("five_to_10pp", 5.0, 10.0),
    ("ten_to_20pp", 10.0, 20.0),
    ("over_20pp", 20.0, float("inf")),
)
COMPETITIVE_PRIOR_THRESHOLD_PP = 10.0

REGION_STATES = {
    "Northeast": {"CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"},
    "Midwest": {"IN", "IL", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"},
    "South": {"DE", "FL", "GA", "MD", "NC", "SC", "VA", "DC", "WV", "AL", "KY", "MS", "TN", "AR", "LA", "OK", "TX"},
    "West": {"AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"},
}
REGION_ORDER = ("Northeast", "Midwest", "South", "West")


def difficulty_band(prior_margin: float) -> str:
    value = abs(float(prior_margin))
    for label, lo, hi in PRIOR_DIFFICULTY_BANDS:
        if lo == 0.0:
            if value <= hi:
                return label
        elif value > lo and value <= hi:
            return label
    raise ValueError(f"No difficulty band for prior margin {prior_margin}")


def region_for_race_code(race_code: str) -> str:
    state = (race_code or "").split("-", 1)[0].strip().upper()
    for region, states in REGION_STATES.items():
        if state in states:
            return region
    return "Unknown"


def predictive_profile(pred: dict, race: dict, polls: list[dict], cutoff) -> dict:
    """Freeze sparsity/difficulty/geography without opening outcomes."""
    profile = sm.source_profile(pred, race, polls, cutoff)
    prior_margin = float(profile["prior_margin_d_minus_r"])
    profile.update({
        "prior_abs_margin_pp": round(abs(prior_margin), 9),
        "prior_difficulty_band": difficulty_band(prior_margin),
        "prior_competitive_10pp": abs(prior_margin) <= COMPETITIVE_PRIOR_THRESHOLD_PP,
        "poll_sparse": int(profile["poll_count"]) == 1,
        "source_sparse": int(profile["unique_pollsters"]) == 1,
        "region": region_for_race_code(profile["race_code"]),
    })
    return profile


def scored_block(rows: list[dict]) -> dict:
    if not rows:
        return {"state": "unavailable", "n": 0}
    return {
        "state": "scored",
        "n": len(rows),
        "mean_prior_abs_margin_pp": round(sum(r["prior_abs_margin_pp"] for r in rows) / len(rows), 6),
        "one_poll_share": round(sum(bool(r["poll_sparse"]) for r in rows) / len(rows), 6),
        "one_pollster_share": round(sum(bool(r["source_sparse"]) for r in rows) / len(rows), 6),
        "raw_poll": pe.error_metrics(rows, "raw_poll_margin_d_minus_r"),
        "prior": pe.error_metrics(rows, "prior_margin_d_minus_r"),
        "full_model": pe.error_metrics(rows, "full_model_margin_d_minus_r"),
    }


def group_rows(rows: list[dict], key: str, labels: tuple[str, ...]) -> list[dict]:
    return [{"band": label, **scored_block([r for r in rows if r.get(key) == label])} for label in labels]


def interaction_cells(rows: list[dict], sparse_key: str) -> list[dict]:
    cells = []
    for competitive in (True, False):
        for sparse in (True, False):
            cell_rows = [
                r for r in rows
                if bool(r["prior_competitive_10pp"]) == competitive
                and bool(r[sparse_key]) == sparse
            ]
            cells.append({
                "prior_competitiveness": "within_10pp" if competitive else "over_10pp",
                "sparsity": "sparse" if sparse else "multi",
                **scored_block(cell_rows),
            })
    return cells


def geography_rows(rows: list[dict]) -> list[dict]:
    out = []
    for region in REGION_ORDER:
        region_rows = [r for r in rows if r.get("region") == region]
        out.append({
            "region": region,
            **scored_block(region_rows),
            "competitive_prior_n": sum(bool(r["prior_competitive_10pp"]) for r in region_rows),
            "one_poll_n": sum(bool(r["poll_sparse"]) for r in region_rows),
            "one_pollster_n": sum(bool(r["source_sparse"]) for r in region_rows),
        })
    unknown = [r for r in rows if r.get("region") == "Unknown"]
    if unknown:
        out.append({
            "region": "Unknown",
            **scored_block(unknown),
            "competitive_prior_n": sum(bool(r["prior_competitive_10pp"]) for r in unknown),
            "one_poll_n": sum(bool(r["poll_sparse"]) for r in unknown),
            "one_pollster_n": sum(bool(r["source_sparse"]) for r in unknown),
        })
    return out


def checkpoint_interaction(checkpoint: dict, races: list[dict], polls: list[dict], result_margins: dict[str, float]) -> dict:
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
            raise ValueError(f"Sparsity interaction active roster missing {pred.get('race_code')}")
        profiles.append(predictive_profile(pred, race, polls, cutoff))

    rows = []
    missing = []
    for profile in profiles:
        code = profile["race_code"]
        if code not in result_margins:
            missing.append(code)
            continue
        rows.append({**profile, "result_margin_d_minus_r": float(result_margins[code])})

    if not rows:
        return {
            "state": "unavailable",
            "reason": "no_interaction_rows_with_certified_margin",
            "n": 0,
            "missing_result_margin_races": sorted(set(missing)),
        }

    house = [r for r in rows if (r.get("race_type") or "").lower() == "house"]
    senate = [r for r in rows if (r.get("race_type") or "").lower() == "senate"]

    def scope_block(scope_rows: list[dict]) -> dict:
        if not scope_rows:
            return {"state": "unavailable", "n": 0}
        return {
            "state": "scored",
            "n": len(scope_rows),
            "overall": scored_block(scope_rows),
            "by_prior_difficulty": group_rows(scope_rows, "prior_difficulty_band", tuple(label for label, _, _ in PRIOR_DIFFICULTY_BANDS)),
            "poll_depth_x_prior_competitiveness": interaction_cells(scope_rows, "poll_sparse"),
            "source_count_x_prior_competitiveness": interaction_cells(scope_rows, "source_sparse"),
            "by_region": geography_rows(scope_rows),
        }

    return {
        "state": "scored",
        "n": len(rows),
        "scope": "scoreable polled two-major-party races with admitted certified D/R result margin",
        "feature_assignment_uses_outcomes": False,
        "difficulty_signal": "absolute structural+generic pre-poll prior margin at checkpoint",
        "competitive_prior_threshold_pp": COMPETITIVE_PRIOR_THRESHOLD_PP,
        "missing_result_margin_races": sorted(set(missing)),
        "all_polled": scope_block(rows),
        "house_only": scope_block(house),
        "senate_only": scope_block(senate),
        "interpretation": "Sparsity and difficulty are observational. A sparse competitive cell can have larger error because hard races receive less polling, because sparse evidence is noisier, or both; this diagnostic does not identify a causal polling-depth effect.",
    }


def cross_cycle(payload: dict) -> dict:
    rows = []
    for cycle in payload.get("cycles", []):
        if cycle.get("state") != "scored":
            continue
        cp = next((c for c in cycle.get("checkpoints", []) if int(c.get("days_to_election") or -1) == 1), None)
        block = (cp or {}).get("score", {}).get("sparsity_interaction", {}).get("house_only")
        if not block or block.get("state") != "scored":
            continue
        rows.append({
            "cycle": cycle["cycle"],
            "n": block["n"],
            "by_prior_difficulty": block["by_prior_difficulty"],
            "poll_depth_x_prior_competitiveness": block["poll_depth_x_prior_competitiveness"],
            "source_count_x_prior_competitiveness": block["source_count_x_prior_competitiveness"],
            "by_region": block["by_region"],
        })
    return {
        "state": "scored" if len(rows) >= 2 else "partial",
        "checkpoint_days_to_election": 1,
        "scope": "House-only final checkpoint; sparsity/difficulty/geography frozen before outcomes",
        "cycles": rows,
        "interpretation": "Cross-cycle interaction cells test whether thin polling was disproportionately concentrated in races the frozen pre-poll prior already regarded as difficult. They are descriptive, not causal.",
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
            raise RuntimeError(f"No admitted result margins for sparsity interaction audit {year}")
        for checkpoint in cycle.get("checkpoints", []):
            if checkpoint.get("state") != "scored":
                continue
            checkpoint.setdefault("score", {})["sparsity_interaction"] = checkpoint_interaction(checkpoint, races, polls, result_margins)

    payload.setdefault("diagnostic_contract", {})["sparsity_interaction"] = {
        "scope": "scoreable races with eligible race-level polls and admitted certified D/R result margins",
        "difficulty_signal": "absolute pre-poll structural+generic prior margin",
        "difficulty_bands_pp": ["0-5", ">5-10", ">10-20", ">20"],
        "headline_competitive_threshold_pp": COMPETITIVE_PRIOR_THRESHOLD_PP,
        "poll_sparsity": "exactly one eligible race poll versus two or more",
        "source_sparsity": "exactly one eligible pollster versus two or more",
        "geography": "fixed Census-style Northeast/Midwest/South/West assignment from race state code",
        "feature_assignment_uses_outcomes": False,
        "model_effect": "NONE",
        "causal_boundary": "Race difficulty, geography and polling sparsity are observational characteristics; interaction differences do not identify a causal effect of adding polls.",
    }
    payload.setdefault("metric_definitions", {})["pre_poll_race_difficulty"] = "Absolute Democratic-minus-Republican structural+generic prior margin before race polling is blended. Smaller absolute margins mean the frozen model regarded the race as harder before race polls."
    payload.setdefault("leakage_guards", []).append("Polling sparsity, unique-source sparsity, prior-difficulty bands and geographic regions are assigned before certified outcome margins are joined; the interaction audit cannot define cells from observed errors.")
    payload["sparsity_interaction_cross_cycle"] = cross_cycle(payload)
    for hypothesis in payload.get("cross_cycle", {}).get("hypotheses", []):
        if hypothesis.get("id") == "race_poll_composition":
            hypothesis["state"] = "diagnostic_exposed"
            hypothesis["evidence"] = "source_mix plus sparsity_interaction: fixed polling-depth/source-count cells crossed with pre-poll prior competitiveness and geography"
    return payload


def main() -> None:
    payload = json.loads(MODEL_LAB.read_text(encoding="utf-8"))
    payload = augment(payload)
    MODEL_LAB.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(MODEL_LAB),
        "diagnostic": "sparsity_interaction",
        "cross_cycle_state": payload.get("sparsity_interaction_cross_cycle", {}).get("state"),
    }))


if __name__ == "__main__":
    main()
