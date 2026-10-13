#!/usr/bin/env python3
"""Acquire and normalize the 2018 Model Lab corpus.

One-shot, fail-closed historical admission. This is not part of the live
forecast refresh. Source inputs are commit-pinned where practical. The
Downballot/Daily Kos district sheet is admitted only if its bytes match an
independently published SHA-256 fingerprint.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "historical" / "2018"
RAW = OUT / "raw"
UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"

K5 = "47fd763f01de196586ca6e8f2ecb221e873b62ed"
FTE_MIRROR = "fe795fa790446b9c478de4b21a1df488ef8d1bf3"
MEDSL = "fe67c056502fc09ddb1ace2ff8f87c53233a744e"
DISTRICT_SHEET_SHA256 = "1ac29ca1575210f62470732cacd2b8d0203b6219ef5223bf12ae309f54f7a23e"

SOURCES = {
    "house_forecast": f"https://raw.githubusercontent.com/k5cents/models-markets/{K5}/data/raw/models/house_district_forecast.csv",
    "senate_forecast": f"https://raw.githubusercontent.com/k5cents/models-markets/{K5}/data/raw/models/senate_seat_forecast.csv",
    "winner_crosscheck": f"https://raw.githubusercontent.com/k5cents/models-markets/{K5}/data/new/results.csv",
    "house_polls": f"https://raw.githubusercontent.com/markjrieke/2022-midterm-forecasts/{FTE_MIRROR}/data/polls/src/fte/house_polls_historical.csv",
    "senate_polls": f"https://raw.githubusercontent.com/markjrieke/2022-midterm-forecasts/{FTE_MIRROR}/data/polls/src/fte/senate_polls_historical.csv",
    "generic_polls": f"https://raw.githubusercontent.com/markjrieke/2022-midterm-forecasts/{FTE_MIRROR}/data/polls/src/fte/generic_ballot_polls_historical.csv",
    "house_results": f"https://raw.githubusercontent.com/MEDSL/constituency-returns/{MEDSL}/1976-2018-house.csv",
    "senate_results": f"https://raw.githubusercontent.com/MEDSL/constituency-returns/{MEDSL}/1976-2018-senate.csv",
    "president_results": f"https://raw.githubusercontent.com/MEDSL/constituency-returns/{MEDSL}/1976-2016-president.csv",
    "district_presidential": "https://docs.google.com/spreadsheets/d/1zLNAuRqPauss00HDz4XbTH2HqsCzMe0pR8QmD1K8jk8/export?format=csv",
}

FEC_REFERENCE = {
    "2008": "https://www.fec.gov/resources/cms-content/documents/federalelections2008.pdf",
    "2012": "https://www.fec.gov/resources/cms-content/documents/federalelections2012.pdf",
    "2016": "https://www.fec.gov/resources/cms-content/documents/federalelections2016.pdf",
    "2018": "https://www.fec.gov/resources/cms-content/documents/federalelections2018.pdf",
}
FEC_NATIONAL_MARGINS = {2008: 7.28, 2012: 3.86, 2016: 2.09}

STATE_CODES = {
    "ALABAMA":"AL","ALASKA":"AK","ARIZONA":"AZ","ARKANSAS":"AR","CALIFORNIA":"CA",
    "COLORADO":"CO","CONNECTICUT":"CT","DELAWARE":"DE","FLORIDA":"FL","GEORGIA":"GA",
    "HAWAII":"HI","IDAHO":"ID","ILLINOIS":"IL","INDIANA":"IN","IOWA":"IA","KANSAS":"KS",
    "KENTUCKY":"KY","LOUISIANA":"LA","MAINE":"ME","MARYLAND":"MD","MASSACHUSETTS":"MA",
    "MICHIGAN":"MI","MINNESOTA":"MN","MISSISSIPPI":"MS","MISSOURI":"MO","MONTANA":"MT",
    "NEBRASKA":"NE","NEVADA":"NV","NEW HAMPSHIRE":"NH","NEW JERSEY":"NJ","NEW MEXICO":"NM",
    "NEW YORK":"NY","NORTH CAROLINA":"NC","NORTH DAKOTA":"ND","OHIO":"OH","OKLAHOMA":"OK",
    "OREGON":"OR","PENNSYLVANIA":"PA","RHODE ISLAND":"RI","SOUTH CAROLINA":"SC",
    "SOUTH DAKOTA":"SD","TENNESSEE":"TN","TEXAS":"TX","UTAH":"UT","VERMONT":"VT",
    "VIRGINIA":"VA","WASHINGTON":"WA","WEST VIRGINIA":"WV","WISCONSIN":"WI","WYOMING":"WY",
    "DISTRICT OF COLUMBIA":"DC",
}

GRADE_SCORE = {
    "A+":3.0,"A":2.8,"A-":2.6,"A/B":2.5,"B+":2.4,"B":2.2,"B-":2.0,
    "B/C":1.8,"C+":1.6,"C":1.4,"C-":1.2,"C/D":1.0,"D+":0.9,"D":0.8,"D-":0.75,
}
DEM_ALIGNED_INDEPENDENTS = {"ME-S1": "Angus King", "VT-S1": "Bernie Sanders"}


def fetch(name: str, url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as response:
        data = response.read()
    if not data:
        raise RuntimeError(f"Empty source: {name}")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{name}.csv").write_bytes(data)
    return data


def rows(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def fnum(value):
    try:
        return float(str(value or "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def parse_date(value) -> str:
    s = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%m/%d/%y %H:%M", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def party(value: str | None) -> str:
    s = str(value or "").strip().upper()
    if s.startswith("DEM") or s in {"D", "DFL"}:
        return "DEM"
    if s.startswith("REP") or s == "R":
        return "REP"
    if s.startswith("IND") or s == "I":
        return "IND"
    return s


def state_po(value: str | None) -> str:
    s = str(value or "").strip().upper()
    if len(s) == 2 and s.isalpha():
        return s
    return STATE_CODES.get(s, "")


def district_code(state, district) -> str:
    st = state_po(state)
    d = str(district or "").strip().upper()
    if not st:
        return ""
    if d in ("", "0", "00", "AL", "AT-LARGE"):
        return f"{st}-01"
    try:
        return f"{st}-{int(float(d)):02d}"
    except ValueError:
        return ""


def senate_class(row: dict) -> int | None:
    raw = str(row.get("class") or "").strip()
    if raw:
        try:
            n = int(float(raw))
            if n in (1, 2, 3):
                return n
        except ValueError:
            pass
    name = str(row.get("seat_name") or "").strip().upper()
    if "III" in name:
        return 3
    if "II" in name:
        return 2
    if re.search(r"\bI\b", name):
        return 1
    return None


def race_from_538(row: dict, chamber: str) -> str:
    if chamber == "house":
        return district_code(row.get("state"), row.get("district") or row.get("seat_number"))
    st = state_po(row.get("state"))
    cls = senate_class(row)
    return f"{st}-S{cls}" if st and cls else ""


def normalized_side(code: str, raw_party: str, candidate: str = "") -> str:
    p = party(raw_party)
    if p == "IND" and code in DEM_ALIGNED_INDEPENDENTS:
        return "DEM"
    return p


def parse_downballot(data: bytes) -> dict[str, dict[int, float]]:
    table = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    subheader_idx = None
    for i, row in enumerate(table[:10]):
        low = [c.strip().lower() for c in row]
        if any(c in {"clinton","trump","obama","romney","mccain"} for c in low):
            subheader_idx = i
            break
    if subheader_idx is None or subheader_idx == 0:
        raise RuntimeError("Downballot multi-year header not found")
    years = [c.strip() for c in table[subheader_idx - 1]]
    names = [c.strip().lower() for c in table[subheader_idx]]
    pairs = {}
    for i, y in enumerate(years):
        if y not in {"2008","2012","2016"}:
            continue
        dem = next((j for j in range(i, min(i+4, len(names))) if names[j] in {"clinton","obama","dem"}), None)
        rep = next((j for j in range(i, min(i+4, len(names))) if names[j] in {"trump","romney","mccain","rep"}), None)
        if dem is not None and rep is not None:
            pairs[int(y)] = (dem, rep)
    if set(pairs) != {2008, 2012, 2016}:
        raise RuntimeError(f"Downballot years missing: {pairs}")
    output = {}
    for row in table[subheader_idx + 1:]:
        if not row:
            continue
        code = str(row[0] or "").strip().upper().replace("-AL", "-01")
        if not re.match(r"^[A-Z]{2}-\d{2}$", code):
            continue
        vals = {}
        for year, (di, ri) in pairs.items():
            if max(di, ri) >= len(row):
                continue
            d, r = fnum(row[di]), fnum(row[ri])
            vals[year] = None if d is None or r is None else d - r
        if all(vals.get(y) is not None for y in (2008, 2012, 2016)):
            output[code] = vals
    if len(output) != 435:
        raise RuntimeError(f"Expected 435 structural districts, got {len(output)}")
    return output


def presidential_margins(president_rows: list[dict]) -> tuple[dict[int, float], dict[str, dict[int, float]]]:
    national = {}
    states: dict[str, dict[int, float]] = defaultdict(dict)
    for year in (2008, 2012, 2016):
        by_state = defaultdict(lambda: {"DEM": 0.0, "REP": 0.0, "ALL": 0.0})
        for row in president_rows:
            if str(row.get("year") or "") != str(year):
                continue
            st = state_po(row.get("state_po") or row.get("state"))
            votes = fnum(row.get("candidatevotes")) or 0.0
            if not st:
                continue
            by_state[st]["ALL"] += votes
            side = party(row.get("party"))
            if side in {"DEM", "REP"}:
                by_state[st][side] += votes
        d = sum(v["DEM"] for v in by_state.values())
        r = sum(v["REP"] for v in by_state.values())
        total = sum(v["ALL"] for v in by_state.values())
        if not d or not r or not total:
            raise RuntimeError(f"Missing presidential returns for {year}")
        national[year] = 100 * (d - r) / total
        for st, v in by_state.items():
            if v["ALL"] > 0:
                states[st][year] = 100 * (v["DEM"] - v["REP"]) / v["ALL"]
    for year, official in FEC_NATIONAL_MARGINS.items():
        if abs(national[year] - official) > 0.08:
            raise RuntimeError(f"MEDSL/FEC national margin disagreement {year}: {national[year]:.3f} vs {official:.2f}")
    missing = [st for st, vals in states.items() if any(y not in vals for y in (2008, 2012, 2016))]
    if missing:
        raise RuntimeError(f"State presidential baseline incomplete: {missing}")
    return national, dict(states)


def forecast_versions(forecast_rows: list[dict], chamber: str, district_structural, state_structural) -> list[dict]:
    by_race_date: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in forecast_rows:
        if str(row.get("model") or "").lower() != "deluxe":
            continue
        code = race_from_538(row, chamber)
        known = parse_date(row.get("forecastdate"))
        name = str(row.get("candidate") or "").strip()
        raw_party = party(row.get("party"))
        if not code or not known or not name:
            continue
        by_race_date[(code, known)].append({
            "name": name,
            "raw_party": raw_party,
            "side": normalized_side(code, raw_party, name),
            "incumbent": str(row.get("incumbent") or "").strip().upper() in {"TRUE", "1", "T"},
        })
    dates_by_race = defaultdict(list)
    for code, known in by_race_date:
        dates_by_race[code].append(known)
    output = []
    for code in sorted(dates_by_race):
        previous_signature = None
        for known in sorted(set(dates_by_race[code])):
            candidates = by_race_date[(code, known)]
            signature = tuple(sorted((c["name"], c["raw_party"], c["incumbent"]) for c in candidates))
            if signature == previous_signature:
                continue
            previous_signature = signature
            major = defaultdict(list)
            for c in candidates:
                if c["side"] in {"DEM", "REP"}:
                    major[c["side"]].append(c["name"])
            incumbent_rows = [c for c in candidates if c["incumbent"]]
            incumbent_party = incumbent_rows[0]["raw_party"] if len({c["raw_party"] for c in incumbent_rows}) == 1 and incumbent_rows else ""
            same_party = "DEM" if major["DEM"] and not major["REP"] else "REP" if major["REP"] and not major["DEM"] else ""
            st = code[:2]
            vals = district_structural.get(code) if chamber == "house" else state_structural.get(st)
            if not vals:
                raise RuntimeError(f"No structural prior for {code}")
            ind_name = DEM_ALIGNED_INDEPENDENTS.get(code, "")
            output.append({
                "race_code": code,
                "race_type": chamber,
                "state": st,
                "district": code.split("-")[1] if chamber == "house" else "",
                "known_date": known,
                "dem_name": major["DEM"][0] if major["DEM"] else "",
                "rep_name": major["REP"][0] if major["REP"] else "",
                "ind_name": ind_name if any(c["raw_party"] == "IND" for c in candidates) else "",
                "ind_caucus": "DEM" if ind_name and any(c["raw_party"] == "IND" for c in candidates) else "",
                "incumbent_party": incumbent_party,
                "same_party": same_party,
                "margin_earliest": vals[2008],
                "margin_middle": vals[2012],
                "margin_latest": vals[2016],
            })
    return output


def grade_score(value) -> float:
    return GRADE_SCORE.get(str(value or "").strip().upper(), 1.3)


def publication_date(row: dict, end_iso: str) -> str:
    created = parse_date(row.get("created_at") or row.get("publication_date"))
    if not created or not end_iso:
        return ""
    delta = (datetime.fromisoformat(created).date() - datetime.fromisoformat(end_iso).date()).days
    return created if 0 <= delta <= 14 else ""


def normalize_polls(raw_rows: list[dict], kind: str, chamber: str | None = None) -> list[dict]:
    if kind == "generic_ballot":
        output = []
        for row in raw_rows:
            if str(row.get("cycle") or "") != "2018":
                continue
            end = parse_date(row.get("end_date"))
            dem, rep = fnum(row.get("dem")), fnum(row.get("rep"))
            if not end or dem is None or rep is None:
                continue
            output.append({
                "kind": "generic_ballot",
                "publication_date": publication_date(row, end),
                "end_date": end,
                "pollster": row.get("pollster") or row.get("display_name") or "",
                "rating": grade_score(row.get("fte_grade")),
                "n": fnum(row.get("sample_size")) or 800,
                "lean": party(row.get("partisan"))[:1] if row.get("partisan") else "",
                "dem": dem, "rep": rep, "margin": dem - rep,
            })
        return output

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in raw_rows:
        if str(row.get("cycle") or "") != "2018":
            continue
        code = race_from_538(row, chamber or "")
        end = parse_date(row.get("end_date"))
        pct = fnum(row.get("pct"))
        side = normalized_side(code, row.get("candidate_party") or row.get("party"), row.get("candidate_name") or "")
        if not code or not end or pct is None or side not in {"DEM", "REP"}:
            continue
        key = (code, row.get("question_id") or row.get("poll_id"), row.get("population") or "", end)
        grouped[key].append({
            "side": side,
            "name": row.get("candidate_name") or "",
            "pct": pct,
            "row": row,
        })
    output = []
    for (code, _, _, end), candidates in grouped.items():
        by_side = defaultdict(list)
        for c in candidates:
            by_side[c["side"]].append(c)
        if len(by_side["DEM"]) != 1 or len(by_side["REP"]) != 1:
            continue
        d, r = by_side["DEM"][0], by_side["REP"][0]
        source = d["row"]
        output.append({
            "kind": "race",
            "race_code": code,
            "publication_date": publication_date(source, end),
            "end_date": end,
            "pollster": source.get("pollster") or source.get("display_name") or "",
            "rating": grade_score(source.get("fte_grade")),
            "n": fnum(source.get("sample_size")) or 800,
            "lean": party(source.get("partisan"))[:1] if source.get("partisan") else "",
            "dem_name": d["name"], "rep_name": r["name"],
            "dem": d["pct"], "rep": r["pct"], "margin": d["pct"] - r["pct"],
        })
    return output


def build_results(house_rows: list[dict], senate_rows: list[dict], race_codes: set[str]) -> list[dict]:
    candidates: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"votes": 0.0, "parties": set()}))
    for chamber, source_rows in (("house", house_rows), ("senate", senate_rows)):
        for row in source_rows:
            if str(row.get("year") or "") != "2018":
                continue
            if str(row.get("stage") or "").strip().upper() not in {"", "GEN"}:
                continue
            if chamber == "house":
                code = district_code(row.get("state_po") or row.get("state"), row.get("district"))
            else:
                st = state_po(row.get("state_po") or row.get("state"))
                special = str(row.get("special") or "").upper() == "TRUE"
                code = f"{st}-S{2 if special else 1}" if st else ""
            if code not in race_codes:
                continue
            name = str(row.get("candidate") or "").strip().upper()
            if not name:
                continue
            votes = fnum(row.get("candidatevotes")) or 0.0
            candidates[code][name]["votes"] += votes
            candidates[code][name]["parties"].add(party(row.get("party")))
    result = []
    for code in sorted(race_codes):
        if code not in candidates:
            raise RuntimeError(f"No result rows for {code}")
        winner_name, winner = max(candidates[code].items(), key=lambda item: item[1]["votes"])
        parties = winner["parties"]
        if "DEM" in parties:
            side = "DEM"
        elif "REP" in parties:
            side = "REP"
        elif code in DEM_ALIGNED_INDEPENDENTS:
            side = "DEM"
        else:
            raise RuntimeError(f"Cannot map winning party for {code}: {winner_name} {sorted(parties)}")
        result.append({"race_code": code, "winner_party": side})
    return result


def crosscheck_winners(result: list[dict], cross_rows: list[dict]) -> None:
    expected = {str(r.get("race") or ""): "DEM" if str(r.get("winner") or "").upper() == "TRUE" else "REP" for r in cross_rows}
    mismatches = [(r["race_code"], r["winner_party"], expected.get(r["race_code"])) for r in result if expected.get(r["race_code"]) and expected[r["race_code"]] != r["winner_party"]]
    if mismatches:
        raise RuntimeError(f"Independent winner-map cross-check failed: {mismatches[:12]}")


def write_csv(path: Path, data: list[dict]) -> None:
    if not data:
        raise RuntimeError(f"No rows for {path}")
    fields = []
    for row in data:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)


def main() -> None:
    blobs = {name: fetch(name, url) for name, url in SOURCES.items()}
    actual = hashlib.sha256(blobs["district_presidential"]).hexdigest()
    if actual != DISTRICT_SHEET_SHA256:
        raise RuntimeError(f"Downballot sheet SHA-256 mismatch: {actual}; refusing admission")

    district_structural = parse_downballot(blobs["district_presidential"])
    medsl_national, state_structural = presidential_margins(rows(blobs["president_results"]))

    races = forecast_versions(rows(blobs["house_forecast"]), "house", district_structural, state_structural)
    races += forecast_versions(rows(blobs["senate_forecast"]), "senate", district_structural, state_structural)
    race_codes = {r["race_code"] for r in races}
    house_codes = {c for c in race_codes if "-S" not in c}
    senate_codes = race_codes - house_codes
    if len(house_codes) != 435:
        raise RuntimeError(f"House race universe incomplete: {len(house_codes)}")
    if len(senate_codes) != 35:
        raise RuntimeError(f"Senate race universe incomplete: {len(senate_codes)}")

    polls = normalize_polls(rows(blobs["house_polls"]), "race", "house")
    polls += normalize_polls(rows(blobs["senate_polls"]), "race", "senate")
    generic = normalize_polls(rows(blobs["generic_polls"]), "generic_ballot")
    polls += generic
    if not generic:
        raise RuntimeError("No 2018 generic-ballot polls normalized")

    results = build_results(rows(blobs["house_results"]), rows(blobs["senate_results"]), race_codes)
    if len(results) != 470:
        raise RuntimeError(f"Result universe incomplete: {len(results)}")
    crosscheck_winners(results, rows(blobs["winner_crosscheck"]))

    write_csv(OUT / "races.csv", races)
    write_csv(OUT / "polls.csv", polls)
    write_csv(OUT / "results.csv", results)

    provenance = []
    for name, url in SOURCES.items():
        provenance.append({"name": name, "url": url, "sha256": hashlib.sha256(blobs[name]).hexdigest(), "bytes": len(blobs[name])})
    provenance.append({"name": "FEC official election reports", "urls": FEC_REFERENCE, "role": "official external cross-check for national margins and published federal results"})

    config = {
        "cycle": 2018,
        "election_date": "2018-11-06",
        "corpus_state": "admitted",
        "baseline_presidential_years": [2008, 2012, 2016],
        "national_presidential_margins": {
            "earliest": FEC_NATIONAL_MARGINS[2008],
            "middle": FEC_NATIONAL_MARGINS[2012],
            "latest": FEC_NATIONAL_MARGINS[2016],
        },
        "provenance": provenance,
        "admission": {
            "unique_house_races": len(house_codes),
            "unique_senate_races": len(senate_codes),
            "roster_versions": len(races),
            "poll_rows": len(polls),
            "result_rows": len(results),
            "downballot_sha256_expected": DISTRICT_SHEET_SHA256,
            "medsl_national_margin_crosscheck": {str(y): round(medsl_national[y], 6) for y in (2008, 2012, 2016)},
            "transformations": {
                "poll_quality": "FiveThirtyEight letter grades converted to a predeclared monotone 0.75-3.0 scale; missing grade=1.3. No election outcomes are used.",
                "poll_availability": "created_at is used only when it falls 0-14 days after poll end; otherwise publication_date is blank and Model Lab falls back to end_date.",
                "multi_candidate_polls": "Questions with multiple candidates on the same D/R side are excluded from binary race-poll blending.",
                "aligned_independents": "Angus King (ME-S1) and Bernie Sanders (VT-S1) are scored as Democratic-aligned for chamber-control outcome; their raw incumbent party remains IND.",
            },
            "notes": [
                "FiveThirtyEight forecast probabilities and vote-share forecasts are never imported as MIDTERM SIGNALS predictive inputs.",
                "Roster known_date comes from first appearance or subsequent candidate-set change in the archived daily FiveThirtyEight deluxe forecast.",
                "MEDSL constituency returns supply machine-readable scoring outcomes and are checked against an independently preserved 2018 winner map.",
                "Official FEC published national presidential margins are used in the frozen structural-prior convention.",
            ],
        },
    }
    (OUT / "cycle.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(config["admission"], indent=2))


if __name__ == "__main__":
    main()
