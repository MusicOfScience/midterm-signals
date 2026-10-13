#!/usr/bin/env python3
"""Build the official MIDTERM SIGNALS Model Lab artefact with scoreability gates.

The numerical replay engine lives in model_lab.py. This orchestration layer adds
corpus-level scoreability decisions that must be frozen before certified outcome
bytes are opened. It never changes a probability or production-model coefficient.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import model_lab as core


PRESENCE_EXCLUSION = "unstable_major_party_presence_across_fixed_checkpoints"
MISSING_CHECKPOINT_EXCLUSION = "missing_race_roster_at_fixed_checkpoint"


def candidate_presence(row: dict) -> tuple[bool, bool]:
    """Return only D/R candidate presence, not candidate identity or outcomes."""
    dem = bool((row.get("dem_name") or "").strip())
    rep = bool((row.get("rep_name") or "").strip())
    return dem, rep


def fixed_sample_scoreability(races: list[dict], election) -> dict:
    """Freeze a fixed replay sample using predictive roster evidence only.

    A race is excluded from every checkpoint if it is absent at any fixed
    checkpoint or if D/R candidate *presence* changes across the five checkpoint
    rosters. The latter means the archive cannot distinguish a genuine contest-
    status change from a source omission, so missingness must not be interpreted
    as an unopposed/same-party race.
    """
    rosters: dict[int, dict[str, dict]] = {}
    for days in core.CHECKPOINT_DAYS:
        cutoff = election - timedelta(days=days)
        rosters[days] = {r["race_code"]: r for r in core.select_race_versions(races, cutoff)}

    all_codes = set().union(*(set(rows) for rows in rosters.values())) if rosters else set()
    exclusions = []
    for code in sorted(all_codes):
        missing_days = [days for days in core.CHECKPOINT_DAYS if code not in rosters[days]]
        if missing_days:
            exclusions.append({
                "race_code": code,
                "reason": MISSING_CHECKPOINT_EXCLUSION,
                "missing_checkpoint_days": missing_days,
            })
            continue
        signatures = [candidate_presence(rosters[days][code]) for days in core.CHECKPOINT_DAYS]
        if len(set(signatures)) > 1:
            exclusions.append({
                "race_code": code,
                "reason": PRESENCE_EXCLUSION,
                "checkpoint_presence": [
                    {
                        "days_to_election": days,
                        "dem_present": candidate_presence(rosters[days][code])[0],
                        "rep_present": candidate_presence(rosters[days][code])[1],
                    }
                    for days in core.CHECKPOINT_DAYS
                ],
            })

    excluded_codes = {row["race_code"] for row in exclusions}
    admitted_codes = sorted(all_codes - excluded_codes)
    return {
        "state": "frozen_pre_outcome",
        "rule": "Race must be present at all fixed checkpoints and retain stable Democratic/Republican candidate presence across them.",
        "rationale": "An archive that later gains or loses a major-party candidate cannot safely distinguish a true contest-status change from earlier source omission. Missing evidence is not treated as an unopposed race.",
        "uses_outcomes": False,
        "universe_races": len(all_codes),
        "admitted_races": len(admitted_codes),
        "excluded_races": len(exclusions),
        "admitted_race_codes": admitted_codes,
        "exclusions": exclusions,
    }


def run_cycle(cycle_dir: Path, config: dict, contract: dict) -> dict:
    year = int(config["cycle"])
    election = core.parse_day(config.get("election_date"))
    base = {
        "cycle": year,
        "election_date": config.get("election_date"),
        "corpus_state": config.get("corpus_state", "unknown"),
        "provenance": config.get("provenance", []),
        "checkpoints": [],
    }
    if not election:
        return {**base, "state": "unavailable", "blocking_reasons": ["invalid_election_date"]}
    blockers = core.cycle_blockers(cycle_dir, config, contract)
    if blockers:
        return {**base, "state": "unavailable", "blocking_reasons": blockers}

    races = core.read_csv(cycle_dir / "races.csv")
    polls = core.read_csv(cycle_dir / "polls.csv")
    scoreability = fixed_sample_scoreability(races, election)
    admitted = set(scoreability["admitted_race_codes"])
    national = config["national_presidential_margins"]
    predictions_by_code: dict[str, list[dict]] = defaultdict(list)
    replay_checkpoints = []

    # Predictive replay and scoreability are complete before outcome bytes open.
    for days in core.CHECKPOINT_DAYS:
        cutoff = election - timedelta(days=days)
        raw_active = core.select_race_versions(races, cutoff)
        active = [r for r in raw_active if r["race_code"] in admitted]
        gcb, gcb_count, gcb_latest = core.aggregate_generic(polls, cutoff)
        checkpoint = {
            "days_to_election": days,
            "cutoff": cutoff.isoformat(),
            "roster_race_count": len(raw_active),
            "race_count": len(active),
            "scoreability_excluded_count": len(raw_active) - len(active),
            "generic_ballot_poll_count": gcb_count,
            "generic_ballot_latest": gcb_latest,
            "generic_ballot_margin_d_minus_r": round(gcb, 4) if gcb is not None else None,
        }
        if not active:
            checkpoint.update({"state": "unscored", "reason": "no_scoreable_race_roster_known_by_cutoff"})
            replay_checkpoints.append(checkpoint)
            continue
        if gcb is None:
            checkpoint.update({"state": "unscored", "reason": "no_eligible_generic_ballot_input"})
            replay_checkpoints.append(checkpoint)
            continue
        predictions = [core.race_probability(r, polls, gcb, cutoff, national) for r in active]
        for prediction in predictions:
            predictions_by_code[prediction["race_code"]].append(prediction)
        checkpoint["predictions"] = predictions
        checkpoint["state"] = "replayed_unscored"
        replay_checkpoints.append(checkpoint)

    # Certified results become visible only after the fixed scoreability sample
    # and every checkpoint prediction have been frozen above.
    outcomes = core.load_results(core.read_csv(cycle_dir / "results.csv"))
    any_unscored = False
    for checkpoint in replay_checkpoints:
        predictions = checkpoint.get("predictions") or []
        if not predictions:
            any_unscored = True
            continue
        score = core.score_checkpoint(predictions, outcomes)
        checkpoint["score"] = score
        checkpoint["state"] = score["state"]
        if score["state"] != "scored":
            any_unscored = True

    evolution = [
        {
            "race_code": code,
            "points": [{"cutoff": row["cutoff"], "dem_probability": row["dem_probability"]} for row in rows],
        }
        for code, rows in sorted(predictions_by_code.items())
    ]
    movement = core.movement_diagnostics(replay_checkpoints, outcomes) if not any_unscored else {
        "state": "unavailable",
        "reason": "complete_scored_cycle_required",
    }
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
        "scoreability": scoreability,
        "checkpoints": replay_checkpoints,
        "forecast_evolution": evolution,
        "movement": movement,
        "chamber_scope": chamber_scope,
    }


def build() -> dict:
    contract = core.production_contract_state()
    cycles = []
    for year in (2018, 2022):
        cycle_dir = core.HISTORICAL / str(year)
        config_path = cycle_dir / "cycle.json"
        if not config_path.is_file():
            cycles.append({"cycle": year, "state": "unavailable", "blocking_reasons": ["missing:cycle.json"], "checkpoints": []})
            continue
        cycles.append(run_cycle(cycle_dir, json.loads(config_path.read_text()), contract))

    scored = sum(c.get("state") == "scored" for c in cycles)
    return {
        "schema_version": "1.1.1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "product": "MIDTERM SIGNALS MODEL LAB",
        "evaluation_only": True,
        "retuning_allowed": False,
        "model_contract": {**core.MODEL_CONTRACT, **contract},
        "checkpoints_days_to_election": list(core.CHECKPOINT_DAYS),
        "diagnostic_contract": {
            "competitive_bands": [
                {"label": label, "lower": lo, "upper": hi, "nested": True}
                for label, lo, hi in core.COMPETITIVE_BANDS
            ],
            "safe_definition": "p_dem < 0.20 or p_dem > 0.80",
            "calibration_bin_width": 0.10,
            "movement_threshold": core.MOVEMENT_THRESHOLD,
            "confident_miss_threshold": core.CONFIDENT_MISS_THRESHOLD,
            "scoreability_gate": "stable Democratic/Republican candidate presence at all five fixed checkpoints, frozen before results are opened",
            "rule": "Thresholds and scoreability rules are fixed before reviewing diagnostic results and are not model coefficients.",
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
            "scoreability_exclusion": "Evaluation-only exclusion decided from predictive roster evidence before outcomes are opened. It changes the scored historical sample, never a forecast probability.",
        },
        "leakage_guards": [
            "Corpus state must be explicitly admitted before replay or scoring can run.",
            "Polls are eligible only when publication_date (or end_date if publication_date is absent) is on or before the checkpoint.",
            "Candidate/race roster rows are versioned by known_date; the latest row known by the checkpoint is selected.",
            "The fixed scored sample is frozen before results are opened; races with unstable major-party candidate presence across checkpoints are excluded rather than treating archive missingness as an unopposed race.",
            "Structural presidential baselines must pre-date the cycle and be admitted with provenance.",
            "Election outcome bytes are not opened until every checkpoint prediction and scoreability decision has been produced; outcomes are then passed only to scoring functions.",
            "A checkpoint is not scored if any replayed race lacks an outcome.",
            "Missing generic-ballot input is missing, never zero.",
            "Replay output cannot mutate the live forecast or model contract.",
            "Competitive, polling and chamber diagnostics reuse the frozen checkpoint predictions; they do not create alternative forecasts.",
        ],
        "cycles": cycles,
        "cross_cycle": core.cross_cycle_comparison(cycles),
        "summary": {
            "state": "scored" if scored == len(cycles) else "unscored" if scored == 0 else "partial",
            "scored_cycles": scored,
            "requested_cycles": len(cycles),
            "message": "Historical performance remains unpublished until each cycle passes the leakage-free corpus gates." if scored < len(cycles) else "All admitted historical cycles passed replay, scoreability and scoring gates.",
        },
    }


def main() -> None:
    payload = build()
    core.OUT.parent.mkdir(parents=True, exist_ok=True)
    core.OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(core.OUT),
        "state": payload["summary"]["state"],
        "contract": payload["model_contract"]["state"],
        "samples": {str(c["cycle"]): c.get("scoreability", {}).get("admitted_races") for c in payload["cycles"]},
    }))


if __name__ == "__main__":
    main()
