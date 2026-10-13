#!/usr/bin/env python3
"""Strict entrypoint for the 2022 historical admission.

The source normalizer is kept separate from this admission-policy guard so a
name-matching correction cannot alter the election-data transformations.
"""
from __future__ import annotations

from collections import defaultdict

import run_historical_2022 as impl


def strict_match_incumbents(row: dict, chamber: str, incumbents: dict) -> tuple[str, list[str], bool]:
    """Match incumbents without surname-only false positives.

    Exact normalized aliases win. The fallback requires a surname that is
    unique among same-state incumbents *and* the candidate and incumbent alias
    to share a first initial. This admits common nickname/full-name variants
    (Mike/Michael, Katie/Katherine) while rejecting cases such as Matt Jacobs
    being confused with Sara Jacobs.
    """
    st = row["_code"][:2]
    term_type = "rep" if chamber == "house" else "sen"
    named = [(n, "DEM") for n in impl.names(row, impl.D_KEYS)] + [(n, "REP") for n in impl.names(row, impl.R_KEYS)]
    matched = []
    pool = incumbents.get((term_type, st), [])
    surname_freq = defaultdict(int)
    for inc in pool:
        seen = set()
        for alias in inc["aliases"]:
            bits = alias.split()
            if bits:
                seen.add(bits[-1])
        for s in seen:
            surname_freq[s] += 1

    for candidate, side in named:
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
            nm, par = next(iter(uniq))
            if par != side:
                raise RuntimeError(f"incumbent party mismatch {row['_code']}: {candidate} {side} vs {nm} {par}")
            matched.append((nm, par))
        elif len(uniq) > 1:
            return "", [x[0] for x in sorted(uniq)], True

    parties = {p for _, p in matched}
    ambiguous = len(parties) > 1
    return (next(iter(parties)) if len(parties) == 1 else ""), [n for n, _ in matched], ambiguous


impl.match_incumbents = strict_match_incumbents

if __name__ == "__main__":
    impl.main()
