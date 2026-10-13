#!/usr/bin/env python3
"""Inspect difficult 2022 official-result cases before admitting outcomes."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from collections import defaultdict

UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"
COMMIT = "a8126c5790b8d1f438a3e63c3506cdcdc7406d9f"
BASE = f"https://raw.githubusercontent.com/MEDSL/2022-elections-official/{COMMIT}/individual_states"
STATES = ("ak", "ok", "al")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if not data:
        raise RuntimeError(f"empty source: {url}")
    return data


def read_zip(data: bytes) -> tuple[str, list[dict]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX/")]
        if not csvs:
            raise RuntimeError(f"no CSV in result zip: {z.namelist()[:20]}")
        name = csvs[0]
        raw = z.read(name)
    text = raw.decode("utf-8-sig", errors="replace")
    return name, list(csv.DictReader(io.StringIO(text)))


def summarize(state: str) -> dict:
    url = f"{BASE}/2022-{state}-local-precinct-general.zip"
    data = fetch(url)
    member, rows = read_zip(data)
    if not rows:
        raise RuntimeError(f"{state}: empty result table")
    required = {"office", "party_simplified", "votes", "candidate", "district", "stage", "special", "state_po", "date", "mode", "precinct"}
    missing = sorted(required - set(rows[0]))
    if missing:
        raise RuntimeError(f"{state}: missing columns {missing}")

    federal = [r for r in rows if (r.get("office") or "").upper() in {"US HOUSE", "US SENATE"}]
    races: dict[tuple, list[dict]] = defaultdict(list)
    for r in federal:
        key = (
            r.get("office", ""), r.get("district", ""), r.get("stage", ""),
            r.get("special", ""), r.get("date", ""),
        )
        races[key].append(r)

    details = []
    for key, group in sorted(races.items()):
        cand_votes: dict[tuple[str, str], int] = defaultdict(int)
        modes = set()
        precincts = set()
        for r in group:
            modes.add(r.get("mode", ""))
            precincts.add(r.get("precinct", ""))
            try:
                v = int(float(r.get("votes") or 0))
            except ValueError:
                raise RuntimeError(f"{state}: nonnumeric votes in {key}: {r.get('votes')!r}")
            cand_votes[((r.get("candidate") or "").strip(), (r.get("party_simplified") or "").strip())] += v
        ranked = sorted(
            ({"candidate": c, "party": p, "votes_sum": v} for (c, p), v in cand_votes.items()),
            key=lambda x: (-x["votes_sum"], x["candidate"]),
        )
        details.append({
            "identity": {"office": key[0], "district": key[1], "stage": key[2], "special": key[3], "date": key[4]},
            "row_count": len(group),
            "precinct_count": len(precincts),
            "modes": sorted(modes),
            "candidate_totals_by_raw_sum": ranked[:12],
        })

    return {
        "url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "member": member,
        "federal_rows": len(federal),
        "race_signatures": details,
    }


def main() -> None:
    out = {s.upper(): summarize(s) for s in STATES}
    ak = out["AK"]["race_signatures"]
    ok = out["OK"]["race_signatures"]
    # Fail closed if the difficult cases are not distinguishable in metadata.
    if not any(x["identity"]["office"] == "US HOUSE" for x in ak):
        raise RuntimeError("Alaska House race absent")
    if not any(x["identity"]["office"] == "US SENATE" for x in ak):
        raise RuntimeError("Alaska Senate race absent")
    ok_sen = [x for x in ok if x["identity"]["office"] == "US SENATE"]
    if len(ok_sen) < 2:
        raise RuntimeError(f"Oklahoma dual Senate contests not distinguishable: {len(ok_sen)} signatures")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
