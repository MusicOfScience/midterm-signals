#!/usr/bin/env python3
"""Run the 2018 historical acquisition with audited source-normalisation fixes.

FEC is the sole authority for the frozen national presidential centring
constants. MEDSL is used only to reconstruct state two-party D-R margins for
Senate structural priors. Its archived candidate totals differ slightly from
later certified FEC national totals, so admission checks completeness and a
broad sanity bound rather than asserting false byte-level equivalence.

Some historical MEDSL CSVs contain legacy Windows-1252 characters in candidate
names. Decoding therefore uses an explicit UTF-8 -> CP1252 -> Latin-1 fallback;
no numeric fields are altered by this text-encoding rule.

Some uncontested MEDSL House winners have party=NA. Their party is recovered
only by matching the winner's name to the pre-election FiveThirtyEight roster
already used for historical known-date reconstruction. Ambiguous or unmatched
fallbacks fail closed and every successful fallback is recorded in cycle.json.
"""
from collections import defaultdict
import csv
import io
import json
import re

import acquire_historical_2018 as acquisition


ROSTER_SIDE: dict[tuple[str, str], set[str]] = defaultdict(set)
ROSTER_SURNAME: dict[tuple[str, str], set[str]] = defaultdict(set)
RESULT_PARTY_FALLBACKS: list[dict] = []


def csv_rows(data: bytes) -> list[dict]:
    last_error = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return list(csv.DictReader(io.StringIO(data.decode(encoding))))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"Unable to decode historical CSV: {last_error}")


def canon_name(value: str | None) -> str:
    bits = re.findall(r"[A-Z0-9]+", str(value or "").upper())
    suffixes = {"JR", "SR", "II", "III", "IV"}
    bits = [bit for bit in bits if bit not in suffixes]
    # MEDSL generally stores FIRST LAST, but tolerate LAST, FIRST and initials
    # by using a sorted token signature after punctuation/suffix removal.
    return " ".join(sorted(bits))


def surname(value: str | None) -> str:
    bits = re.findall(r"[A-Z]+", str(value or "").upper())
    bits = [bit for bit in bits if bit not in {"JR", "SR", "II", "III", "IV"}]
    return bits[-1] if bits else ""


def capture_forecast_versions(forecast_rows, chamber, district_structural, state_structural):
    rows = ORIGINAL_FORECAST_VERSIONS(forecast_rows, chamber, district_structural, state_structural)
    for row in rows:
        code = row["race_code"]
        for field, side in (("dem_name", "DEM"), ("rep_name", "REP")):
            name = row.get(field) or ""
            if name:
                ROSTER_SIDE[(code, canon_name(name))].add(side)
                ROSTER_SURNAME[(code, surname(name))].add(side)
        ind = row.get("ind_name") or ""
        caucus = row.get("ind_caucus") or ""
        if ind and caucus in {"DEM", "REP"}:
            ROSTER_SIDE[(code, canon_name(ind))].add(caucus)
            ROSTER_SURNAME[(code, surname(ind))].add(caucus)
    return rows


def roster_side(code: str, winner_name: str) -> str | None:
    exact = ROSTER_SIDE.get((code, canon_name(winner_name)), set())
    if len(exact) == 1:
        return next(iter(exact))
    by_surname = ROSTER_SURNAME.get((code, surname(winner_name)), set())
    if len(by_surname) == 1:
        return next(iter(by_surname))
    return None


