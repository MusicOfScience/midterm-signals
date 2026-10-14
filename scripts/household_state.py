#!/usr/bin/env python3
"""Build the governed US Household & Voter State module for MIDTERM SIGNALS.

This entry point re-exports the module's pure classifier functions for testing.
The module is contextual analysis only and cannot mutate forecast probabilities.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from household_state_core import *
from household_state_classifiers import *
from household_state_composites import *
from household_state_outputs import *
from household_state_render import *

def main() -> None:
    as_of_override = os.environ.get("MIDTERM_SIGNALS_AS_OF")
    analytical_today = date.fromisoformat(as_of_override) if as_of_override else date.today()
    now = utc_now()
    as_of = analytical_today.isoformat()
    forecast_before = file_hash(FORECAST)

    registry = read_json(REF_ROOT / "household_source_registry.json", {"sources": []}) or {"sources": []}
    errors: dict[str, str] = {}
    bls_payload: dict | None = None
    try:
        bls_payload = fetch_bls(2019, analytical_today.year)
    except Exception as exc:
        errors["bls"] = f"{type(exc).__name__}: {exc}"
        raw_fallback = DATA_ROOT / "raw" / "latest_bls.json"
        bls_payload = read_json(raw_fallback)

    observations: list[dict] = []
    histories: dict[str, list[tuple[date, float]]] = {}
    if isinstance(bls_payload, dict):
        raw_dir = DATA_ROOT / "raw" / as_of
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / "bls.json"
        if not raw_path.exists():
            write_json(raw_path, {"retrieved_at": now, "source": "Bureau of Labor Statistics", "payload": bls_payload})
        write_json(DATA_ROOT / "raw" / "latest_bls.json", bls_payload)
        bls_obs, histories = normalize_bls(bls_payload, now, analytical_today)
        observations.extend(bls_obs)

    manual_obs = load_manual_observations(analytical_today, now)
    automated_ids = {x.get("id") for x in observations if x.get("id")}
    manual_obs = [x for x in manual_obs if x.get("id") not in automated_ids]
    observations.extend(manual_obs)
    validate_observations(observations)
    by_id = latest_by_id(observations)
    baseline = load_provisional_baseline()

    states: dict[str, dict] = {}
    states["affordability_pressure"] = classify_affordability(by_id)
    states["real_income_pressure"] = classify_real_income(by_id)
    labour, retention, mobility = classify_labour(by_id, histories)
    states["labour_market_security"] = labour
    states["employment_retention_security"] = retention
    states["job_mobility_security"] = mobility

    manual_state_sensors = {
        "aggregate_wealth", "wealth_distribution", "household_cash_flow", "financial_buffer", "credit_stress",
        "revolving_credit_stress", "auto_credit_stress", "mortgage_credit_stress", "student_credit_stress", "total_household_credit_stress",
        "consumption", "current_conditions", "expectations", "sentiment_behaviour_divergence", "essential_discretionary_pressure",
        "economic_salience", "national_personal_economy_gap", "policy_attribution", "incumbent_attribution",
        "cross_partisan_affordability_consensus", "partisan_deflection", "independent_state", "vote_intention_pressure",
        "electoral_economic_pressure",
    }
    for sensor in manual_state_sensors:
        states[sensor] = survey_state_from_manual(sensor, manual_obs, baseline, minimum_sources=2)
    states["k_shaped_economy"] = k_shaped_state_from_manual(manual_obs, baseline)

    # Explicit stress taxonomy remains separate even when the headline cash-flow
    # state is provisional.
    states["stress_type"] = {"sensor": "stress_type", "state": baseline.get("stress_type", ["CASH-FLOW PROBLEM"]), "confidence": "LOW", "state_status": "PROVISIONAL_BASELINE_NOT_YET_TRIANGULATED", "forecast_effect": "NONE"}

    previous = read_json(PUBLIC_ROOT / "household_state.json", {}) or {}
    revisions = detect_revisions(observations, previous)
    contradictions = contradiction_engine(states, by_id)
    alerts = alert_engine(states, by_id, histories)
    composite = stress_score(states)
    political_composite = political_pressure_score(states, composite)
    electoral_links = electoral_transmission(states)
    dashboard = build_dashboard(observations, states)
    chain = transmission(states, baseline)
    distributional = build_distributional_state(observations)
    change_log = monthly_change_log(states, previous)
    policy_claims = load_policy_claims()

    observed_sources = {str(x.get("source_id")) for x in observations if x.get("source_id")}
    health = source_health(registry, observations, errors, now)
    module_available = "bls" in observed_sources and "bls" not in errors

    household_state = {
        "module": "US HOUSEHOLD & VOTER ECONOMIC STATE",
        "as_of": as_of,
        "generated_at": now,
        "governance": {"forecast_effect": "NONE", "separation": ["OBSERVATIONS", "DERIVED INDICATORS", "ANALYTICAL STATE CLASSIFICATIONS", "POLITICAL INTERPRETATION", "ELECTION INFERENCE"], "numerical_forecast_input": False},
        "states": states,
        "stress_composite": composite,
        "political_economic_pressure_composite": political_composite,
        "transmission_chain": chain,
        "electoral_transmission": electoral_links,
        "distributional_state": distributional,
        "alerts": alerts,
        "revisions": revisions,
        "observations": observations,
        "forecast_effect": "NONE",
    }
    voter_state = {
        "as_of": as_of, "generated_at": now,
        "economic_salience": states["economic_salience"], "incumbent_attribution": states["incumbent_attribution"],
        "partisan_deflection": states["partisan_deflection"], "independent_state": states["independent_state"],
        "national_personal_economy_gap": states["national_personal_economy_gap"],
        "policy_attribution": states["policy_attribution"],
        "cross_partisan_affordability_consensus": states["cross_partisan_affordability_consensus"],
        "electoral_economic_pressure": states["electoral_economic_pressure"],
        "electoral_transmission": electoral_links,
        "political_economic_pressure_composite": political_composite,
        "forecast_effect": "NONE",
    }
    partisan = {**states["partisan_deflection"], "as_of": as_of, "generated_at": now, "forecast_effect": "NONE"}
    source_payload = {"as_of": as_of, "generated_at": now, "sources": health, "forecast_effect": "NONE"}
    watch = build_watchlist(dashboard)
    watch_payload = {"as_of": as_of, "watchlist": watch, "forecast_effect": "NONE"}

    outputs = {
        "household_state.json": household_state,
        "voter_state.json": voter_state,
        "partisan_deflection.json": partisan,
        "household_dashboard.json": {"as_of": as_of, "indicators": dashboard, "forecast_effect": "NONE"},
        "contradictions.json": {"as_of": as_of, "contradictions": contradictions, "forecast_effect": "NONE"},
        "watchlist.json": watch_payload,
        "source_health.json": source_payload,
        "monthly_change_log.json": {"as_of": as_of, **change_log},
        "distributional_state.json": {"as_of": as_of, "groups": distributional, "forecast_effect": "NONE"},
        "policy_interpretation.json": {"as_of": as_of, "claims": policy_claims, "forecast_effect": "NONE"},
    }
    for name, payload in outputs.items():
        write_json(PUBLIC_ROOT / name, payload)
        write_json(GENERATED_ROOT / name, payload)

    write_json(DATA_ROOT / "normalized" / "latest.json", {"as_of": as_of, "generated_at": now, "observations": observations, "forecast_effect": "NONE"})
    write_json(DATA_ROOT / "revisions" / "latest.json", {"as_of": as_of, "generated_at": now, "revisions": revisions, "forecast_effect": "NONE"})

    report = render_report(as_of, states, dashboard, contradictions, alerts, chain, composite, distributional, watch, change_log, electoral_links, political_composite)
    (PUBLIC_ROOT / "report.md").write_text(report + "\n", encoding="utf-8")
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    (GENERATED_ROOT / "report.md").write_text(report + "\n", encoding="utf-8")
    html = render_html(as_of, states, dashboard, contradictions, alerts, chain, composite)
    household_page = ROOT / "public" / "household" / "index.html"
    household_page.parent.mkdir(parents=True, exist_ok=True)
    household_page.write_text(html, encoding="utf-8")

    archive = ARCHIVE_ROOT / as_of
    archive.mkdir(parents=True, exist_ok=True)
    for name in ["household_state.json", "voter_state.json", "household_dashboard.json"]:
        write_json(archive / name.replace("household_dashboard", "dashboard"), outputs[name])
    (archive / "report.md").write_text(report + "\n", encoding="utf-8")

    update_main_source_status("AVAILABLE" if module_available else "DEGRADED", now, f"Governed household/voter sensor; {len(observations)} observations, {len(errors)} automated-source errors.")

    forecast_after = file_hash(FORECAST)
    if forecast_before != forecast_after:
        raise RuntimeError("Household/voter module changed forecast.json; governance boundary violated")
    if any(x.get("forecast_effect") not in {None, "NONE"} for x in observations):
        raise RuntimeError("Contextual observation attempted non-NONE forecast effect")

    print(f"Household/voter state built: {len(observations)} observations; {len(dashboard)} dashboard rows; forecast unchanged")


if __name__ == "__main__":
    main()
