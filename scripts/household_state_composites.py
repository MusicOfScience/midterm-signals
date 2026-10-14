"""Contradiction, alert, composite and electoral-transmission logic."""
from household_state_core import *
from household_state_classifiers import *

def contradiction_engine(states: dict[str, dict], obs: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    def add(name: str, observation: str, mechanism: str, evidence: list[str], confidence: str, relevance: str) -> None:
        out.append({"contradiction": name, "observation": observation, "mechanism": mechanism, "evidence": evidence, "confidence": confidence, "political_relevance": relevance, "forecast_effect": "NONE"})

    aff = states.get("affordability_pressure", {}).get("state")
    real = states.get("real_income_pressure", {}).get("state")
    labour = states.get("labour_market_security", {}).get("state")
    mobility = states.get("job_mobility_security", {}).get("state")
    if aff in {"HIGH", "ACUTE"} and obs.get("bls.cpi_core") and (obs["bls.cpi_core"].get("yoy_pct_change") or 99) < 3.0:
        add("CORE INFLATION MODERATE / ESSENTIAL PRESSURE HIGH", "Core CPI is comparatively contained while selected household necessities are rising faster.", "Households experience budget weights and salient prices, not only the core aggregate.", ["bls.cpi_core", "bls.cpi_gasoline", "bls.cpi_electricity", "bls.cpi_hospital"], "HIGH", "Can sustain cost-of-living dissatisfaction even when core inflation looks closer to target.")
    if labour in {"HEALTHY", "COOLING"} and mobility in {"COOLING", "WEAK"}:
        add("EMPLOYMENT RETENTION / MOBILITY GAP", "Job retention remains materially better than job-switching/re-employment conditions.", "Low layoffs can coexist with fewer openings, hires and quits.", ["bls.nonfarm_payrolls", "bls.unemployment_rate", "bls.job_openings", "bls.hires", "bls.quits"], "MODERATE", "People may feel trapped in existing jobs before unemployment rises sharply.")
    if aff in {"HIGH", "ACUTE"} and real in {"MODEST REAL LOSS", "MATERIAL REAL LOSS"}:
        add("AFFORDABILITY / REAL-INCOME SQUEEZE", "Prices are rising quickly enough to erode real hourly purchasing power.", "Nominal wage growth is failing to offset the current price impulse.", ["bls.cpi_all", "bls.real_ahe_all_private"], "HIGH", "A direct lived-economy channel with high potential electoral salience.")
    return out[:8]


def alert_engine(states: dict[str, dict], obs: dict[str, dict], histories: dict[str, list[tuple[date, float]]]) -> list[dict]:
    alerts: list[dict] = []
    headline = obs.get("bls.cpi_all", {}).get("yoy_pct_change")
    if headline is not None and headline >= 4.0:
        alerts.append({"alert": "AFFORDABILITY ALERT", "triggered": True, "basis": f"Headline CPI {headline:.1f}% y/y ≥ 4.0%", "forecast_effect": "NONE"})
    real = obs.get("bls.real_ahe_all_private", {}).get("yoy_pct_change")
    real_hist = histories.get("real_ahe_all_private", [])
    if real is not None and real < 0 and len(real_hist) >= 13:
        # Calculate previous month's y/y from level history when possible.
        prev_d, prev_v = real_hist[-2]
        prev_yago = next((v for d, v in real_hist if d.year == prev_d.year - 1 and d.month == prev_d.month), None)
        prev_yoy = pct_change(prev_v, prev_yago)
        if prev_yoy is not None and prev_yoy < 0:
            alerts.append({"alert": "REAL-INCOME ALERT", "triggered": True, "basis": f"Real hourly earnings negative y/y for two consecutive months ({prev_yoy:.1f}%, {real:.1f}%)", "forecast_effect": "NONE"})
    payroll_hist = histories.get("nonfarm_payrolls", [])
    changes = [payroll_hist[i][1] - payroll_hist[i-1][1] for i in range(1, len(payroll_hist))]
    pavg = statistics.mean(changes[-3:]) if len(changes) >= 3 else None
    ur_hist = histories.get("unemployment_rate", [])
    ur_latest = ur_hist[-1][1] if ur_hist else None
    trough = min([v for _, v in ur_hist[-7:]], default=None)
    rise = ur_latest - trough if ur_latest is not None and trough is not None else None
    if pavg is not None and pavg < 50 and rise is not None and rise >= 0.3:
        alerts.append({"alert": "LABOUR ALERT", "triggered": True, "basis": f"3m payroll average {pavg:.0f}k < 50k and unemployment +{rise:.1f}pp from recent trough", "forecast_effect": "NONE"})
    electoral_parts = [states.get("economic_salience", {}), states.get("incumbent_attribution", {}), states.get("partisan_deflection", {})]
    if all(x.get("state_status") == "EVIDENCE_DERIVED" for x in electoral_parts) and states.get("partisan_deflection", {}).get("state") in {"BREAKING", "BROKEN"} and states.get("economic_salience", {}).get("state") in {"HIGH", "DOMINANT"} and states.get("incumbent_attribution", {}).get("state") in {"NET NEGATIVE", "STRONGLY NEGATIVE"}:
        alerts.append({"alert": "ELECTORAL TRANSMISSION ALERT", "triggered": True, "basis": "Economic salience high + incumbent attribution negative + governing-party deflection BREAKING/BROKEN, with all three states evidence-derived", "forecast_effect": "NONE"})
    return alerts


def stress_score(states: dict[str, dict]) -> dict:
    weights = {"affordability_pressure": 25, "real_income_pressure": 20, "labour_market_security": 15, "household_cash_flow": 15, "financial_buffer": 10, "credit_stress": 10, "current_conditions": 5}
    scales = {
        "affordability_pressure": STATE_LADDERS["affordability_pressure"],
        "real_income_pressure": STATE_LADDERS["real_income_pressure"],
        "labour_market_security": STATE_LADDERS["labour_market_security"],
        "household_cash_flow": STATE_LADDERS["household_cash_flow"],
        "financial_buffer": STATE_LADDERS["financial_buffer"],
        "credit_stress": STATE_LADDERS["credit_stress"],
        "current_conditions": STATE_LADDERS["current_conditions"],
    }
    score = 0.0
    used = 0.0
    components = {}
    for sensor, weight in weights.items():
        state = states.get(sensor, {}).get("state")
        ladder = scales[sensor]
        if state not in ladder:
            components[sensor] = None
            continue
        norm = ladder.index(state) / max(1, len(ladder) - 1) * 100
        components[sensor] = round(norm, 2)
        score += norm * weight
        used += weight
    final = score / used if used else None
    if final is None:
        label = "UNCERTAIN"
    elif final <= 20:
        label = "LOW"
    elif final <= 40:
        label = "MODERATE"
    elif final <= 60:
        label = "ELEVATED"
    elif final <= 80:
        label = "HIGH"
    else:
        label = "ACUTE"
    evidence_used = sum(weight for sensor, weight in weights.items() if components.get(sensor) is not None and states.get(sensor, {}).get("state_status") == "EVIDENCE_DERIVED")
    evidence_ready = evidence_used >= 60
    return {
        "score": round(final, 1) if final is not None and evidence_ready else None,
        "state": label if evidence_ready else "UNCERTAIN",
        "provisional_score": round(final, 1) if final is not None and not evidence_ready else None,
        "provisional_state": label if final is not None and not evidence_ready else None,
        "classification_coverage_pct": used, "evidence_coverage_pct": evidence_used,
        "status": "EVIDENCE_DERIVED" if evidence_ready else "PROVISIONAL_OR_PARTIAL",
        "components": components, "descriptive_only": True, "forecast_effect": "NONE"
    }


def political_pressure_score(states: dict[str, dict], household_stress: dict) -> dict:
    weights = {"economic_salience": 25, "incumbent_attribution": 25, "partisan_deflection": 20, "independent_state": 15, "household_stress": 15}
    ladders = {
        "economic_salience": STATE_LADDERS["economic_salience"],
        "incumbent_attribution": STATE_LADDERS["incumbent_attribution"],
        "partisan_deflection": STATE_LADDERS["partisan_deflection"],
        "independent_state": STATE_LADDERS["independent_state"],
    }
    total = 0.0
    used = 0.0
    evidence_used = 0.0
    components: dict[str, float | None] = {}
    for sensor, weight in weights.items():
        if sensor == "household_stress":
            value = household_stress.get("score")
            if isinstance(value, (int, float)):
                components[sensor] = float(value)
                total += float(value) * weight
                used += weight
                evidence_used += weight * (float(household_stress.get("evidence_coverage_pct", 0)) / 100.0)
            else:
                components[sensor] = None
            continue
        rec = states.get(sensor, {})
        state = rec.get("state")
        ladder = ladders[sensor]
        if state not in ladder:
            components[sensor] = None
            continue
        value = ladder.index(state) / max(1, len(ladder) - 1) * 100
        components[sensor] = round(value, 2)
        total += value * weight
        used += weight
        if rec.get("state_status") == "EVIDENCE_DERIVED":
            evidence_used += weight
    score = total / used if used else None
    if score is None:
        state = "UNCERTAIN"
    elif score <= 20:
        state = "LOW"
    elif score <= 40:
        state = "MODERATE"
    elif score <= 60:
        state = "ELEVATED"
    elif score <= 80:
        state = "HIGH"
    else:
        state = "ACUTE"
    evidence_pct = round(evidence_used / sum(weights.values()) * 100, 1)
    evidence_ready = evidence_pct >= 60
    return {
        "score": round(score, 1) if score is not None and evidence_ready else None,
        "state": state if evidence_ready else "UNCERTAIN",
        "provisional_score": round(score, 1) if score is not None and not evidence_ready else None,
        "provisional_state": state if score is not None and not evidence_ready else None,
        "classification_coverage_pct": round(used / sum(weights.values()) * 100, 1),
        "evidence_coverage_pct": evidence_pct,
        "status": "EVIDENCE_DERIVED" if evidence_ready else "PROVISIONAL_OR_PARTIAL",
        "components": components,
        "descriptive_only": True,
        "forecast_effect": "NONE",
    }


def electoral_transmission(states: dict[str, dict]) -> dict:
    links = [
        ("economic_experience", ["affordability_pressure", "real_income_pressure", "household_cash_flow"]),
        ("salience", ["economic_salience"]),
        ("attribution", ["incumbent_attribution"]),
        ("partisan_penetration", ["partisan_deflection"]),
        ("vote_intention", ["vote_intention_pressure", "independent_state"]),
    ]
    output = []
    for label, sensors in links:
        recs = [states.get(k, {}) for k in sensors]
        derived = [r for r in recs if r.get("state_status") == "EVIDENCE_DERIVED"]
        if not derived:
            level = "INACTIVE" if any(r.get("state_status") == "EVIDENCE_INSUFFICIENT" for r in recs) else "WEAK"
            status = "PROVISIONAL_OR_INSUFFICIENT"
        else:
            # The link-strength label is about evidence that transmission is occurring,
            # not about whether the underlying economic state is good or bad.
            confidence = {r.get("confidence") for r in derived}
            level = "STRONG" if len(derived) == len(recs) and "HIGH" in confidence else "ACTIVE"
            status = "EVIDENCE_DERIVED"
        output.append({"link": label, "state": level, "status": status, "sensors": sensors, "forecast_effect": "NONE"})
    return {"links": output, "overall": states.get("electoral_economic_pressure", uncertain_state("electoral_economic_pressure")), "forecast_effect": "NONE"}