def build_results(house_rows: list[dict], senate_rows: list[dict], race_codes: set[str]) -> list[dict]:
    candidates: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"votes": 0.0, "parties": set()})
    )
    for chamber, source_rows in (("house", house_rows), ("senate", senate_rows)):
        for row in source_rows:
            if str(row.get("year") or "") != "2018":
                continue
            if str(row.get("stage") or "").strip().upper() not in {"", "GEN"}:
                continue
            if chamber == "house":
                code = acquisition.district_code(
                    row.get("state_po") or row.get("state"), row.get("district")
                )
            else:
                st = acquisition.state_po(row.get("state_po") or row.get("state"))
                special = str(row.get("special") or "").upper() == "TRUE"
                code = f"{st}-S{2 if special else 1}" if st else ""
            if code not in race_codes:
                continue
            name = str(row.get("candidate") or "").strip().upper()
            if not name:
                continue
            candidates[code][name]["votes"] += acquisition.fnum(row.get("candidatevotes")) or 0.0
            candidates[code][name]["parties"].add(acquisition.party(row.get("party")))

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
        elif code in acquisition.DEM_ALIGNED_INDEPENDENTS:
            side = "DEM"
        else:
            side = roster_side(code, winner_name)
            if side not in {"DEM", "REP"}:
                raise RuntimeError(
                    f"Cannot map winning party for {code}: {winner_name} {sorted(parties)}; "
                    "pre-election roster match unavailable or ambiguous"
                )
            RESULT_PARTY_FALLBACKS.append({
                "race_code": code,
                "winner_name": winner_name,
                "medsl_parties": sorted(parties),
                "resolved_side": side,
                "resolution_source": "pre-election FiveThirtyEight historical roster",
            })
        result.append({"race_code": code, "winner_party": side})
    return result


def presidential_margins(president_rows: list[dict]) -> tuple[dict[int, float], dict[str, dict[int, float]]]:
    national = {}
    states: dict[str, dict[int, float]] = defaultdict(dict)
    for year in (2008, 2012, 2016):
        by_state = defaultdict(lambda: {"DEM": 0.0, "REP": 0.0, "TOTAL": 0.0})
        for row in president_rows:
            if str(row.get("year") or "") != str(year):
                continue
            st = acquisition.state_po(row.get("state_po") or row.get("state"))
            votes = acquisition.fnum(row.get("candidatevotes")) or 0.0
            totalvotes = acquisition.fnum(row.get("totalvotes")) or 0.0
            if not st:
                continue
            by_state[st]["TOTAL"] = max(by_state[st]["TOTAL"], totalvotes)
            side = acquisition.party(row.get("party"))
            if side in {"DEM", "REP"}:
                by_state[st][side] += votes
        if len(by_state) != 51:
            raise RuntimeError(f"Expected 51 presidential jurisdictions in {year}, got {len(by_state)}")
        incomplete = [
            st for st, values in by_state.items()
            if not values["DEM"] or not values["REP"] or not values["TOTAL"]
        ]
        if incomplete:
            raise RuntimeError(f"Incomplete MEDSL presidential returns {year}: {incomplete}")
        d = sum(v["DEM"] for v in by_state.values())
        r = sum(v["REP"] for v in by_state.values())
        total = sum(v["TOTAL"] for v in by_state.values())
        national[year] = 100 * (d - r) / total
        if abs(national[year] - acquisition.FEC_NATIONAL_MARGINS[year]) > 0.5:
            raise RuntimeError(
                f"MEDSL presidential archive is implausibly far from FEC in {year}: "
                f"{national[year]:.3f} vs {acquisition.FEC_NATIONAL_MARGINS[year]:.2f}"
            )
        for st, values in by_state.items():
            two_party = values["DEM"] + values["REP"]
            states[st][year] = 100 * (values["DEM"] - values["REP"]) / two_party
    missing = [
        st for st, values in states.items()
        if any(year not in values for year in (2008, 2012, 2016))
    ]
    if missing:
        raise RuntimeError(f"State presidential baseline incomplete: {missing}")
    return national, dict(states)


ORIGINAL_FORECAST_VERSIONS = acquisition.forecast_versions
acquisition.csv_rows = csv_rows
acquisition.presidential_margins = presidential_margins
acquisition.forecast_versions = capture_forecast_versions
acquisition.build_results = build_results

if __name__ == "__main__":
    acquisition.main()
    config_path = acquisition.OUT / "cycle.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.setdefault("admission", {})["result_party_fallbacks"] = RESULT_PARTY_FALLBACKS
    config["admission"].setdefault("transformations", {})["missing_result_party"] = (
        "When MEDSL party is neither DEM nor REP, the winner must match an unambiguous "
        "pre-election historical roster candidate; otherwise admission fails."
    )
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
