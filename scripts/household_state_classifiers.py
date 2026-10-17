"""Validation and state classifiers for the governed household/voter sensor."""
from household_state_core import *

def validate_observations(observations: list[dict]) -> None:
    for row in observations:
        missing = [key for key in REQUIRED_OBSERVATION_FIELDS if key not in row]
        if missing:
            raise RuntimeError(f"Observation {row.get('id') or '<unknown>'} missing required metadata: {', '.join(missing)}")
        if not row.get("id") or not row.get("indicator") or not row.get("sensor") or not row.get("source") or not row.get("source_type"):
            raise RuntimeError(f"Observation {row.get('id') or '<unknown>'} has empty identity/source metadata")
        if row.get("forecast_effect") != "NONE":
            raise RuntimeError(f"Observation {row.get('id')} attempted forecast_effect={row.get('forecast_effect')!r}")
        if row.get("freshness") not in {"FRESH", "RECENT", "AGING", "STALE"}:
            raise RuntimeError(f"Observation {row.get('id')} has invalid freshness={row.get('freshness')!r}")


def latest_by_id(observations: Iterable[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in observations:
        key = str(row.get("id") or "")
        if key:
            result[key] = row
    return result


def classify_real_income(obs: dict[str, dict]) -> dict:
    row = obs.get("bls.real_ahe_all_private")
    yoy = row.get("yoy_pct_change") if row else None
    if yoy is None:
        return uncertain_state("real_income_pressure")
    if yoy >= 1.5:
        state = "STRONG REAL GAINS"
    elif yoy > 0.2:
        state = "MODEST REAL GAINS"
    elif yoy >= -0.2:
        state = "FLAT"
    elif yoy > -1.5:
        state = "MODEST REAL LOSS"
    else:
        state = "MATERIAL REAL LOSS"
    return state_record("real_income_pressure", state, "MODERATE", [row], "BLS real average hourly earnings y/y")


def classify_affordability(obs: dict[str, dict]) -> dict:
    headline = obs.get("bls.cpi_all")
    headline_sa = obs.get("bls.cpi_all_sa")
    core = obs.get("bls.cpi_core")
    essentials_ids = ["bls.cpi_food_home", "bls.cpi_gasoline", "bls.cpi_electricity", "bls.cpi_utility_gas", "bls.cpi_shelter", "bls.cpi_hospital"]
    essentials = [obs[x].get("yoy_pct_change") for x in essentials_ids if x in obs and obs[x].get("yoy_pct_change") is not None]
    hy = headline.get("yoy_pct_change") if headline else None
    hm = headline_sa.get("three_month_annualised_pct") if headline_sa else None
    essential_median = statistics.median(essentials) if len(essentials) >= 3 else None
    max_essential = max(essentials) if essentials else None
    if hy is None:
        return uncertain_state("affordability_pressure")
    if hy >= 5.0 or (essential_median is not None and essential_median >= 8.0):
        state = "ACUTE"
    elif hy >= 3.5 or (max_essential is not None and max_essential >= 10.0) or (essential_median is not None and essential_median >= 4.5) or (hm is not None and hm >= 5.0):
        state = "HIGH"
    elif hy >= 2.5 or (essential_median is not None and essential_median >= 3.0):
        state = "ELEVATED"
    elif hy >= 1.5:
        state = "MODERATE"
    else:
        state = "LOW"
    evidence = [r for r in [headline, headline_sa, core] + [obs.get(x) for x in essentials_ids] if r]
    result = state_record("affordability_pressure", state, "MODERATE", evidence, "Inflation momentum plus concentration in household necessities; price-level burden remains a separate field")
    result["inflation_momentum"] = {"headline_yoy": hy, "headline_3m_annualised": hm, "core_yoy": core.get("yoy_pct_change") if core else None, "essential_median_yoy": essential_median}
    result["price_level_burden"] = {
        "headline_cpi_change_since_january_2020_pct": headline.get("change_since_january_2020_pct") if headline else None,
        "classification": "NOT COLLAPSED INTO INFLATION MOMENTUM",
        "note": "The cumulative price-level increase is recorded separately from the current inflation rate."
    }
    return result


def classify_labour(obs: dict[str, dict], histories: dict[str, list[tuple[date, float]]]) -> tuple[dict, dict, dict]:
    payroll = obs.get("bls.nonfarm_payrolls")
    ur = obs.get("bls.unemployment_rate")
    payroll_hist = histories.get("nonfarm_payrolls", [])
    ur_hist = histories.get("unemployment_rate", [])
    payroll_changes = [payroll_hist[i][1] - payroll_hist[i-1][1] for i in range(1, len(payroll_hist))]
    three_avg = statistics.mean(payroll_changes[-3:]) if len(payroll_changes) >= 3 else None
    recent_ur = [v for _, v in ur_hist[-7:]]
    trough = min(recent_ur) if recent_ur else None
    rise = (ur.get("latest") - trough) if ur and trough is not None else None
    u = ur.get("latest") if ur else None
    if u is None or three_avg is None:
        base = uncertain_state("labour_market_security") | {"reason": "Overall labour-market classification requires both unemployment and a recent payroll-growth history; low unemployment alone is insufficient."}
    else:
        if three_avg < 0 and rise is not None and rise >= 0.5:
            state = "DETERIORATING RAPIDLY"
        elif three_avg < 50 and (rise is not None and rise >= 0.3):
            state = "WEAK"
        elif three_avg < 100 or (rise is not None and rise >= 0.2):
            state = "COOLING"
        elif u <= 4.2 and three_avg >= 100:
            state = "HEALTHY"
        else:
            state = "HEALTHY"
        base = state_record("labour_market_security", state, "MODERATE", [r for r in [payroll, ur, obs.get("bls.u6_rate"), obs.get("bls.lfpr"), obs.get("bls.employment_population_ratio")] if r], "Employment retention and job mobility are evaluated separately")
    base["three_month_payroll_average_thousands"] = three_avg
    base["unemployment_rise_from_recent_trough_pp"] = rise

    # Retention uses actual employment/unemployment; mobility requires openings,
    # hires/quits plus expectation surveys, so it is deliberately more cautious.
    if u is not None and u <= 4.5 and not (rise is not None and rise >= 0.4):
        retention_state = "HEALTHY" if three_avg is None or three_avg >= 50 else "COOLING"
    else:
        retention_state = "COOLING" if u is not None and u < 5.0 else "WEAK"
    retention = state_record("employment_retention_security", retention_state, "MODERATE", [r for r in [payroll, ur] if r], "Retention risk from payrolls and unemployment")

    j_open = obs.get("bls.job_openings")
    hires = obs.get("bls.hires")
    quits = obs.get("bls.quits")
    if not (j_open and hires and quits):
        mobility = {"sensor": "job_mobility_security", "state": "UNCERTAIN", "confidence": "LOW", "evidence": [], "reason": "JOLTS and/or expectation evidence incomplete", "forecast_effect": "NONE"}
    else:
        open_yoy = j_open.get("yoy_pct_change")
        hire_yoy = hires.get("yoy_pct_change")
        quit_yoy = quits.get("yoy_pct_change")
        vals = [v for v in [open_yoy, hire_yoy, quit_yoy] if v is not None]
        if len(vals) < 2:
            mobility = uncertain_state("job_mobility_security") | {"confidence": "LOW", "reason": "At least two comparable JOLTS year-on-year opportunity/turnover measures are required; low layoffs alone cannot establish healthy mobility."}
        else:
            mean_move = statistics.mean(vals)
            if mean_move <= -8:
                mstate = "WEAK"
            elif mean_move <= -2:
                mstate = "COOLING"
            else:
                mstate = "HEALTHY"
            mobility = state_record("job_mobility_security", mstate, "MODERATE", [j_open, hires, quits], "JOLTS opportunity/turnover measures; NY Fed job-loss/job-finding expectations should corroborate future high-confidence calls")
    return base, retention, mobility


def state_record(sensor: str, state: str, confidence: str, evidence: list[dict], reason: str, *, provisional: bool = False) -> dict:
    source_ids = sorted({str(e.get("source_id") or e.get("source") or "") for e in evidence if e})
    return {
        "sensor": sensor,
        "state": state,
        "confidence": confidence,
        "state_status": "PROVISIONAL" if provisional else "EVIDENCE_DERIVED",
        "independent_source_count": len([x for x in source_ids if x]),
        "evidence": [e.get("id") for e in evidence if e and e.get("id")],
        "reason": reason,
        "forecast_effect": "NONE",
    }


def uncertain_state(sensor: str) -> dict:
    return {"sensor": sensor, "state": "UNCERTAIN", "confidence": "UNCERTAIN", "state_status": "EVIDENCE_INSUFFICIENT", "independent_source_count": 0, "evidence": [], "forecast_effect": "NONE"}


def load_provisional_baseline() -> dict:
    return read_json(DATA_ROOT / "manual" / "provisional_baseline_2026-10-15.json", {}) or {}


def provisional_sensor(sensor: str, baseline: dict) -> dict:
    mapping = baseline.get("states", {})
    state = mapping.get(sensor)
    if state is None:
        return uncertain_state(sensor)
    return {
        "sensor": sensor,
        "state": state,
        "confidence": "LOW",
        "state_status": "PROVISIONAL_BASELINE_NOT_YET_TRIANGULATED",
        "independent_source_count": 0,
        "evidence": [],
        "reason": "15 October 2026 provisional baseline retained as a hypothesis until governed observations meet the module's triangulation rule.",
        "forecast_effect": "NONE",
    }


def survey_state_from_manual(sensor: str, observations: list[dict], baseline: dict, minimum_sources: int = 2) -> dict:
    relevant = [x for x in observations if x.get("sensor") == sensor and x.get("state_contribution")]
    if sensor == "partisan_deflection":
        relevant = [x for x in relevant if int(x.get("tier") or 99) <= 2 and x.get("source_type") in {"HIGH_QUALITY_PUBLIC_OPINION", "PRIMARY_MEASUREMENT"}]
    if not relevant:
        return provisional_sensor(sensor, baseline) | {"triangulation_met": False}

    # Reduce repeated observations from the same source to its latest admitted
    # state contribution so one prolific pollster cannot manufacture triangulation.
    latest_per_source: dict[str, dict] = {}
    for row in sorted(relevant, key=lambda x: (x.get("publication_date") or "", x.get("data_reference_period") or "", x.get("id") or "")):
        source = str(row.get("source_id") or row.get("source") or "")
        if source:
            latest_per_source[source] = row
    source_rows = list(latest_per_source.values())
    sources = set(latest_per_source)
    counts: dict[str, int] = {}
    for row in source_rows:
        state = str(row.get("state_contribution"))
        counts[state] = counts.get(state, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    candidate, support = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0

    if len(sources) >= minimum_sources and support == second:
        return uncertain_state(sensor) | {
            "confidence": "LOW", "triangulation_met": False,
            "evidence": [r.get("id") for r in source_rows if r.get("id")],
            "independent_source_count": len(sources),
            "reason": "Independent high-quality sources disagree on the governed state; the module preserves the contradiction rather than forcing a consensus.",
        }

    if sensor == "partisan_deflection" and candidate in {"BREAKING", "BROKEN"} and len(sources) < 2:
        return provisional_sensor(sensor, baseline) | {
            "triangulation_met": False,
            "reason": "BREAKING/BROKEN requires at least two independent high-quality survey sources (or an explicitly registered longitudinal-plus-cross-sectional design).",
        }

    confidence = "HIGH" if len(sources) >= minimum_sources and support >= minimum_sources else "MODERATE"
    return state_record(sensor, candidate, confidence, source_rows, "Governed manual/panel observations with source-level de-duplication", provisional=False) | {
        "triangulation_met": len(sources) >= minimum_sources and support >= minimum_sources,
        "state_vote": counts,
    }


def k_shaped_state_from_manual(observations: list[dict], baseline: dict) -> dict:
    relevant = [x for x in observations if x.get("sensor") == "k_shaped_economy" and x.get("state_contribution") and x.get("domain")]
    domains = {str(x.get("domain")) for x in relevant}
    if len(domains) < 2:
        return provisional_sensor("k_shaped_economy", baseline) | {
            "triangulation_met": False, "independent_domains": sorted(domains),
            "reason": "A K-shaped state requires evidence from at least two independent domains (for example spending plus credit, or wealth plus sentiment).",
        }
    result = survey_state_from_manual("k_shaped_economy", relevant, baseline, minimum_sources=1)
    result["independent_domains"] = sorted(domains)
    result["triangulation_met"] = True
    return result


def detect_revisions(current: list[dict], prior: dict | None) -> list[dict]:
    if not prior:
        return []
    previous = {x.get("id"): x for x in prior.get("observations", []) if isinstance(x, dict)}
    revisions = []
    for row in current:
        old = previous.get(row.get("id"))
        if not old or old.get("data_reference_period") != row.get("data_reference_period"):
            continue
        ov, nv = old.get("latest"), row.get("latest")
        if isinstance(ov, (int, float)) and isinstance(nv, (int, float)) and not math.isclose(float(ov), float(nv), rel_tol=0, abs_tol=1e-12):
            revisions.append({
                "indicator": row.get("indicator"), "id": row.get("id"), "data_reference_period": row.get("data_reference_period"),
                "initial_value": ov, "latest_revised_value": nv, "revision_magnitude": nv - ov,
                "source": row.get("source"), "forecast_effect": "NONE",
            })
    return revisions

