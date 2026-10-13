#!/usr/bin/env python3
"""Run the 2018 historical acquisition with the audited MEDSL denominator fix.

MEDSL repeats each state's official totalvotes value on every presidential
candidate row. National D-R margins must therefore use that state total once,
not the sum of candidate rows, which can omit residual/write-in votes.
"""
from collections import defaultdict

import acquire_historical_2018 as acquisition


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
        d = sum(v["DEM"] for v in by_state.values())
        r = sum(v["REP"] for v in by_state.values())
        total = sum(v["TOTAL"] for v in by_state.values())
        if not d or not r or not total:
            raise RuntimeError(f"Missing presidential returns for {year}")
        national[year] = 100 * (d - r) / total
        for st, values in by_state.items():
            two_party = values["DEM"] + values["REP"]
            if two_party > 0:
                states[st][year] = 100 * (values["DEM"] - values["REP"]) / two_party
    for year, official in acquisition.FEC_NATIONAL_MARGINS.items():
        if abs(national[year] - official) > 0.08:
            raise RuntimeError(
                f"MEDSL/FEC national margin disagreement {year}: "
                f"{national[year]:.3f} vs {official:.2f}"
            )
    missing = [
        st for st, values in states.items()
        if st != "DC" and any(year not in values for year in (2008, 2012, 2016))
    ]
    if missing:
        raise RuntimeError(f"State presidential baseline incomplete: {missing}")
    return national, dict(states)


acquisition.presidential_margins = presidential_margins

if __name__ == "__main__":
    acquisition.main()
