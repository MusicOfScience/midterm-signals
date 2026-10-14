"""Distributional, dashboard, watchlist, revision and source-health outputs."""
from household_state_core import *
from household_state_classifiers import *
from household_state_composites import *

def build_distributional_state(observations: list[dict]) -> list[dict]:
    allowed = {"HIGH-INCOME / HIGH-ASSET", "MIDDLE-INCOME", "LOWER-INCOME", "HOMEOWNER", "RENTER", "UNDER-35", "55+", "REPUBLICAN", "DEMOCRAT", "INDEPENDENT"}
    groups: dict[str, list[dict]] = {}
    for row in observations:
        group = str(row.get("population_group") or "").upper()
        if group in allowed:
            groups.setdefault(group, []).append(row)
    out = []
    for group in sorted(groups):
        rows = groups[group]
        out.append({
            "group": group,
            "observations": [r.get("id") for r in rows],
            "latest_publication_date": max((r.get("publication_date") or "" for r in rows), default=None),
            "sample_notes": sorted({str(r.get("population_sample")) for r in rows if r.get("population_sample")}),
            "confidence": "MODERATE" if len({r.get("source_id") or r.get("source") for r in rows}) >= 2 else "LOW",
            "forecast_effect": "NONE",
        })
    return out


def build_watchlist(dashboard: list[dict]) -> list[dict]:
    rules = {
        "Headline CPI (not seasonally adjusted)": ("≥4.0% y/y or essentials accelerate sharply for two months", "Cost-of-living pressure and affordability salience"),
        "Real average hourly earnings, private": ("negative y/y for two consecutive months", "Direct purchasing-power squeeze"),
        "Total nonfarm payroll employment": ("3-month average payroll gain <50k with unemployment +0.3pp from trough", "Potential transition from cooling to weak labour security"),
        "Unemployment rate": ("+0.3pp from recent trough alongside weak payrolls", "Lagging confirmation of labour deterioration"),
        "Job openings": ("persistent broad decline in openings and hiring", "Leading signal for job mobility/re-employment security"),
        "Hires": ("persistent decline relative to year-ago levels", "Whether available jobs are converting into actual employment transitions"),
        "Quits": ("persistent decline relative to year-ago levels", "Worker confidence and ability to switch jobs"),
        "Gasoline CPI": ("renewed acceleration or broadening into utilities/transport", "Highly salient essential-price channel"),
    }
    out=[]
    for row in dashboard[:30]:
        trigger, why = rules.get(row.get("indicator"), ("material move sufficient to change its governed sensor classification", "Potential movement in the household-to-political transmission chain"))
        out.append({
            "indicator": row.get("indicator"), "current_state": row.get("state"), "trigger": trigger,
            "why_it_matters": why, "next_expected_release": row.get("next_expected_release"),
            "freshness": row.get("freshness"), "forecast_effect": "NONE",
        })
        if len(out) >= 15:
            break
    return out


def build_dashboard(observations: list[dict], states: dict[str, dict]) -> list[dict]:
    rows = []
    for x in observations:
        if x.get("latest") is None:
            continue
        latest = x.get("latest")
        prev = x.get("previous")
        direction = "UNCHANGED"
        if isinstance(latest, (int, float)) and isinstance(prev, (int, float)):
            direction = "UP" if latest > prev else "DOWN" if latest < prev else "UNCHANGED"
        rows.append({
            "indicator": x.get("indicator"), "latest": latest, "previous": prev, "january_2026": x.get("january_2026"),
            "twelve_month_comparison": x.get("yoy_pct_change"), "direction": direction,
            "state": states.get(x.get("sensor"), {}).get("state", "OBSERVATION"), "confidence": x.get("confidence"),
            "freshness": x.get("freshness"), "unit": x.get("unit"), "source": x.get("source"),
            "data_reference_period": x.get("data_reference_period"), "fieldwork_start": x.get("fieldwork_start"), "fieldwork_end": x.get("fieldwork_end"),
            "publication_date": x.get("publication_date"), "retrieval_timestamp": x.get("retrieval_timestamp"), "revision_status": x.get("revision_status"),
            "next_expected_release": x.get("next_expected_release"), "forecast_effect": "NONE",
        })
    return rows[:30]


