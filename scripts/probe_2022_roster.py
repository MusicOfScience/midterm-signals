#!/usr/bin/env python3
"""Classify dated 2022 FiveThirtyEight roster states before replay admission.

Candidate identities are metadata, not model outputs. The preserved topline
files repeat the same roster across forecast variants, so this probe collapses
variant rows only when their candidate signatures agree. Any disagreement at
the same race/date fails closed instead of choosing a forecast variant.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime

UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"
COMMIT = "83f2c9867f319b921fa10ad04bc256d8106bc8f4"
BASE = f"https://raw.githubusercontent.com/stephensond/election-night-2022/{COMMIT}/input"
FILES = {
    "house": f"{BASE}/house_district_toplines_2022.csv",
    "senate": f"{BASE}/senate_state_toplines_2022.csv",
}
CHECKPOINTS = [date(2022,9,9), date(2022,10,9), date(2022,10,25), date(2022,11,1), date(2022,11,7)]
EDGE_PREFIXES = ("AK", "GA", "LA", "OK")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=240) as r:
        data = r.read()
    if not data:
        raise RuntimeError(f"empty source: {url}")
    return data


def parse_day(v: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime((v or "").strip(), fmt).date()
        except ValueError:
            pass
    return None


def code(row: dict, chamber: str) -> str:
    raw = (row.get("district") or "").strip().upper()
    if chamber == "senate":
        return raw
    return raw.replace("-AL", "-01")


def signature(row: dict) -> tuple[str, str, str]:
    return tuple((row.get(k) or "").strip() for k in ("name_D1", "name_R1", "name_I1"))


def classify(row: dict) -> str:
    d, r, i = signature(row)
    if d and r:
        return "binary_dr_with_ind" if i else "binary_dr"
    if d and not r:
        return "dem_no_rep"
    if r and not d:
        return "rep_no_dem"
    if i and not d and not r:
        return "ind_only"
    return "no_major_candidates"


def scan(chamber: str, data: bytes) -> dict:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="strict")))
    required = {"cycle","branch","district","forecastdate","expression","name_D1","name_R1"}
    missing = sorted(required - set(reader.fieldnames or []))
    if missing:
        raise RuntimeError(f"{chamber} roster missing fields: {missing}")

    branches = Counter()
    expressions = Counter()
    variants: dict[tuple[str,date], list[dict]] = defaultdict(list)
    for row in reader:
        if str(row.get("cycle") or "") != "2022":
            continue
        branches[row.get("branch") or ""] += 1
        expressions[row.get("expression") or ""] += 1
        day = parse_day(row.get("forecastdate") or "")
        rc = code(row, chamber)
        if day and rc:
            variants[(rc, day)].append(dict(row))

    collapsed=[]
    disagreements=[]
    for (rc,day), rows in variants.items():
        sigs={signature(r) for r in rows}
        # Empty independent-name differences are harmless only if D/R agree.
        dr={(s[0],s[1]) for s in sigs}
        if len(dr) != 1:
            disagreements.append({"race_code":rc,"date":day.isoformat(),"signatures":[list(s) for s in sorted(sigs)]})
            continue
        # Choose the most complete representative; this affects metadata only.
        row=max(rows,key=lambda r:sum(bool((r.get(k) or "").strip()) for k in ("name_D1","name_R1","name_I1")))
        row["_day"]=day; row["_code"]=rc
        collapsed.append(row)
    if disagreements:
        raise RuntimeError(f"candidate roster disagreement across forecast variants: {disagreements[:8]}")
    if not collapsed:
        raise RuntimeError(f"no dated {chamber} roster rows")

    by_code=defaultdict(list)
    for row in collapsed: by_code[row["_code"]].append(row)
    for arr in by_code.values(): arr.sort(key=lambda r:r["_day"])

    checkpoint_summary=[]; exclusions=defaultdict(set); edge=[]
    for cp in CHECKPOINTS:
        counts=Counter(); active=0
        for rc,arr in by_code.items():
            eligible=[r for r in arr if r["_day"]<=cp]
            if not eligible: continue
            row=eligible[-1]; active+=1; cls=classify(row); counts[cls]+=1
            if cls != "binary_dr": exclusions[rc].add(cls)
            if rc.startswith(EDGE_PREFIXES):
                edge.append({
                    "checkpoint":cp.isoformat(),"race_code":rc,"class":cls,
                    "forecastdate":row["_day"].isoformat(),
                    "D":row.get("name_D1") or "","R":row.get("name_R1") or "","I":row.get("name_I1") or "",
                    "branch_example":row.get("branch") or "","expression_example":row.get("expression") or "",
                })
        checkpoint_summary.append({"checkpoint":cp.isoformat(),"active_races":active,"classes":dict(counts)})

    return {
        "columns": reader.fieldnames or [],
        "branch_counts": dict(branches),
        "expression_counts": dict(expressions),
        "variant_race_dates": len(variants),
        "collapsed_race_dates": len(collapsed),
        "unique_races": len(by_code),
        "date_min": min(r["_day"] for r in collapsed).isoformat(),
        "date_max": max(r["_day"] for r in collapsed).isoformat(),
        "checkpoints": checkpoint_summary,
        "nonbinary_races": {k:sorted(v) for k,v in sorted(exclusions.items())},
        "edge_cases": edge,
    }


def main() -> None:
    out={}
    for chamber,url in FILES.items():
        data=fetch(url); out[chamber]={"url":url,"bytes":len(data),**scan(chamber,data)}
    if out["house"]["unique_races"] < 435: raise RuntimeError(f"house roster universe too small: {out['house']['unique_races']}")
    if out["senate"]["unique_races"] < 34: raise RuntimeError(f"senate roster universe too small: {out['senate']['unique_races']}")
    print(json.dumps(out,indent=2,default=str))


if __name__ == "__main__": main()
