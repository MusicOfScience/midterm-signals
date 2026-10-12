#!/usr/bin/env python3
"""Build the deterministic MIDTERM SIGNALS v0.1 forecast snapshot.

The script consumes checked-in, dated observations. It performs no network access and
never silently substitutes missing observations. Output is deterministic for the same
inputs, model version and seed.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "2026-10-12"
MODEL_VERSION = "0.1.0"
SEED = 20261012
SIMULATIONS = 100_000

INPUT_DIR = ROOT / "data" / "raw" / SNAPSHOT
REF_DIR = ROOT / "data" / "reference"
OUT_DIR = ROOT / "public" / "data"
HISTORY_DIR = OUT_DIR / "history"

RATING_PRIORS = {
    "Solid D": 0.995,
    "Likely D": 0.90,
    "Lean D": 0.70,
    "Toss Up": 0.50,
    "Lean R": 0.30,
    "Likely R": 0.10,
    "Solid R": 0.005,
}

NORMAL = NormalDist()


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def canonical_hash(path: Path) -> str:
    data = json.dumps(read_json(path), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def clamp(p: float, lo: float = 0.005, hi: float = 0.995) -> float:
    return max(lo, min(hi, p))


def logit(p: float) -> float:
    p = clamp(p)
    return math.log(p / (1.0 - p))


def inv_logit(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def quantile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        raise ValueError("empty distribution")
    i = int(round((len(sorted_values) - 1) * q))
    return sorted_values[max(0, min(len(sorted_values) - 1, i))]


def ols(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    if len(xs) != len(ys) or len(xs) < 3:
        raise ValueError("insufficient calibration sample")
    xbar = sum(xs) / len(xs)
    ybar = sum(ys) / len(ys)
    sxx = sum((x - xbar) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("zero calibration variance")
    beta = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sxx
    alpha = ybar - beta * xbar
    residuals = [y - (alpha + beta * x) for x, y in zip(xs, ys)]
    sigma = math.sqrt(sum(r * r for r in residuals) / max(1, len(xs) - 2))
    return alpha, beta, sigma


def senate_race_probability(row: dict) -> dict:
    rating = row["rating"]
    prior = RATING_PRIORS[rating]
    margin = row.get("dem_poll_margin")
    n = int(row.get("poll_count") or 0)

    # Nebraska has an independent, not a Democratic, principal challenger.
    # We estimate the non-Republican upset chance but assign zero Democratic-
    # control credit until a caucus/organization commitment is documented.
    is_ne_independent = row["state"] == "NE" and not row.get("dem_candidate")

    if margin is None:
        race_p = prior
        poll_p = None
        weight = 0.0
    else:
        # 5-point effective margin error is intentionally wider than a single
        # poll's sampling error and represents aggregate/model uncertainty.
        poll_p = clamp(normal_cdf(float(margin) / 5.0))
        # Poll evidence gains weight slowly and is capped; ratings and polling
        # are deliberately not treated as independent certainty machines.
        weight = min(0.65, 0.18 + 0.10 * math.log1p(max(n, 0)))
        race_p = inv_logit((1.0 - weight) * logit(prior) + weight * logit(poll_p))

    race_p = clamp(race_p)
    control_p = 0.0 if is_ne_independent else race_p
    result = dict(row)
    result["rating_prior_dem_or_non_r"] = round(prior, 4)
    result["poll_probability_dem_or_non_r"] = None if poll_p is None else round(poll_p, 4)
    result["poll_weight"] = round(weight, 4)
    result["forecast_probability_dem_or_non_r"] = round(race_p, 4)
    result["democratic_control_credit_probability"] = round(control_p, 4)
    result["probability_type"] = "non_republican_win" if is_ne_independent else "democratic_win"
    return result


def main() -> None:
    national_path = INPUT_DIR / "national.json"
    house_path = INPUT_DIR / "house_ratings.json"
    senate_path = INPUT_DIR / "senate.json"
    calibration_path = REF_DIR / "house_midterm_calibration.json"

    national = read_json(national_path)
    house = read_json(house_path)
    senate = read_json(senate_path)
    calibration = read_json(calibration_path)

    if national["snapshot_date"] != SNAPSHOT or senate["snapshot_date"] != SNAPSHOT:
        raise ValueError("snapshot date mismatch")
    if sum(house["rating_counts"].values()) != 435:
        raise ValueError("House rating counts do not sum to 435")
    if len(house["competitive_races"]) != 76:
        raise ValueError("expected 76 non-Solid House races in current snapshot")
    if len(senate["races"]) != 35:
        raise ValueError("Senate contest universe must contain 35 races")

    # HOUSE
    xs = [float(x["dem_margin"]) for x in calibration["elections"]]
    ys = [float(x["dem_seats"]) for x in calibration["elections"]]
    alpha, beta, residual_sigma = ols(xs, ys)

    gb_margin = float(national["generic_ballot"]["dem_margin"])
    rating_map_expected = sum(
        int(house["rating_counts"][rating]) * RATING_PRIORS[rating]
        for rating in RATING_PRIORS
    )

    # Predeclared v0.1 blend. The national vote/seat leg is 65%; the current
    # categorical map prior is 35%. The blend is documented and versioned.
    house_weights = {"national_vote_seat_leg": 0.65, "current_map_prior_leg": 0.35}
    generic_margin_sigma = 3.0
    map_prior_sigma_seats = 8.0

    # SENATE
    senate_races = [senate_race_probability(row) for row in senate["races"]]
    senate_control_ps = {
        row["state"]: float(row["democratic_control_credit_probability"])
        for row in senate_races
    }

    # JOINT MONTE CARLO
    # One shared national latent shock ties House vote environment and Senate
    # race errors together. The Senate latent correlation is deliberately
    # modest (rho=.20); race-specific errors remain dominant.
    rho = 0.20
    rng = random.Random(SEED)
    house_seats: list[int] = []
    senate_dem_caucus_seats: list[int] = []
    joint = {"dem_both": 0, "dem_house_rep_senate": 0, "rep_house_dem_senate": 0, "rep_both": 0}

    for _ in range(SIMULATIONS):
        shared = rng.gauss(0.0, 1.0)

        simulated_margin = gb_margin + generic_margin_sigma * shared
        national_leg = alpha + beta * simulated_margin + rng.gauss(0.0, residual_sigma)
        map_leg = rng.gauss(rating_map_expected, map_prior_sigma_seats)
        d_house = round(
            house_weights["national_vote_seat_leg"] * national_leg
            + house_weights["current_map_prior_leg"] * map_leg
        )
        d_house = max(0, min(435, d_house))
        house_seats.append(d_house)

        d_up = 0
        for state, p in senate_control_ps.items():
            if p <= 0.0:
                continue
            if p >= 1.0:
                d_up += 1
                continue
            threshold = NORMAL.inv_cdf(1.0 - p)
            score = math.sqrt(rho) * shared + math.sqrt(1.0 - rho) * rng.gauss(0.0, 1.0)
            if score > threshold:
                d_up += 1

        d_senate = int(senate["not_up"]["democratic_caucus"]) + d_up
        senate_dem_caucus_seats.append(d_senate)

        dh = d_house >= 218
        ds = d_senate >= 51
        if dh and ds:
            joint["dem_both"] += 1
        elif dh and not ds:
            joint["dem_house_rep_senate"] += 1
        elif (not dh) and ds:
            joint["rep_house_dem_senate"] += 1
        else:
            joint["rep_both"] += 1

    house_sorted = sorted(house_seats)
    senate_sorted = sorted(senate_dem_caucus_seats)

    house_expected = sum(house_seats) / SIMULATIONS
    senate_expected = sum(senate_dem_caucus_seats) / SIMULATIONS
    house_d_control = sum(v >= 218 for v in house_seats) / SIMULATIONS
    senate_d_control = sum(v >= 51 for v in senate_dem_caucus_seats) / SIMULATIONS

    house_detail = []
    for row in house["competitive_races"]:
        house_detail.append({
            "race_id": row["race_id"],
            "rating": row["rating"],
            "map_prior_probability_dem": RATING_PRIORS[row["rating"]],
            "probability_type": "categorical_map_prior",
        })
    house_detail.sort(key=lambda r: (abs(r["map_prior_probability_dem"] - 0.5), r["race_id"]))
    senate_races.sort(key=lambda r: (abs(r["forecast_probability_dem_or_non_r"] - 0.5), r["state"]))

    inputs = {
        "national": canonical_hash(national_path),
        "house_ratings": canonical_hash(house_path),
        "senate": canonical_hash(senate_path),
        "house_calibration": canonical_hash(calibration_path),
    }

    forecast = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "publication_state": "published_provisional",
        "as_of": SNAPSHOT,
        "election_date": national["election_date"],
        "seed": SEED,
        "simulations": SIMULATIONS,
        "input_sha256": inputs,
        "national_environment": {
            "generic_ballot": national["generic_ballot"],
            "presidential_approval": national["presidential_approval"],
        },
        "house": {
            "total_seats": 435,
            "majority": 218,
            "all_seats_accounted_for": True,
            "expected_democratic_seats": round(house_expected, 2),
            "expected_republican_seats": round(435 - house_expected, 2),
            "median_democratic_seats": quantile(house_sorted, 0.50),
            "democratic_control_probability": round(house_d_control, 4),
            "republican_control_probability": round(1.0 - house_d_control, 4),
            "interval_80_democratic_seats": [quantile(house_sorted, 0.10), quantile(house_sorted, 0.90)],
            "interval_90_democratic_seats": [quantile(house_sorted, 0.05), quantile(house_sorted, 0.95)],
            "rating_counts": house["rating_counts"],
            "map_prior_expected_democratic_seats": round(rating_map_expected, 3),
            "competitive_race_count": len(house_detail),
            "solid_races_aggregated": house["rating_counts"]["Solid D"] + house["rating_counts"]["Solid R"],
            "competitive_races": house_detail,
            "national_vote_seat_model": {
                "intercept": round(alpha, 6),
                "slope_seats_per_dem_margin_point": round(beta, 6),
                "residual_sigma_seats": round(residual_sigma, 6),
                "generic_ballot_sigma_points": generic_margin_sigma,
                "map_prior_sigma_seats": map_prior_sigma_seats,
                "blend_weights": house_weights,
                "historical_cycles": [r["year"] for r in calibration["elections"]],
            },
        },
        "senate": {
            "total_seats": 100,
            "majority_for_democratic_control": 51,
            "not_up": senate["not_up"],
            "contested_seats": 35,
            "expected_democratic_caucus_seats": round(senate_expected, 2),
            "median_democratic_caucus_seats": quantile(senate_sorted, 0.50),
            "democratic_control_probability": round(senate_d_control, 4),
            "non_democratic_control_probability": round(1.0 - senate_d_control, 4),
            "interval_80_democratic_caucus_seats": [quantile(senate_sorted, 0.10), quantile(senate_sorted, 0.90)],
            "interval_90_democratic_caucus_seats": [quantile(senate_sorted, 0.05), quantile(senate_sorted, 0.95)],
            "shared_race_error_correlation": rho,
            "races": senate_races,
            "control_note": "A 50-50 Senate is treated as Republican control because the Republican vice president breaks ties. Nebraska independent Dan Osborn is assigned no Democratic-control credit absent a documented caucus/organization commitment.",
        },
        "joint_control": {key: round(value / SIMULATIONS, 4) for key, value in joint.items()},
        "source_registry": [
            national["generic_ballot"]["source"],
            national["presidential_approval"]["source"],
            house["source"],
            senate["rating_source"],
            senate["poll_source"],
            {"name": "U.S. House historical election statistics", "url": calibration["source_url"], "use": "House national vote-to-seat calibration"},
        ],
        "limitations": [
            "Model v0.1 is a transparent provisional production baseline, not a final fully backtested district model.",
            "House current-map information enters through categorical ratings; the 359 Solid seats are aggregated rather than republished as a proprietary all-seat table.",
            "House race-level entries are categorical map priors, not individualized district polling forecasts.",
            "Senate polling probabilities use a deliberately conservative effective margin-error scale and capped evidence weight.",
            "Candidate quality, fundraising and qualitative campaign intelligence do not silently alter numerical probabilities.",
            "Presidential approval is descriptive only in v0.1 and has a numerical coefficient of zero.",
        ],
    }

    status = {
        "schema_version": 1,
        "project": "MIDTERM SIGNALS",
        "election_date": national["election_date"],
        "as_of": SNAPSHOT,
        "production_forecast": "published",
        "publication_label": "LIVE BASELINE · MODEL v0.1",
        "model_version": MODEL_VERSION,
        "simulations": SIMULATIONS,
        "input_sha256": inputs,
        "house_all_435_accounted_for": True,
        "senate_all_35_contests_accounted_for": True,
        "warnings": forecast["limitations"],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    forecast_text = json.dumps(forecast, indent=2, ensure_ascii=False) + "\n"
    status_text = json.dumps(status, indent=2, ensure_ascii=False) + "\n"
    (OUT_DIR / "forecast.json").write_text(forecast_text, encoding="utf-8")
    (OUT_DIR / "status.json").write_text(status_text, encoding="utf-8")
    (HISTORY_DIR / f"{SNAPSHOT}.json").write_text(forecast_text, encoding="utf-8")
    (HISTORY_DIR / "index.json").write_text(
        json.dumps({"schema_version": 1, "snapshots": [{"as_of": SNAPSHOT, "model_version": MODEL_VERSION, "path": f"./{SNAPSHOT}.json"}]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"House D expected {house_expected:.2f}; P(control)={house_d_control:.3f}. Senate D-caucus expected {senate_expected:.2f}; P(control)={senate_d_control:.3f}.")


if __name__ == "__main__":
    main()
