#!/usr/bin/env python3
"""Enrich the published forecast with non-model external/contextual data.

This layer runs *after* the numerical forecast has been built. It may attach
third-party ratings, FEC finance summaries and structured campaign signals, but
it is forbidden from changing any MIDTERM SIGNALS probability, expected margin,
seat distribution or chamber-control output.

Source policy:
- Inside Elections: use the public JSON endpoints linked as "API" from its
  ratings pages. Preserve native rating labels; never translate them into fake
  probabilities.
- FEC: use official public bulk files; no API key is required.
- Cook / Silver: do not scrape or bypass licensed/subscriber access.
- Sabato / DDHQ: keep explicit manual/link boundaries until a redistribution-
  safe machine feed is configured.
- Campaign signals are structured facts derived from permitted quantitative
  inputs and the adapters above. Qualitative items default to model effect NONE.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public" / "data"
FORECAST = DATA / "forecast.json"
STATUS = DATA / "status.json"
SOURCE_STATUS = DATA / "source-status.json"
SIGNALS = DATA / "signals.json"
EXTERNAL = DATA / "external-forecasters.json"
FEC = DATA / "fec.json"
RUN_REPORT = DATA / "run-report.json"

USER_AGENT = "MIDTERM-SIGNALS/1.0 (+https://github.com/MusicOfScience/midterm-signals)"
IE_URLS = {
    "house": "https://insideelections.com/wp-content/themes/inside-elections/cache/ratings_latest_house_year=2026_district=all_clean.json",
    "senate": "https://insideelections.com/wp-content/themes/inside-elections/cache/ratings_latest_senate_year=2026_district=all_clean.json",
}
IE_PAGE_URLS = {
    "house": "https://insideelections.com/ratings/house/",
    "senate": "https://insideelections.com/ratings/senate/",
}
FEC_BULK_URL = "https://www.fec.gov/files/bulk-downloads/2026/webl26.zip"
FEC_CSV_FALLBACK = "https://www.fec.gov/files/bulk-downloads/2026/candidate_summary_2026.csv"
FEC_HOME = "https://www.fec.gov/data/"

FEC_FIELDS = [
    "CAND_ID", "CAND_NAME", "CAND_ICI", "PTY_CD", "CAND_PTY_AFFILIATION",
    "TTL_RECEIPTS", "TRANS_FROM_AUTH", "TTL_DISB", "TRANS_TO_AUTH", "COH_BOP",
    "COH_COP", "CAND_CONTRIB", "CAND_LOANS", "OTHER_LOANS", "CAND_LOAN_REPAY",
    "OTHER_LOAN_REPAY", "DEBTS_OWED_BY", "TTL_INDIV_CONTRIB", "CAND_OFFICE_ST",
    "CAND_OFFICE_DISTRICT", "SPEC_ELECTION", "PRIM_ELECTION", "RUN_ELECTION",
    "GEN_ELECTION", "GEN_ELECTION_PRECENT", "OTHER_POL_CMTE_CONTRIB",
    "POL_PTY_CONTRIB", "CVG_END_DT", "INDIV_REFUNDS", "CMTE_REFUNDS",
]

FORECAST_INVARIANT_KEYS = (
    "summary", "nowcast", "election_day_forecast", "tipping_point_house",
    "senate_battlegrounds", "national_environment",
)
RACE_NUMERIC_KEYS = (
    "dem_probability", "rep_probability", "forecast_margin_d_minus_r",
    "dem_two_party_vote", "rep_two_party_vote", "rating", "prior_margin",
    "model_sigma", "poll_average_margin", "poll_weight", "poll_count",
)


def fetch_bytes(url: str, timeout: int = 35) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except Exception:
            pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            pass
    return None


def clean_state(value: Any) -> str:
    return str(value or "").strip().upper()


def canonical_house_code(state: str, district: Any) -> str | None:
    state = clean_state(state)
    d = str(district or "").strip().upper()
    if not state:
        m = re.match(r"^([A-Z]{2})[- ](AL|\d{1,2})$", d)
        if m:
            state, d = m.group(1), m.group(2)
    elif re.match(r"^[A-Z]{2}[- ]", d):
        m = re.match(r"^([A-Z]{2})[- ](AL|\d{1,2})$", d)
        if m:
            state, d = m.group(1), m.group(2)
    if not state:
        return None
    if d in {"AL", "AT-LARGE", "00", "0"}:
        # The production race universe uses AK-01 and other single-district
        # states as 01 rather than AL, so try 01 first when mapping below.
        return f"{state}-01"
    try:
        return f"{state}-{int(d):02d}"
    except Exception:
        return None


def normalise_rating_race(item: dict, chamber: str, modeled: list[dict]) -> str | None:
    if chamber == "senate":
        state = clean_state(item.get("state") or item.get("district"))
        candidates = [r for r in modeled if r.get("race_type") == "senate" and clean_state(r.get("state")) == state]
        return candidates[0]["race_code"] if len(candidates) == 1 else None

    raw_district = str(item.get("district") or "").strip().upper()
    state = clean_state(item.get("state"))
    code = canonical_house_code(state, raw_district)
    by_code = {str(r.get("race_code", "")).upper(): r for r in modeled if r.get("race_type") == "house"}
    if code and code in by_code:
        return by_code[code]["race_code"]
    if raw_district in by_code:
        return by_code[raw_district]["race_code"]
    # A public feed may label a one-district state as AL while this project uses 01.
    if state:
        one = [r for r in modeled if r.get("race_type") == "house" and clean_state(r.get("state")) == state]
        if len(one) == 1:
            return one[0]["race_code"]
    return None


def source_age_state(last_updated: date | None, today: date, current_days: int = 14, stale_days: int = 45) -> str:
    if not last_updated:
        return "unavailable"
    age = max(0, (today - last_updated).days)
    return "current" if age <= current_days else "stale" if age <= stale_days else "unavailable"


def fetch_inside_elections(modeled: list[dict], today: date, previous: dict | None) -> tuple[dict, dict[str, dict]]:
    previous = previous or {}
    records: dict[str, dict] = {}
    source_errors: list[str] = []
    last_updates: list[date] = []
    fetched_chambers: list[str] = []

    for chamber, url in IE_URLS.items():
        try:
            payload = json.loads(fetch_bytes(url).decode("utf-8-sig"))
            fetched_chambers.append(chamber)
            top_date = parse_date(payload.get("last_updated") or payload.get("generated_at"))
            if top_date:
                last_updates.append(top_date)
            for item in payload.get("ratings", []):
                race_code = normalise_rating_race(item, chamber, modeled)
                if not race_code:
                    continue
                rating = str(item.get("rating") or "").strip()
                if not rating:
                    continue
                rec_date = parse_date(item.get("date")) or top_date
                if rec_date:
                    last_updates.append(rec_date)
                records[race_code] = {
                    "rating": rating,
                    "state": "current",
                    "source": IE_PAGE_URLS[chamber],
                    "source_api": url,
                    "updated_at": rec_date.isoformat() if rec_date else None,
                    "shift": item.get("shift") or None,
                    "previous_rating": item.get("previous_rating") or None,
                    "open": bool(item.get("open")) if item.get("open") is not None else None,
                    "special": bool(item.get("special")) if item.get("special") is not None else None,
                    "native_scale": True,
                }
        except Exception as exc:
            source_errors.append(f"{chamber}: {type(exc).__name__}")

    if not records:
        cached = (previous.get("race_ratings") or {}) if isinstance(previous, dict) else {}
        if cached:
            records = cached
            for rec in records.values():
                rec["state"] = "stale"
            last = parse_date(previous.get("last_updated"))
            source = {
                "name": "Inside Elections",
                "id": "inside_elections",
                "state": "stale",
                "mode": "last-known-good public API",
                "url": IE_PAGE_URLS["house"],
                "last_updated": last.isoformat() if last else previous.get("last_updated"),
                "ratings_count": len(records),
                "note": "Live public API retrieval failed; retaining the last-known-good ratings snapshot without affecting MIDTERM SIGNALS probabilities.",
                "errors": source_errors,
            }
            return source, records

    latest = max(last_updates) if last_updates else today
    state = source_age_state(latest, today)
    for rec in records.values():
        rec["state"] = state
    source = {
        "name": "Inside Elections",
        "id": "inside_elections",
        "state": state,
        "mode": "public API",
        "url": IE_PAGE_URLS["house"],
        "api_urls": list(IE_URLS.values()),
        "last_updated": latest.isoformat(),
        "ratings_count": len(records),
        "chambers": fetched_chambers,
        "note": "Native public ratings imported from the API links exposed on Inside Elections ratings pages; ratings remain external and never alter MIDTERM SIGNALS probabilities.",
    }
    if source_errors:
        source["errors"] = source_errors
    return source, records


def float_or_none(value: Any) -> float | None:
    try:
        text = str(value or "").replace(",", "").strip()
        return float(text) if text else None
    except Exception:
        return None


def normalise_fec_row(row: dict) -> dict:
    # Candidate-summary CSVs have varied header capitalisation over time.
    canon = {re.sub(r"[^A-Z0-9]", "", str(k).upper()): v for k, v in row.items()}
    def pick(*names: str) -> Any:
        for name in names:
            key = re.sub(r"[^A-Z0-9]", "", name.upper())
            if key in canon and canon[key] not in (None, ""):
                return canon[key]
        return None
    return {
        "CAND_ID": pick("CAND_ID", "Cand_Id"),
        "CAND_NAME": pick("CAND_NAME", "Cand_Name"),
        "CAND_PTY_AFFILIATION": pick("CAND_PTY_AFFILIATION", "Cand_Party_Affiliation", "Cand_Party"),
        "TTL_RECEIPTS": pick("TTL_RECEIPTS", "Total_Receipts"),
        "TTL_DISB": pick("TTL_DISB", "Total_Disb", "Total_Disbursements"),
        "COH_COP": pick("COH_COP", "Cash_On_Hand_COP", "Cash_On_Hand"),
        "DEBTS_OWED_BY": pick("DEBTS_OWED_BY", "Debts_Owed_By"),
        "CAND_OFFICE_ST": pick("CAND_OFFICE_ST", "Cand_Office_St"),
        "CAND_OFFICE_DISTRICT": pick("CAND_OFFICE_DISTRICT", "Cand_Office_Dist", "Cand_Office_District"),
        "CVG_END_DT": pick("CVG_END_DT", "Coverage_End_Date", "Coverage_Through"),
    }


def fetch_fec_rows() -> tuple[list[dict], str]:
    # Prefer the official, documented House/Senate current-campaign bulk file.
    try:
        raw = fetch_bytes(FEC_BULK_URL, timeout=45)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if not names:
                raise RuntimeError("empty FEC bulk archive")
            text = zf.read(names[0]).decode("utf-8-sig", errors="replace")
        rows = []
        for values in csv.reader(io.StringIO(text), delimiter="|"):
            if not values:
                continue
            padded = values + [""] * max(0, len(FEC_FIELDS) - len(values))
            rows.append(dict(zip(FEC_FIELDS, padded[: len(FEC_FIELDS)])))
        if rows:
            return rows, FEC_BULK_URL
    except Exception:
        pass

    raw = fetch_bytes(FEC_CSV_FALLBACK, timeout=45)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))
    rows = [normalise_fec_row(r) for r in reader]
    if not rows:
        raise RuntimeError("official FEC candidate summary returned no rows")
    return rows, FEC_CSV_FALLBACK


def name_tokens(value: str | None) -> list[str]:
    text = re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper())
    suffix = {"JR", "SR", "II", "III", "IV", "V", "DR", "MR", "MS", "MRS"}
    return [x for x in text.split() if x and x not in suffix]


def surname_token(value: str | None) -> str:
    tokens = name_tokens(value)
    return tokens[-1] if tokens else ""


def fec_surname(value: str | None) -> str:
    text = str(value or "")
    before_comma = text.split(",", 1)[0]
    tokens = name_tokens(before_comma)
    return tokens[-1] if tokens else surname_token(text)


def party_matches(side: str, fec_party: str | None) -> bool:
    party = clean_state(fec_party)
    if side == "D":
        return party.startswith("DEM") or party in {"DFL", "D"}
    if side == "R":
        return party.startswith("REP") or party == "R"
    return False


def candidate_match_score(model_name: str, fec_name: str) -> float:
    mt = name_tokens(model_name)
    ft = name_tokens(fec_name)
    if not mt or not ft:
        return 0.0
    if surname_token(model_name) != fec_surname(fec_name):
        return 0.0
    shared = len(set(mt) & set(ft))
    base = 0.65
    if shared >= 2:
        base += 0.25
    if mt[0] in ft or any(t.startswith(mt[0][:3]) or mt[0].startswith(t[:3]) for t in ft if len(t) >= 3):
        base += 0.10
    return min(1.0, base)


def fec_race_filter(row: dict, race: dict, side: str) -> bool:
    state = clean_state(row.get("CAND_OFFICE_ST"))
    if state != clean_state(race.get("state")):
        return False
    cid = str(row.get("CAND_ID") or "").upper()
    if race.get("race_type") == "senate":
        if cid and not cid.startswith("S"):
            return False
    else:
        if cid and not cid.startswith("H"):
            return False
        expected = str(race.get("district") or "").strip().upper()
        actual = str(row.get("CAND_OFFICE_DISTRICT") or "").strip().upper()
        try:
            expected = f"{int(expected):02d}"
        except Exception:
            expected = "00" if expected in {"AL", "AT-LARGE"} else expected
        try:
            actual = f"{int(actual):02d}"
        except Exception:
            actual = "00" if actual in {"AL", "AT-LARGE"} else actual
        # Single-district states sometimes use 00 in FEC data and 01 here.
        if actual != expected and not ({actual, expected} == {"00", "01"}):
            return False
    return party_matches(side, row.get("CAND_PTY_AFFILIATION"))


def best_fec_match(rows: list[dict], race: dict, side: str, name: str | None) -> dict | None:
    if not name:
        return None
    scored = []
    for row in rows:
        if not fec_race_filter(row, race, side):
            continue
        score = candidate_match_score(name, str(row.get("CAND_NAME") or ""))
        if score >= 0.65:
            scored.append((score, parse_date(row.get("CVG_END_DT")) or date(1900, 1, 1), row))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1], float_or_none(x[2].get("TTL_RECEIPTS")) or 0), reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[0][2].get("CAND_ID") != scored[1][2].get("CAND_ID"):
        # Ambiguous surname/name match: preserve absence rather than guess.
        return None
    return scored[0][2]


def fec_public_record(race: dict, side: str, model_name: str, row: dict, source_url: str) -> dict:
    coverage = parse_date(row.get("CVG_END_DT"))
    cid = str(row.get("CAND_ID") or "").strip() or None
    return {
        "race_code": race.get("race_code"),
        "candidate": model_name,
        "party": side,
        "fec_candidate_id": cid,
        "fec_name": row.get("CAND_NAME") or None,
        "receipts": float_or_none(row.get("TTL_RECEIPTS")),
        "disbursements": float_or_none(row.get("TTL_DISB")),
        "cash_on_hand": float_or_none(row.get("COH_COP")),
        "debts_owed_by": float_or_none(row.get("DEBTS_OWED_BY")),
        "coverage_through": coverage.isoformat() if coverage else None,
        "source": f"https://www.fec.gov/data/candidate/{cid}/?cycle=2026&election_full=true" if cid else FEC_HOME,
        "bulk_source": source_url,
    }


def attach_fec(modeled: list[dict], today: date, previous: dict | None) -> tuple[dict, list[dict]]:
    previous = previous or {}
    try:
        rows, source_url = fetch_fec_rows()
        records: list[dict] = []
        latest: date | None = None
        for race in modeled:
            attached = []
            for side, name in (("D", race.get("dem_candidate")), ("R", race.get("rep_candidate"))):
                row = best_fec_match(rows, race, side, name)
                if not row or not name:
                    continue
                rec = fec_public_record(race, side, name, row, source_url)
                attached.append(rec)
                records.append(rec)
                d = parse_date(rec.get("coverage_through"))
                if d and (latest is None or d > latest):
                    latest = d
            if attached:
                coverages = {x.get("coverage_through") for x in attached if x.get("coverage_through")}
                race["money"] = {
                    "state": "current",
                    "source": "Federal Election Commission",
                    "candidates": attached,
                    "coverage_mismatch": len(coverages) > 1,
                }
        state = source_age_state(latest, today, current_days=35, stale_days=75)
        # FEC quarterly/monthly reporting calendars differ; a valid successful
        # official bulk retrieval remains usable even if coverage dates differ.
        if state == "unavailable" and records:
            state = "stale"
        source = {
            "state": state,
            "source": "Federal Election Commission",
            "mode": "official bulk data",
            "url": FEC_HOME,
            "bulk_url": source_url,
            "last_success": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "latest_coverage": latest.isoformat() if latest else None,
            "matched_candidates": len(records),
            "note": "Official FEC current-campaign summaries. Reporting periods travel with every dollar figure; unmatched candidates remain missing rather than guessed.",
            "records": records,
        }
        return source, records
    except Exception as exc:
        cached_records = previous.get("records") or []
        if cached_records:
            by_race: dict[str, list[dict]] = {}
            for rec in cached_records:
                by_race.setdefault(str(rec.get("race_code")), []).append(rec)
            for race in modeled:
                attached = by_race.get(str(race.get("race_code")), [])
                if attached:
                    race["money"] = {"state": "stale", "source": "Federal Election Commission", "candidates": attached, "coverage_mismatch": len({x.get('coverage_through') for x in attached}) > 1}
            return {
                "state": "stale",
                "source": "Federal Election Commission",
                "mode": "last-known-good official bulk data",
                "url": FEC_HOME,
                "latest_coverage": previous.get("latest_coverage"),
                "matched_candidates": len(cached_records),
                "note": "Live FEC bulk retrieval failed; serving the last-known-good official snapshot and marking it stale.",
                "error": type(exc).__name__,
                "records": cached_records,
            }, cached_records
        return {
            "state": "unavailable",
            "source": "Federal Election Commission",
            "mode": "official bulk data",
            "url": FEC_HOME,
            "matched_candidates": 0,
            "note": "Official FEC bulk retrieval failed and no last-known-good snapshot exists.",
            "error": type(exc).__name__,
            "records": [],
        }, []


def money_for_public_index(records: list[dict], modeled: list[dict]) -> list[dict]:
    by_code = {r.get("race_code"): r for r in modeled}
    selected = []
    for rec in records:
        race = by_code.get(rec.get("race_code"))
        if not race:
            continue
        competitive = race.get("race_type") == "senate" or 0.10 <= float(race.get("dem_probability", 0.5)) <= 0.90
        if competitive:
            selected.append(rec)
    selected.sort(key=lambda x: (x.get("race_code") or "", x.get("party") or ""))
    return selected


def money_fmt(value: Any) -> str:
    try:
        n = float(value)
    except Exception:
        return "unavailable"
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.1f}m"
    if abs(n) >= 1_000:
        return f"${n/1_000:.0f}k"
    return f"${n:,.0f}"


def build_signals(model: dict, inside_records: dict[str, dict], fec_records: list[dict], previous: dict | None, today: date) -> list[dict]:
    signals: list[dict] = []
    seen: set[str] = set()

    def add(signal: dict) -> None:
        sid = str(signal.get("id") or "")
        if not sid or sid in seen:
            return
        seen.add(sid)
        signal.setdefault("model_effect", "NONE")
        signal.setdefault("confidence", "source-recorded")
        signals.append(signal)

    # Current polling is itself a structured election signal. These records are
    # quantitative model inputs, not qualitative text interpretations.
    for p in model.get("polls", []) or model.get("national_environment", {}).get("recent_polls", []):
        d = parse_date(p.get("end_date"))
        if not d or (today - d).days > 10:
            continue
        margin = p.get("margin")
        pollster = p.get("pollster") or "Unknown pollster"
        add({
            "id": f"poll-national-{pollster}-{p.get('end_date')}-{margin}",
            "date": d.isoformat(),
            "category": "POLL",
            "geography": "National",
            "description": f"{pollster} generic-ballot observation recorded at D−R {float(margin):+.1f}.",
            "source_name": pollster,
            "source": p.get("source"),
            "provenance": "Production generic-ballot observation",
            "model_effect": "POLL INPUT",
        })

    for race in model.get("races", []):
        for p in race.get("polls", []):
            d = parse_date(p.get("end_date"))
            if not d or (today - d).days > 14:
                continue
            margin = p.get("margin")
            pollster = p.get("pollster") or "Unknown pollster"
            add({
                "id": f"poll-{race.get('race_code')}-{pollster}-{p.get('end_date')}-{margin}",
                "date": d.isoformat(),
                "category": "POLL",
                "race_code": race.get("race_code"),
                "geography": race.get("race_code"),
                "description": f"{pollster} race poll recorded at D−R {float(margin):+.1f} for {race.get('race_code')}.",
                "source_name": pollster,
                "source": p.get("source"),
                "provenance": "Production nominee-matched race-poll observation",
                "model_effect": "POLL INPUT",
            })

    # External rating changes remain context only.
    for race_code, rec in inside_records.items():
        shift = str(rec.get("shift") or "").strip().lower()
        previous_rating = rec.get("previous_rating")
        if not shift or shift in {"no-change", "no change", "none"} or not previous_rating or previous_rating == rec.get("rating"):
            continue
        d = parse_date(rec.get("updated_at")) or today
        if (today - d).days > 45:
            continue
        add({
            "id": f"rating-inside-{race_code}-{d.isoformat()}-{rec.get('rating')}",
            "date": d.isoformat(),
            "category": "RATING CHANGE",
            "race_code": race_code,
            "geography": race_code,
            "description": f"Inside Elections changed {race_code} from {previous_rating} to {rec.get('rating')}.",
            "source_name": "Inside Elections",
            "source": rec.get("source"),
            "provenance": "Inside Elections public ratings API",
            "model_effect": "NONE",
        })

    # FEC summaries are factual financial records. Limit public signal noise to
    # competitive House races and all Senate races, matching the Money centre.
    by_code = {r.get("race_code"): r for r in model.get("races", [])}
    for rec in money_for_public_index(fec_records, model.get("races", [])):
        d = parse_date(rec.get("coverage_through"))
        if not d or (today - d).days > 50:
            continue
        race = by_code.get(rec.get("race_code")) or {}
        add({
            "id": f"fec-{rec.get('fec_candidate_id')}-{rec.get('coverage_through')}",
            "date": d.isoformat(),
            "category": "FUNDRAISING",
            "race_code": rec.get("race_code"),
            "geography": rec.get("race_code"),
            "description": f"FEC summary through {d.isoformat()} records {money_fmt(rec.get('receipts'))} receipts, {money_fmt(rec.get('disbursements'))} spending and {money_fmt(rec.get('cash_on_hand'))} cash on hand for {rec.get('candidate')}.",
            "source_name": "Federal Election Commission",
            "source": rec.get("source") or FEC_HOME,
            "provenance": "Official FEC current-campaign summary",
            "model_effect": "NONE",
            "importance": "high" if race.get("race_type") == "senate" or 0.35 <= float(race.get("dem_probability", 0.5)) <= 0.65 else "normal",
        })

    # Candidate roster changes between immutable production snapshots.
    old = {r.get("race_code"): r for r in (previous or {}).get("races", [])}
    for race in model.get("races", []):
        prior = old.get(race.get("race_code"))
        if not prior:
            continue
        for party, field in (("D", "dem_candidate"), ("R", "rep_candidate")):
            before, after = prior.get(field), race.get(field)
            if before and after and before != after:
                add({
                    "id": f"candidate-{race.get('race_code')}-{party}-{after}",
                    "date": today.isoformat(),
                    "category": "CANDIDATE EVENT",
                    "race_code": race.get("race_code"),
                    "geography": race.get("race_code"),
                    "description": f"Production race metadata changed the {party} candidate from {before} to {after}.",
                    "source_name": "2026 election input mirror",
                    "source": model.get("provenance", {}).get("upstream_input_mirror"),
                    "provenance": "Pinned production race metadata",
                    "model_effect": "NONE",
                })

    signals.sort(key=lambda s: (s.get("date") or "", s.get("importance") == "high", s.get("category") or ""), reverse=True)
    return signals[:120]


def external_source_catalog(inside_source: dict) -> list[dict]:
    return [
        {
            "name": "Cook Political Report",
            "id": "cook",
            "state": "restricted",
            "mode": "licensed/manual boundary",
            "url": "https://www.cookpolitical.com/ratings/house-race-ratings",
            "note": "No licensed automated redistribution/API access is configured. MIDTERM SIGNALS links to Cook but does not scrape or infer its ratings.",
        },
        inside_source,
        {
            "name": "Sabato's Crystal Ball",
            "id": "crystal_ball",
            "state": "manual",
            "mode": "manual/link boundary",
            "url": "https://centerforpolitics.org/crystalball/",
            "note": "Public analysis is linked; no redistribution-safe automated ratings feed is configured. Manual imports can be added with source/date provenance.",
        },
        {
            "name": "Silver Bulletin",
            "id": "silver_bulletin",
            "state": "restricted",
            "mode": "subscriber/licensing boundary",
            "url": "https://www.natesilver.net/",
            "note": "Subscriber/licensing boundary. No paywall bypass, scraping or synthetic reconstruction.",
        },
        {
            "name": "Decision Desk HQ",
            "id": "ddhq",
            "state": "manual",
            "mode": "public-page/manual boundary",
            "url": "https://votes.decisiondeskhq.com/forecast/2026",
            "note": "Public forecast pages are linked. Until a documented machine-data permission/API is configured, race forecasts are not scraped into production.",
        },
    ]


def replace_source(sources: list[dict], source_id: str, replacement: dict) -> None:
    for i, item in enumerate(sources):
        if item.get("id") == source_id:
            sources[i] = replacement
            return
    sources.append(replacement)


def numerical_fingerprint(model: dict) -> str:
    payload = {k: model.get(k) for k in FORECAST_INVARIANT_KEYS}
    payload["races"] = [
        {"race_code": r.get("race_code"), **{k: r.get(k) for k in RACE_NUMERIC_KEYS}}
        for r in model.get("races", [])
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> None:
    model = load_json(FORECAST)
    if not isinstance(model, dict):
        raise SystemExit("forecast.json missing or invalid; enrichment cannot run")
    previous_model = None
    history = DATA / "history"
    if history.exists():
        candidates = sorted([p for p in history.glob("*.json") if p.name != "index.json"], reverse=True)
        for path in candidates:
            try:
                candidate = load_json(path)
                if candidate and candidate.get("generated_at") != model.get("generated_at"):
                    previous_model = candidate
                    break
            except Exception:
                continue

    before = numerical_fingerprint(model)
    today = min(date.today(), date(2026, 11, 3))
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    previous_external = load_json(EXTERNAL, {}) or {}
    inside_source, inside_records = fetch_inside_elections(model.get("races", []), today, previous_external.get("inside_elections"))
    for race in model.get("races", []):
        rec = inside_records.get(race.get("race_code"))
        if rec:
            race.setdefault("external_forecasters", {})["Inside Elections"] = rec

    previous_fec = load_json(FEC, {}) or {}
    fec_source, fec_records = attach_fec(model.get("races", []), today, previous_fec)

    signals = build_signals(model, inside_records, fec_records, previous_model, today)
    sources = external_source_catalog(inside_source)
    automated_count = sum(1 for s in sources if s.get("state") in {"current", "stale"} and s.get("mode") in {"public API", "last-known-good public API"})
    manual_count = sum(1 for s in sources if s.get("state") == "manual")
    model["external_forecasters"] = {
        "configured_count": automated_count,
        "tracked_count": len(sources),
        "manual_count": manual_count,
        "race_ratings_count": len(inside_records),
        "sources": sources,
        "note": "External forecasts are displayed on their native scales and are not inputs to MIDTERM SIGNALS probabilities.",
    }
    public_money = money_for_public_index(fec_records, model.get("races", []))
    model["money"] = {
        "state": fec_source.get("state"),
        "source": "Federal Election Commission",
        "mode": fec_source.get("mode"),
        "latest_coverage": fec_source.get("latest_coverage"),
        "records": public_money,
        "matched_candidates": fec_source.get("matched_candidates", len(fec_records)),
        "note": fec_source.get("note"),
    }
    model["campaign_signals"] = signals

    health = load_json(SOURCE_STATUS, {}) or {}
    health_sources = health.get("sources") or model.get("source_health") or []
    replace_source(health_sources, "inside_elections", {
        "id": "inside_elections", "label": "Inside Elections", "kind": "third-party forecast",
        "state": inside_source.get("state", "unavailable"), "url": inside_source.get("url"),
        "last_success": now if inside_source.get("state") == "current" else None,
        "last_observation": inside_source.get("last_updated"),
        "note": f"{inside_source.get('ratings_count', 0)} native race ratings via public API; no model effect.",
    })
    replace_source(health_sources, "cook", {
        "id": "cook", "label": "Cook Political Report", "kind": "third-party forecast", "state": "restricted",
        "url": "https://www.cookpolitical.com/ratings/house-race-ratings",
        "note": "Licensed/manual boundary. No automated scraping or synthetic ratings.",
    })
    replace_source(health_sources, "crystal_ball", {
        "id": "crystal_ball", "label": "Sabato's Crystal Ball", "kind": "third-party forecast", "state": "manual",
        "url": "https://centerforpolitics.org/crystalball/", "note": "Public source linked; manual/import adapter boundary retained until a redistribution-safe feed is configured.",
    })
    replace_source(health_sources, "silver_bulletin", {
        "id": "silver_bulletin", "label": "Silver Bulletin", "kind": "third-party forecast", "state": "restricted",
        "url": "https://www.natesilver.net/", "note": "Subscriber/licensing boundary; no paywall bypass.",
    })
    replace_source(health_sources, "ddhq", {
        "id": "ddhq", "label": "Decision Desk HQ", "kind": "third-party forecast", "state": "manual",
        "url": "https://votes.decisiondeskhq.com/forecast/2026", "note": "Public forecast linked; no undocumented scraping/API use.",
    })
    replace_source(health_sources, "fec", {
        "id": "fec", "label": "Federal Election Commission", "kind": "campaign finance", "state": fec_source.get("state", "unavailable"),
        "url": FEC_HOME, "last_success": fec_source.get("last_success"), "last_observation": fec_source.get("latest_coverage"),
        "note": f"Official bulk adapter; {fec_source.get('matched_candidates', 0)} candidate summaries matched to production candidates.",
    })
    signal_state = "current" if signals else "unavailable"
    replace_source(health_sources, "campaign_signals", {
        "id": "campaign_signals", "label": "Campaign signals", "kind": "structured election intelligence", "state": signal_state,
        "last_success": now if signals else None, "last_observation": signals[0].get("date") if signals else None,
        "note": f"{len(signals)} structured records. Poll inputs are labelled; qualitative/external/FEC context defaults to model effect NONE.",
    })
    model["source_health"] = health_sources

    after = numerical_fingerprint(model)
    if before != after:
        raise RuntimeError("Enrichment changed protected numerical forecast fields")

    external_payload = {
        "generated_at": now,
        "inside_elections": {
            **inside_source,
            "race_ratings": inside_records,
        },
        "sources": sources,
        "model_effect": "NONE",
    }
    fec_payload = {**fec_source, "generated_at": now, "records": fec_records, "model_effect": "NONE"}
    signals_payload = {"generated_at": now, "signals": signals, "default_model_effect": "NONE"}

    write_json(FORECAST, model)
    write_json(EXTERNAL, external_payload)
    write_json(FEC, fec_payload)
    write_json(SIGNALS, signals_payload)
    write_json(SOURCE_STATUS, {"generated_at": now, "sources": health_sources})

    status = load_json(STATUS, {}) or {}
    status["enrichment_generated_at"] = now
    status["external_forecasters_automated"] = automated_count
    status["external_forecasters_tracked"] = len(sources)
    status["fec_state"] = fec_source.get("state")
    status["campaign_signals"] = len(signals)
    status["source_issues"] = sum(1 for s in health_sources if s.get("state") in {"stale", "unavailable", "degraded"})
    status["source_constraints"] = sum(1 for s in health_sources if s.get("state") in {"restricted", "manual"})
    write_json(STATUS, status)

    report = load_json(RUN_REPORT, {}) or {}
    report["enrichment"] = {
        "checks": "passed",
        "numerical_forecast_unchanged": True,
        "inside_elections_state": inside_source.get("state"),
        "inside_elections_ratings": len(inside_records),
        "fec_state": fec_source.get("state"),
        "fec_matched_candidates": fec_source.get("matched_candidates", 0),
        "public_money_records": len(public_money),
        "campaign_signals": len(signals),
        "access_constraints": [s.get("name") for s in sources if s.get("state") in {"restricted", "manual"}],
    }
    write_json(RUN_REPORT, report)
    print(
        "Enrichment passed: "
        f"Inside Elections {inside_source.get('state')} ({len(inside_records)} ratings); "
        f"FEC {fec_source.get('state')} ({fec_source.get('matched_candidates', 0)} candidates); "
        f"{len(signals)} campaign signals; numerical forecast unchanged"
    )


if __name__ == "__main__":
    main()
