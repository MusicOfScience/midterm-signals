#!/usr/bin/env python3
"""Build the governed US Household & Voter State module for MIDTERM SIGNALS.

The module is contextual analysis only. It MUST NOT mutate numerical House/Senate
forecast probabilities. Raw observations, derived indicators, analytical states,
political interpretation and election inference are kept distinct.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "household"
REF_ROOT = ROOT / "data" / "reference"
PUBLIC_ROOT = ROOT / "public" / "data" / "household"
GENERATED_ROOT = ROOT / "generated"
ARCHIVE_ROOT = ROOT / "archive"
FORECAST = ROOT / "public" / "data" / "forecast.json"
MAIN_SOURCE_STATUS = ROOT / "public" / "data" / "source-status.json"

BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
USER_AGENT = "MIDTERM-SIGNALS/1.0 (+https://github.com/MusicOfScience/midterm-signals)"

# A deliberately conservative automated core. Other high-quality sources are
# registered and ingested through governed manual/adapter observations rather
# than scraped from unstable pages or restricted services.
BLS_SERIES: dict[str, dict[str, Any]] = {
    "CUUR0000SA0": {"id": "cpi_all", "indicator": "Headline CPI (not seasonally adjusted)", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUSR0000SA0": {"id": "cpi_all_sa", "indicator": "Headline CPI (seasonally adjusted)", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi_sa"},
    "CUUR0000SA0L1E": {"id": "cpi_core", "indicator": "Core CPI (not seasonally adjusted)", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUSR0000SA0L1E": {"id": "cpi_core_sa", "indicator": "Core CPI (seasonally adjusted)", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi_sa"},
    "CUUR0000SAF1": {"id": "cpi_food", "indicator": "Food CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SAF11": {"id": "cpi_food_home", "indicator": "Food at home CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SETB01": {"id": "cpi_gasoline", "indicator": "Gasoline CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SEHF01": {"id": "cpi_electricity", "indicator": "Electricity CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SEHF02": {"id": "cpi_utility_gas", "indicator": "Utility gas CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SAH1": {"id": "cpi_shelter", "indicator": "Shelter CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SEHA": {"id": "cpi_rent", "indicator": "Rent of primary residence CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SEHC": {"id": "cpi_oer", "indicator": "Owners' equivalent rent CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SAM": {"id": "cpi_medical", "indicator": "Medical care CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SEMD01": {"id": "cpi_hospital", "indicator": "Hospital services CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SEME": {"id": "cpi_health_insurance", "indicator": "Health insurance CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi", "interpretation_note": "BLS health-insurance CPI uses an indirect retained-earnings method; do not read it as a household premium index."},
    "CUUR0000SETA01": {"id": "cpi_new_vehicles", "indicator": "New vehicles CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SETA02": {"id": "cpi_used_vehicles", "indicator": "Used cars and trucks CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SETE": {"id": "cpi_vehicle_insurance", "indicator": "Motor vehicle insurance CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CUUR0000SETD": {"id": "cpi_vehicle_repairs", "indicator": "Motor vehicle maintenance and repair CPI", "sensor": "affordability_pressure", "unit": "index", "kind": "cpi"},
    "CES0500000003": {"id": "ahe_all_private", "indicator": "Average hourly earnings, private", "sensor": "real_income_pressure", "unit": "USD/hour", "kind": "earnings"},
    "CES0500000008": {"id": "ahe_prod_nonsup", "indicator": "Average hourly earnings, production/nonsupervisory", "sensor": "real_income_pressure", "unit": "USD/hour", "kind": "earnings"},
    "CES0500000011": {"id": "awe_all_private", "indicator": "Average weekly earnings, private", "sensor": "real_income_pressure", "unit": "USD/week", "kind": "earnings"},
    "CES0500000013": {"id": "real_ahe_all_private", "indicator": "Real average hourly earnings, private", "sensor": "real_income_pressure", "unit": "1982-84 USD/hour", "kind": "real_earnings"},
    "CES0500000012": {"id": "real_awe_all_private", "indicator": "Real average weekly earnings, private", "sensor": "real_income_pressure", "unit": "1982-84 USD/week", "kind": "real_earnings"},
    "CES0000000001": {"id": "nonfarm_payrolls", "indicator": "Total nonfarm payroll employment", "sensor": "labour_market_security", "unit": "thousands", "kind": "level_change"},
    "LNS14000000": {"id": "unemployment_rate", "indicator": "Unemployment rate", "sensor": "labour_market_security", "unit": "percent", "kind": "rate"},
    "LNS13327709": {"id": "u6_rate", "indicator": "U-6 underemployment rate", "sensor": "labour_market_security", "unit": "percent", "kind": "rate"},
    "LNS11300000": {"id": "lfpr", "indicator": "Labour-force participation rate", "sensor": "labour_market_security", "unit": "percent", "kind": "rate"},
    "LNS12300000": {"id": "employment_population_ratio", "indicator": "Employment-population ratio", "sensor": "labour_market_security", "unit": "percent", "kind": "rate"},
    "JTS00000000JOL": {"id": "job_openings", "indicator": "Job openings", "sensor": "labour_market_security", "unit": "thousands", "kind": "level"},
    "JTS00000000HIL": {"id": "hires", "indicator": "Hires", "sensor": "labour_market_security", "unit": "thousands", "kind": "level"},
    "JTS00000000QUL": {"id": "quits", "indicator": "Quits", "sensor": "labour_market_security", "unit": "thousands", "kind": "level"},
    "JTS00000000LDL": {"id": "layoffs_discharges", "indicator": "Layoffs and discharges", "sensor": "labour_market_security", "unit": "thousands", "kind": "level"},
}

BLS_RELEASES = {
    "cpi": {"current_release": "2026-10-14", "current_reference": "2026-09", "next_release": "2026-11-10"},
    "cpi_sa": {"current_release": "2026-10-14", "current_reference": "2026-09", "next_release": "2026-11-10"},
    "real_earnings": {"current_release": "2026-10-14", "current_reference": "2026-09", "next_release": "2026-11-10"},
    "earnings": {"current_release": "2026-10-02", "current_reference": "2026-09", "next_release": "2026-11-06"},
    "level_change": {"current_release": "2026-10-02", "current_reference": "2026-09", "next_release": "2026-11-06"},
    "rate": {"current_release": "2026-10-02", "current_reference": "2026-09", "next_release": "2026-11-06"},
    "level": {"current_release": "2026-09-29", "current_reference": "2026-08", "next_release": "2026-11-03"},
}

STATE_LADDERS = {
    "affordability_pressure": ["LOW", "MODERATE", "ELEVATED", "HIGH", "ACUTE"],
    "real_income_pressure": ["STRONG REAL GAINS", "MODEST REAL GAINS", "FLAT", "MODEST REAL LOSS", "MATERIAL REAL LOSS"],
    "labour_market_security": ["TIGHT", "HEALTHY", "COOLING", "WEAK", "DETERIORATING RAPIDLY"],
    "household_cash_flow": ["COMFORTABLE", "TIGHTENING", "COMPRESSED", "STRESSED", "ACUTE"],
    "financial_buffer": ["ROBUST", "ADEQUATE", "THIN", "ERODING", "DEPLETED"],
    "credit_stress": ["NORMAL", "ELEVATED", "CONCENTRATED STRESS", "BROAD STRESS", "SYSTEMIC HOUSEHOLD DELEVERAGING"],
    "wealth_distribution": ["BROADLY SHARED", "UNEQUAL", "HIGHLY CONCENTRATED", "EXTREMELY CONCENTRATED"],
    "k_shaped_economy": ["BROADLY SHARED", "MILDLY BIFURCATED", "CLEARLY K-SHAPED", "SEVERELY K-SHAPED"],
    "current_conditions": ["STRONG", "ADEQUATE", "WEAK", "VERY WEAK", "CRISIS-LIKE"],
    "expectations": ["OPTIMISTIC", "NEUTRAL", "CAUTIOUS", "PESSIMISTIC", "DEEPLY PESSIMISTIC"],
    "economic_salience": ["LOW", "MODERATE", "HIGH", "DOMINANT"],
    "incumbent_attribution": ["LOW ATTRIBUTION", "MIXED", "NET NEGATIVE", "STRONGLY NEGATIVE"],
    "partisan_deflection": ["INTACT", "WEAKENING", "BREAKING", "BROKEN"],
    "independent_state": ["INCUMBENT-LEANING", "NEUTRAL", "DISCONTENTED / UNALIGNED", "OPPOSITION-LEANING", "STRONGLY ANTI-INCUMBENT"],
    "electoral_economic_pressure": ["LOW", "MODERATE", "ELEVATED", "HIGH", "ACUTE"],
    "sentiment_behaviour_divergence": ["ALIGNED POSITIVE", "ALIGNED NEGATIVE", "NEGATIVE SENTIMENT / RESILIENT SPENDING", "POSITIVE SENTIMENT / WEAK SPENDING", "MIXED / INDETERMINATE"],
    "essential_discretionary_pressure": ["DISCRETIONARY EXPANSION", "NORMAL", "SELECTIVE TRADE-DOWN", "BROAD RETRENCHMENT", "ESSENTIALS CROWDING OUT DISCRETIONARY SPENDING"],
    "national_personal_economy_gap": ["PERSONAL BETTER THAN NATIONAL", "ALIGNED", "PERSONAL WORSE THAN NATIONAL"],
}

LEAD_LAG = {
    "consumer_expectations": "LEADING", "large_purchase_intentions": "LEADING", "job_openings": "LEADING",
    "hires": "LEADING", "job_loss_expectations": "LEADING", "inflation_expectations": "LEADING",
    "partisan_attribution": "LEADING", "independent_issue_trust": "LEADING",
    "current_conditions": "COINCIDENT", "real_wages": "COINCIDENT", "gasoline_prices": "COINCIDENT",
    "current_financial_situation": "COINCIDENT", "retail_spending": "COINCIDENT", "cost_of_living_concern": "COINCIDENT",
    "unemployment_rate": "LAGGING", "delinquency": "LAGGING", "foreclosure": "LAGGING", "bankruptcy": "LAGGING",
    "annual_income": "LAGGING", "annual_poverty": "LAGGING",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_period(year: str | int, period: str) -> date | None:
    if not str(period).startswith("M") or str(period) == "M13":
        return None
    try:
        return date(int(year), int(str(period)[1:]), 1)
    except Exception:
        return None


def period_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def reference_date(value: Any) -> date | None:
    text = str(value or "")[:10]
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:7], fmt).date()
        except Exception:
            pass
    return None


def freshness(publication_date: str | None, reference_date: date | None, today: date) -> str:
    basis = None
    if publication_date:
        try:
            basis = date.fromisoformat(publication_date[:10])
        except Exception:
            basis = None
    if basis is None and reference_date is not None:
        # Conservative fallback when an adapter cannot expose release date.
        basis = date(reference_date.year, reference_date.month, 1)
    if basis is None:
        return "STALE"
    age = (today - basis).days
    if age <= 31:
        return "FRESH"
    if age <= 90:
        return "RECENT"
    if age <= 180:
        return "AGING"
    return "STALE"


def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return (new / old - 1.0) * 100.0


def annualised_3m(latest: float | None, three_months_prior: float | None) -> float | None:
    if latest is None or three_months_prior in (None, 0):
        return None
    return ((latest / three_months_prior) ** 4 - 1) * 100.0


def as_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_bls(start_year: int, end_year: int) -> dict:
    # The public BLS API has request-size limits. Chunk conservatively so adding
    # another sensor series cannot silently push production over the boundary.
    ids = list(BLS_SERIES)
    series: list[dict] = []
    messages: list[str] = []
    for offset in range(0, len(ids), 20):
        payload = json.dumps({"seriesid": ids[offset:offset + 20], "startyear": str(start_year), "endyear": str(end_year)}).encode("utf-8")
        req = urllib.request.Request(
            BLS_API,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
        parsed = json.loads(raw.decode("utf-8"))
        if parsed.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS API failed: {parsed.get('message')}")
        series.extend(parsed.get("Results", {}).get("series", []))
        messages.extend(parsed.get("message") or [])
    return {"status": "REQUEST_SUCCEEDED", "responseTime": None, "message": messages, "Results": {"series": series}}


def normalize_bls(payload: dict, retrieved_at: str, today: date) -> tuple[list[dict], dict[str, list[tuple[date, float]]]]:
    observations: list[dict] = []
    histories: dict[str, list[tuple[date, float]]] = {}
    for series in payload.get("Results", {}).get("series", []):
        series_id = series.get("seriesID")
        spec = BLS_SERIES.get(series_id)
        if not spec:
            continue
        points: list[tuple[date, float]] = []
        for item in series.get("data", []):
            d = parse_period(item.get("year"), item.get("period"))
            v = as_float(item.get("value"))
            if d is not None and v is not None:
                points.append((d, v))
        points.sort(key=lambda x: x[0])
        if not points:
            continue
        histories[spec["id"]] = points
        latest_date, latest = points[-1]
        prev = points[-2][1] if len(points) >= 2 else None
        prior_3m = points[-4][1] if len(points) >= 4 else None
        yago = next((v for d, v in points if d.year == latest_date.year - 1 and d.month == latest_date.month), None)
        jan = next((v for d, v in points if d.year == 2026 and d.month == 1), None)
        jan_2024 = next((v for d, v in points if d.year == 2024 and d.month == 1), None)
        jan_2020 = next((v for d, v in points if d.year == 2020 and d.month == 1), None)
        release = BLS_RELEASES.get(spec["kind"], {})
        ref_key = period_key(latest_date)
        pub = release.get("current_release") if ref_key == release.get("current_reference") else None
        next_release = release.get("next_release") if ref_key == release.get("current_reference") else None
        latest_change = (latest - prev) if prev is not None else None
        if spec["kind"] in {"cpi", "cpi_sa", "earnings", "real_earnings", "level"}:
            direction = pct_change(latest, prev)
        elif spec["kind"] == "level_change":
            direction = latest_change
        else:
            direction = latest_change
        observations.append({
            "id": f"bls.{spec['id']}",
            "indicator": spec["indicator"],
            "sensor": spec["sensor"],
            "source": "Bureau of Labor Statistics",
            "source_id": "bls",
            "source_type": "PRIMARY_MEASUREMENT",
            "tier": 1,
            "series_id": series_id,
            "data_reference_period": period_key(latest_date),
            "fieldwork_start": None,
            "fieldwork_end": None,
            "publication_date": pub,
            "retrieval_timestamp": retrieved_at,
            "geographic_scope": "United States",
            "population_sample": "BLS national published series; survey universe varies by series",
            "methodology_notes": "Official BLS public time-series API. Seasonal-adjustment status is encoded in the native series ID." + ((" " + spec["interpretation_note"]) if spec.get("interpretation_note") else ""),
            "freshness": freshness(pub, latest_date, today),
            "revision_status": "LATEST_AVAILABLE",
            "transformation_method": "Native level plus deterministic period comparisons",
            "confidence": "HIGH",
            "unit": spec["unit"],
            "latest": latest,
            "previous": prev,
            "january_2026": jan,
            "january_2024": jan_2024,
            "january_2020": jan_2020,
            "change_since_january_2020_pct": pct_change(latest, jan_2020),
            "twelve_months_ago": yago,
            "month_change": latest_change,
            "month_pct_change": pct_change(latest, prev),
            "yoy_pct_change": pct_change(latest, yago),
            "three_month_annualised_pct": annualised_3m(latest, prior_3m),
            "direction_value": direction,
            "lead_lag": LEAD_LAG.get(spec["id"]),
            "forecast_effect": "NONE",
            "next_expected_release": next_release,
        })
    return observations, histories


def load_manual_observations(today: date | None = None, retrieved_at: str | None = None) -> list[dict]:
    today = today or date.today()
    retrieved_at = retrieved_at or utc_now()
    manual_dir = DATA_ROOT / "manual"
    rows: list[dict] = []
    if not manual_dir.exists():
        return rows
    for path in sorted(manual_dir.glob("observations*.json")):
        value = read_json(path, {}) or {}
        candidates = value.get("observations") if isinstance(value, dict) else value
        if not isinstance(candidates, list):
            continue
        for row in candidates:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item.setdefault("forecast_effect", "NONE")
            item.setdefault("revision_status", "AS_PUBLISHED")
            item.setdefault("transformation_method", "NONE")
            item.setdefault("confidence", "MODERATE")
            item.setdefault("retrieval_timestamp", retrieved_at)
            item.setdefault("fieldwork_start", None)
            item.setdefault("fieldwork_end", None)
            item.setdefault("publication_date", None)
            item.setdefault("data_reference_period", None)
            item.setdefault("geographic_scope", "United States")
            item.setdefault("population_sample", None)
            item.setdefault("methodology_notes", None)
            item.setdefault("freshness", freshness(item.get("publication_date"), reference_date(item.get("data_reference_period")), today))
            rows.append(item)
    return rows


REQUIRED_OBSERVATION_FIELDS = (
    "id", "indicator", "sensor", "source", "source_type", "data_reference_period",
    "fieldwork_start", "fieldwork_end", "publication_date", "retrieval_timestamp",
    "geographic_scope", "population_sample", "methodology_notes", "freshness",
    "revision_status", "transformation_method", "confidence", "forecast_effect",
)

