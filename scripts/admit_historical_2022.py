#!/usr/bin/env python3
"""Strict entrypoint for the 2022 historical admission.

Admission-policy guards live here so identity/source corrections cannot
silently alter the frozen forecasting implementation.
"""
from __future__ import annotations

import csv
import io
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

import run_historical_2022 as impl

MEDSL_PRES_COMMIT = "fe67c056502fc09ddb1ace2ff8f87c53233a744e"
MEDSL_PRES_URL = (
    "https://raw.githubusercontent.com/MEDSL/constituency-returns/"
    f"{MEDSL_PRES_COMMIT}/1976-2016-president.csv"
)


def strict_match_incumbents(row: dict, chamber: str, incumbents: dict) -> tuple[str, list[str], bool]:
    """Match incumbents without surname/initial false positives."""
    st = row["_code"][:2]
    term_type = "rep" if chamber == "house" else "sen"
    named = [(n, "DEM") for n in impl.names(row, impl.D_KEYS)] + [(n, "REP") for n in impl.names(row, impl.R_KEYS)]
    matched = []
    state_pool = incumbents.get((term_type, st), [])

    for candidate, side in named:
        pool = [inc for inc in state_pool if inc["party"] == side]
        surname_freq = defaultdict(int)
        for inc in pool:
            seen = set()
            for alias in inc["aliases"]:
                bits = alias.split()
                if bits:
                    seen.add(bits[-1])
            for s in seen:
                surname_freq[s] += 1

        cn = impl.norm_name(candidate)
        cbits = cn.split()
        cs = cbits[-1] if cbits else ""
        cinitial = cbits[0][0] if cbits and cbits[0] else ""
        candidates = []
        for inc in pool:
            if cn in inc["aliases"]:
                candidates.append(inc)
                continue
            alias_bits = [a.split() for a in inc["aliases"] if a.split()]
            compatible = any(bits[-1] == cs and bits[0][0] == cinitial for bits in alias_bits)
            if cs and cinitial and surname_freq[cs] == 1 and compatible:
                candidates.append(inc)

        uniq = {(x["name"], x["party"]) for x in candidates}
        if len(uniq) == 1:
            matched.append(next(iter(uniq)))
        elif len(uniq) > 1:
            return "", [x[0] for x in sorted(uniq)], True

    parties = {p for _, p in matched}
    ambiguous = len(parties) > 1
    return (next(iter(parties)) if len(parties) == 1 else ""), [n for n, _ in matched], ambiguous


def alaska_2012_two_party() -> tuple[float, float]:
    """Return exact Alaska 2012 Democratic/Republican presidential votes.

    Alaska is an at-large House district, so statewide presidential returns are
    exactly the district return; no geographic remap is required.
    """
    data = impl.fetch("MEDSL 1976-2016 presidential state returns", MEDSL_PRES_URL)
    dem = rep = 0.0
    for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        if str(row.get("year") or "") != "2012" or str(row.get("state_po") or "").upper() != "AK":
            continue
        p = str(row.get("party") or "").strip().lower()
        votes = impl.fnum(row.get("candidatevotes"), 0.0) or 0.0
        if p.startswith("democrat"):
            dem += votes
        elif p.startswith("republican"):
            rep += votes
    if dem <= 0 or rep <= 0:
        raise RuntimeError(f"MEDSL Alaska 2012 two-party vote unavailable: D={dem} R={rep}")
    return dem, rep


def strict_structural_priors() -> dict:
    """Aggregate 2012/2016/2020 presidential returns onto 118th districts.

    DRA block data remains canonical for redistricted geography. Alaska 2012 is
    supplied from exact statewide MEDSL returns because Alaska is at-large and
    its DRA archive lacks 2012 fields. Census non-district placeholders are
    discarded before margin calculation; the final 435-district invariant
    ensures that no real congressional district can vanish silently.
    """
    refs = impl.latest_dra_refs()
    ak12 = alaska_2012_two_party()
    required_by_year = {
        12: ("E_12_PRES_Dem", "E_12_PRES_Rep"),
        16: ("E_16_PRES_Dem", "E_16_PRES_Rep"),
        20: ("E_20_PRES_Dem", "E_20_PRES_Rep"),
    }
    with tempfile.TemporaryDirectory() as td:
        paths = impl.split_bef(Path(td))
        districts = {}
        for st in sorted(impl.FIPS):
            mapping = {}
            with paths[st].open(newline="") as fh:
                for geoid, cd in csv.reader(fh):
                    mapping[geoid] = cd
            _, url = refs[st]
            data = impl.fetch(f"DRA blocks {st}", url, timeout=600)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                members = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX/")]
                if not members:
                    raise RuntimeError(f"{st}: DRA zip has no CSV")
                text = io.TextIOWrapper(z.open(members[0]), encoding="utf-8-sig", errors="replace", newline="")
                reader = csv.DictReader(text)
                fields = set(reader.fieldnames or [])
                available = {yr for yr, pair in required_by_year.items() if set(pair).issubset(fields)}
                missing = sorted(set(required_by_year) - available)
                if missing and not (st == "AK" and missing == [12]):
                    raise RuntimeError(f"{st}: DRA presidential years unavailable: {missing}")

                dsum = defaultdict(lambda: defaultdict(float))
                seen = joined = 0
                for row in reader:
                    geoid = str(row.get("GEOID") or "").strip()
                    seen += 1
                    cd = mapping.get(geoid)
                    if cd is None:
                        continue
                    joined += 1
                    for yr in available:
                        dk, rk = required_by_year[yr]
                        dsum[cd][f"{yr}d"] += impl.fnum(row.get(dk), 0.0) or 0.0
                        dsum[cd][f"{yr}r"] += impl.fnum(row.get(rk), 0.0) or 0.0
                if seen and joined / seen < 0.995:
                    raise RuntimeError(f"{st}: DRA/Census GEOID join only {joined}/{seen}")

                for cd, vals in dsum.items():
                    rc = impl.district_code(st, cd)
                    if not rc:
                        continue
                    margins = {}
                    for yr, key in ((12, "earliest"), (16, "middle"), (20, "latest")):
                        if st == "AK" and yr == 12:
                            d, r = ak12
                        else:
                            d, r = vals[f"{yr}d"], vals[f"{yr}r"]
                        if d + r <= 0:
                            raise RuntimeError(f"{rc}: empty {yr} presidential denominator")
                        margins[key] = 100 * (d - r) / (d + r)
                    districts[rc] = margins

    if len(districts) != 435:
        raise RuntimeError(f"expected 435 redistricted House structural priors, got {len(districts)}")
    return districts


impl.match_incumbents = strict_match_incumbents
impl.structural_priors = strict_structural_priors

if __name__ == "__main__":
    impl.main()
