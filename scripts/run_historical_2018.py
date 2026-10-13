#!/usr/bin/env python3
"""Run the 2018 historical acquisition with audited MEDSL state priors.

FEC is the sole authority for the frozen national presidential centring
constants. MEDSL is used only to reconstruct state two-party D-R margins for
Senate structural priors. Its archived candidate totals differ slightly from
later certified FEC national totals, so admission checks completeness and a
broad sanity bound rather than asserting false byte-level equivalence.
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
        if len(by_state) != 51:
            raise RuntimeError(f"Expected 51 presidential jurisdictions in {year}, got {len(by_state)}")
        incomplete = [st for st, values in by_state.items() if not values["DEM"] or not values["REP"] or not values["TOTAL"]]
        if incomplete:
            raise RuntimeError(f"Incomplete MEDSL presidential returns {year}: {incomplete}")
        d = sum(v["DEM"] for v in by_state.values())
        r = sum(v["REP"] for v in by_state.values())
        total = sum(v["TOTAL"] for v in by_state.values())
        national[year] = 100 * (d - r) / total
        # This is a sanity guard only. FEC, not MEDSL, supplies the model's
        # national centring constant; archived source revisions can differ.
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


acquisition.presidential_margins = presidential_margins

if __name__ == "__main__":
    acquisition.main()
