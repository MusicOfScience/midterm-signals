#!/usr/bin/env python3
"""Acquire and normalize the 2018 Model Lab corpus.

One-shot, fail-closed historical admission. This script is never part of the
live forecast refresh. Predictive inputs are reconstructed only from evidence
known by each historical cutoff. Election outcomes are normalized separately
and consumed only later by Model Lab scoring.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tempfile
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import pyreadr
except ImportError as exc:
    raise SystemExit("Historical admission requires pyreadr==0.5.7") from exc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "historical" / "2018"
RAW = OUT / "raw"
UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"

K5 = "47fd763f01de196586ca6e8f2ecb221e873b62ed"
FTE_MIRROR = "fe795fa790446b9c478de4b21a1df488ef8d1bf3"
MEDSL = "fe67c056502fc09ddb1ace2ff8f87c53233a744e"
CCES = "e4482502dbebc00ca4060c29c7e532272d4b03c6"

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
    "district_structural": f"https://raw.githubusercontent.com/kuriwaki/ccesMRPprep/{CCES}/data/cd_info_2018.rda",
}

STRUCTURAL_DOC = f"https://github.com/kuriwaki/ccesMRPprep/blob/{CCES}/man/cd_info.Rd"
STRUCTURAL_LICENSE = f"https://github.com/kuriwaki/ccesMRPprep/blob/{CCES}/LICENSE"
FEC_REFERENCE = {
    "2008": "https://www.fec.gov/resources/cms-content/documents/federalelections2008.pdf",
    "2012": "https://www.fec.gov/resources/cms-content/documents/federalelections2012.pdf",
    "2016": "https://www.fec.gov/resources/cms-content/documents/federalelections2016.pdf",
    "2018": "https://www.fec.gov/resources/cms-content/documents/federalelections2018.pdf",
}
# D percentage minus R percentage of all presidential votes. This matches the
# national centring constants used by the frozen live specification.
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
    suffix = ".rda" if name == "district_structural" else ".csv"
    (RAW / f"{name}{suffix}").write_bytes(data)
    return data


def csv_rows(data: bytes) -> list[dict]:
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


def structural_from_rda(data: bytes) -> dict[str, dict[int, float]]:
    with tempfile.NamedTemporaryFile(suffix=".rda") as tmp:
        tmp.write(data)
        tmp.flush()
        objects = pyreadr.read_r(tmp.name)
    if not objects:
        raise RuntimeError("cd_info_2018.rda contained no readable data frame")
    frame = next(iter(objects.values()))
    required = {"cd", "pct_mccain", "pct_romney", "pct_trump"}
    if not required.issubset(frame.columns):
        raise RuntimeError(f"cd_info_2018 columns missing: {sorted(required - set(frame.columns))}")
    output = {}
    for row in frame.to_dict("records"):
        code = str(row.get("cd") or "").strip().upper().replace("-AL", "-01")
        if not re.match(r"^[A-Z]}{2}-\d{2}$", code):
            continue
        values = {}
        for year, key in ((2008, "pct_mccain"), (2012, "pct_romney"), (2016, "pct_trump")):
            rshare = fnum(row.get(key))
            if rshare is None:
                values[year] = None
                continue
            # ccesMRPprep stores Republican two-party vote share. Handle either
            # proportion or percent representation defensively.
            if abs(rshare) <= 1.0:
                rshare *= 100.0
            if not 0 <= rshare <= 100:
                raise RuntimeError(f"Impossible {key} for {code}: {rshare}")
            values[year] = 100.0 - 2.0 * rshare
        if all(values[y] is not None for y in (2008, 2012, 2016)):
            output[code] = values
    if len(output) != 435:
        raise RuntimeError(f"Expected 435 complete 2018-line districts from cd_info_2018, got {len(output)}")
    return output


def presidential_margins(president_rows: list[dict]) -> tuple[dict[int, float], dict[str, dict[int, float]]]:
    national = {}
    states: dict[str, dict[int, float]] = defaultdict(dict)
    for year in (2008, 2012, 2016):
        by_state = defaultdict(lambda: {"DEM": 0.0, "REP": 0.0, "TOTAL": 0.0})
        for row in president_rows:
            if str(row.get("year") or "") != str(year):
                continue
            st = state_po(row.get("state_po") or row.get("state"))
            votes = fnum(row.get("candidatevotes")) or 0.0
            totalvotes = fnum(row.get("totalvotes")) or 0.0
            if not st:
                continue
            # MEDSL repeats the state total on every candidate row. Use it once;
            # summing candidate rows can omit uncategorised/write-in residuals.
            by_state[st]["TOTAL"] = max(by_state[st]["TOTAL"], totalvotes)
            side = party(row.get("party"))
            if side in {"DEM", "REP"}:
                by_state[st][side] += votes
        d = sum(v)["DEM"] for v in by_state.values())
        r = sum(v["REP"] for v in by_state.values())
        total = sum(v)["TOTAL"] for v in by_state.values())
        if not d or not r or not total:
            raise RuntimeError(f"Missing presidential returns for {year}")
        national[year] = 100 * (d - r) / total
        for st, v in by_state.items():
            dr = vX-®ιάjΧ