def transmission(states: dict[str, dict], baseline: dict) -> list[dict]:
    order = [
        ("aggregate_wealth", "AGGREGATE WEALTH"), ("wealth_distribution", "WEALTH DISTRIBUTION"),
        ("affordability_pressure", "AFFORDABILITY PRESSURE"), ("real_income_pressure", "REAL INCOME"),
        ("household_cash_flow", "HOUSEHOLD CASH FLOW"), ("financial_buffer", "FINANCIAL BUFFER"),
        ("credit_stress", "CREDIT STRESS"), ("consumption", "CONSUMPTION"),
        ("labour_market_security", "LABOUR MARKET"), ("current_conditions", "CURRENT CONDITIONS"),
        ("expectations", "EXPECTATIONS"), ("incumbent_attribution", "INCUMBENT ATTRIBUTION"),
        ("partisan_deflection", "PARTISAN DEFLECTION"), ("electoral_economic_pressure", "ELECTORAL ECONOMIC PRESSURE"),
    ]
    out=[]
    for key,label in order:
        rec=states.get(key) or provisional_sensor(key, baseline)
        out.append({"sensor":key,"label":label,"state":rec.get("state"),"confidence":rec.get("confidence"),"state_status":rec.get("state_status"),"forecast_effect":"NONE"})
    return out


def monthly_change_log(states: dict[str, dict], previous_state: dict | None) -> dict:
    old = (previous_state or {}).get("states", {}) if previous_state else {}
    buckets = {"new_signals": [], "strengthened_signals": [], "weakened_signals": [], "reversed_signals": [], "unchanged_signals": []}
    for sensor, rec in states.items():
        cur = rec.get("state")
        before = old.get(sensor, {}).get("state") if isinstance(old.get(sensor), dict) else None
        item = {"sensor": sensor, "previous": before, "current": cur}
        if before is None:
            buckets["new_signals"].append(item)
        elif before == cur:
            buckets["unchanged_signals"].append(item)
        else:
            ladder = STATE_LADDERS.get(sensor)
            if ladder and before in ladder and cur in ladder:
                delta = ladder.index(cur) - ladder.index(before)
                (buckets["strengthened_signals"] if delta > 0 else buckets["weakened_signals"]).append(item)
            else:
                buckets["reversed_signals"].append(item)
    return buckets | {"forecast_effect": "NONE"}


def load_policy_claims() -> list[dict]:
    path = DATA_ROOT / "interpretation" / "policy_claims.json"
    payload = read_json(path, {"claims": []}) or {"claims": []}
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    valid_assessments = {"STRONGLY SUPPORTED", "PLAUSIBLE", "CONTESTED", "WEAKLY SUPPORTED", "NOT TESTABLE WITH CURRENT DATA"}
    required = {"institution", "claim", "underlying_data", "causal_mechanism", "counterevidence", "ideological_policy_assumption", "assessment", "evidence_strength"}
    out=[]
    for item in claims:
        if not isinstance(item, dict):
            continue
        missing = sorted(required - set(item))
        if missing:
            raise RuntimeError(f"Policy interpretation claim missing required fields: {', '.join(missing)}")
        if item.get("assessment") not in valid_assessments:
            raise RuntimeError(f"Invalid policy interpretation assessment: {item.get('assessment')!r}")
        row = dict(item)
        row["forecast_effect"] = "NONE"
        out.append(row)
    return out


def source_health(registry: dict, observations: list[dict], errors: dict[str, str], now: str) -> list[dict]:
    rows=[]
    by_source: dict[str, list[dict]] = {}
    for obs in observations:
        sid = str(obs.get("source_id") or "")
        if sid:
            by_source.setdefault(sid, []).append(obs)
    freshness_rank = {"FRESH": 0, "RECENT": 1, "AGING": 2, "STALE": 3}
    for src in registry.get("sources", []):
        sid=src.get("id")
        observed = by_source.get(str(sid), [])
        if sid in errors:
            state="FETCH_FAILED"
        elif observed:
            best = min((x.get("freshness", "STALE") for x in observed), key=lambda x: freshness_rank.get(x, 99))
            state="STALE" if best == "STALE" else "AVAILABLE"
        else:
            state=src.get("default_state", "MANUAL")
        rows.append({**src, "state": state, "checked_at": now, "error": errors.get(sid), "forecast_effect": "NONE"})
    return rows


def update_main_source_status(module_state: str, now: str, note: str) -> None:
    payload = read_json(MAIN_SOURCE_STATUS, {}) or {}
    sources = payload.get("sources") or []
    replacement = {
        "id": "household_voter_state", "label": "US Household & Voter State", "kind": "economic-political contextual sensor",
        "state": "current" if module_state == "AVAILABLE" else "degraded", "url": "/household/",
        "last_success": now if module_state == "AVAILABLE" else None, "last_observation": now[:10],
        "note": note + " Forecast effect NONE.",
    }
    for i, row in enumerate(sources):
        if row.get("id") == "household_voter_state":
            sources[i] = replacement
            break
    else:
        sources.append(replacement)
    payload["generated_at"] = now
    payload["sources"] = sources
    write_json(MAIN_SOURCE_STATUS, payload)
