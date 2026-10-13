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
# States with a single U.S. House district in 2022. If DRA omits an older
# presidential year for one of these states, the statewide result is exactly
# the congressional-district result, so no geographic interpolation is needed.
AT_LARGE_2022 = {"AK", "DE", "ND", "SD", "VT", "WY"}


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


def state_presidential_two_party() -> dict[str, dict[int, tuple[float, float]]]:
    """Return exact state D/R presidential totals for 2012 and 2016.

    These are used only as an at-large fallback where statewide and district
    geography are identical. The source is never used to remap multi-district
    states and therefore cannot smuggle current boundaries into older results.
    """
    data = impl.fetch("MEDSL 1976-2016 presidential state returns", MEDSL_PRES_URL)
    out: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        try:
            year = int(str(row.get("year") or ""))
        except ValueError:
            continue
        if year not in {2012, 2016}:
            continue
        st = str(row.get("state_po") or "").upper()
        if st not in AT_LARGE_2022:
            continue
        p = str(row.get("party") or "").strip().lower()
        votes = impl.fnum(row.get("candidatevotes"), 0.0) or 0.0
        if p.startswith("democrat"):
            out[st][year][0] += votes
        elif p.startswith("republican"):
            out[st][year][1] += votes

    clean: dict[str, dict[int, tuple[float, float]]] = {}
    for st in AT_LARGE_2022:
        clean[st] = {}
        for year in (2012, 2016):
            dem, rep = out[st][year]
            if dem <= 0 or rep <= 0:
                raise RuntimeError(f"MEDSL {st} {year} two-party vote unavailable: D={dem} R={rep}")
            clean[st][year] = (dem, rep)
    return clean


def strict_structural_priors() -> dict:
    """Aggregate 2012/2016/2020 presidential returns onto 118th districts.

    DRA block data is canonical for redistricted geography. For a 2022
    at-large state only, a missing older DRA presidential field may be replaced
    by the exact statewide MEDSL D/R total because statewide and district
    geography are identical. Missing 2020 data or missing data in any
    multi-district state fail closed. Census non-district placeholders are
    discarded before margin calculation; the final 435-district invariant
    ensures that no real congressional district can vanish silently.
    """
    refs = impl.latest_dra_refs()
    statewide = state_presidential_two_party()
    required_by_year = {
        12: ("E_12_PRES_Dem", "E_12_PRES_Rep"),
        16: ("E_16_PRES_Dem", "E_16_PRES_Rep"),
        20: ("E_20_PRES_Dem", "E_20_PRES_Rep"),
    }
    year_full = {12: 2012, 16: 2016, 20: 2020}

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

                allowed_missing = []
                if st in AT_LARGE_2022:
                    allowed_missing = [yr for yr in missing if yr in {12, 16}]
                disallowed = [yr for yr in missing if yr not in allowed_missing]
                if disallowed:
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

                # At-large states may have no rows accumulated for a missing
                # historical year, so enumerate the actual Census district IDs.
                cds = sorted({cd for cd in mapping.values() if impl.district_code(st, cd)})
                if st in AT_LARGE_2022 and len(cds) != 1:
                    raise RuntimeError(f"{st}: expected exactly one 2022 House district, got {cds}")

                for cd in cds:
                    vals = dsum[cd]
                    rc = impl.district_code(st, cd)
                    if not rc:
                        continue
                    margins = {}
                    for yr, key in ((12, "earliest"), (16, "middle"), (20, "latest")):
                        if yr in available:
                            d, r = vals[f"{yr}d"], vals[f"{yr}r"]
                        else:
                            full_year = year_full[yr]
                            if st not in AT_LARGE_2022 or full_year not in statewide[st]:
                                raise RuntimeError(f"{rc}: no lawful fallback for missing {full_year} presidential data")
                            d, r = statewide[st][full_year]
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
