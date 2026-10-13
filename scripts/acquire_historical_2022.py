#!/usr/bin/env python3
"""Acquire and normalize the 2022 Model Lab corpus.

This starts in fail-closed probe mode. It verifies the actual block-level
schema, Census 118th-Congress geography, dated FiveThirtyEight roster/poll
schemas, and MEDSL result schema before national normalization is allowed to
run. No result data are used for prediction and no historical score is
produced in probe mode.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from collections import Counter

UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"
DRA_COMMIT = "7f29db811844c02ab726ffec9bb34865c73ef342"
DRA_REPO = "dra2020/block_data"
CENSUS_BEF = "https://www2.census.gov/programs-surveys/decennial/rdo/mapping-files/2023/118-congressional-district-bef/cd118.zip"
FTE_FORECAST_MIRROR_COMMIT = "83f2c9867f319b921fa10ad04bc256d8106bc8f4"
FTE_FORECAST_MIRROR = f"https://raw.githubusercontent.com/stephensond/election-night-2022/{FTE_FORECAST_MIRROR_COMMIT}/input"
FTE_POLLS = "https://projects.fivethirtyeight.com/polls-page/data"
MEDSL_COMMIT = "a8126c5790b8d1f438a3e63c3506cdcdc7406d9f"
MEDSL_AL = f"https://raw.githubusercontent.com/MEDSL/2022-elections-official/{MEDSL_COMMIT}/individual_states/2022-al-local-precinct-general.zip"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if not data:
        raise RuntimeError(f"empty source: {url}")
    return data


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def github_json(url: str):
    return json.loads(fetch(url).decode("utf-8"))


def latest_election_md(state: str) -> tuple[str, str]:
    tree = github_json(f"https://api.github.com/repos/{DRA_REPO}/git/trees/{DRA_COMMIT}?recursive=1")
    pat = re.compile(rf"^2020_Geography/{state}/Election_Data_Block_{state}\.v(\d+)\.md$")
    matches = []
    for item in tree.get("tree", []):
        m = pat.match(item.get("path", ""))
        if m:
            matches.append((int(m.group(1)), item["path"]))
    if not matches:
        raise RuntimeError(f"no DRA election block reference for {state}")
    _, path = max(matches)
    md = fetch(f"https://raw.githubusercontent.com/{DRA_REPO}/{DRA_COMMIT}/{path}").decode("utf-8")
    m = re.search(r"https://data\.dra2020\.net/[^)\s]+\.zip", md)
    if not m:
        raise RuntimeError(f"no download URL in {path}")
    return path, m.group(0)


def zip_csv_header(data: bytes) -> tuple[list[str], list[str], str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        csvs = [n for n in names if n.lower().endswith(".csv") and not n.startswith("__MACOSX/")]
        if not csvs:
            raise RuntimeError(f"zip has no CSV: {names[:20]}")
        name = csvs[0]
        with z.open(name) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="strict", newline="")
            header = next(csv.reader(text))
    return names, header, name


def zip_csv_rows(data: bytes, limit: int | None = None) -> tuple[list[str], list[dict], str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        csvs = [n for n in names if n.lower().endswith(".csv") and not n.startswith("__MACOSX/")]
        if not csvs:
            raise RuntimeError(f"zip has no CSV: {names[:20]}")
        name = csvs[0]
        raw = z.read(name)
    rows = []
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))
    for i, row in enumerate(reader):
        rows.append(row)
        if limit is not None and i + 1 >= limit:
            break
    return names, rows, name


def csv_probe(data: bytes, sample: int = 6) -> dict:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        rows.append(row)
        if i + 1 >= sample:
            break
    return {"columns": reader.fieldnames or [], "sample": rows}


def csv_cycle_count(data: bytes, cycle: str = "2022") -> tuple[list[str], int, list[dict]]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    count = 0
    sample = []
    for row in reader:
        if str(row.get("cycle") or "").strip() == cycle:
            count += 1
            if len(sample) < 4:
                sample.append(row)
    return reader.fieldnames or [], count, sample


def bef_header(data: bytes) -> tuple[list[str], list[str], str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        candidates = [n for n in names if "national" in n.lower() and not n.endswith("/")]
        if not candidates:
            candidates = [n for n in names if n.lower().endswith((".txt", ".csv")) and not n.endswith("/")]
        if not candidates:
            raise RuntimeError(f"Census BEF zip has no tabular file: {names[:30]}")
        name = candidates[0]
        raw = z.read(name)
    sample = raw[:8192].decode("utf-8-sig", errors="replace")
    first = sample.splitlines()[0]
    delim = "|" if first.count("|") >= first.count(",") else ","
    header = next(csv.reader([first], delimiter=delim))
    return names, header, name, delim


def probe_structural() -> dict:
    md_path, dra_url = latest_election_md("AL")
    dra = fetch(dra_url)
    dra_names, dra_header, dra_csv = zip_csv_header(dra)
    required = [
        "E_12_PRES_Dem", "E_12_PRES_Rep",
        "E_16_PRES_Dem", "E_16_PRES_Rep",
        "E_20_PRES_Dem", "E_20_PRES_Rep",
    ]
    missing = [x for x in required if x not in dra_header]
    geoid_candidates = [x for x in dra_header if "geoid" in x.lower() or "block" in x.lower()]
    if missing:
        raise RuntimeError(f"DRA Alabama missing required fields: {missing}")
    if geoid_candidates != ["GEOID"]:
        raise RuntimeError(f"unexpected DRA block identifier: {geoid_candidates}")

    bef = fetch(CENSUS_BEF)
    bef_names, bef_cols, bef_file, bef_delim = bef_header(bef)
    if not {"GEOID", "CDFP"}.issubset(bef_cols):
        raise RuntimeError(f"Census BEF missing required columns: {bef_cols}")
    return {
        "state": "AL",
        "dra_commit": DRA_COMMIT,
        "dra_reference": md_path,
        "dra_url": dra_url,
        "dra_sha256": sha(dra),
        "dra_zip_members": dra_names,
        "dra_csv": dra_csv,
        "dra_columns": dra_header,
        "dra_geoid_candidates": geoid_candidates,
        "required_presidential_fields": required,
        "census_bef_url": CENSUS_BEF,
        "census_bef_sha256": sha(bef),
        "census_zip_member_count": len(bef_names),
        "census_candidate_file": bef_file,
        "census_columns": bef_cols,
        "census_delimiter": bef_delim,
    }


def probe_fte() -> dict:
    outputs = {}
    for name in ("house_district_toplines_2022.csv", "senate_state_toplines_2022.csv"):
        url = f"{FTE_FORECAST_MIRROR}/{name}"
        data = fetch(url)
        p = csv_probe(data, sample=5)
        required = {"cycle", "branch", "district", "forecastdate", "expression", "name_D1", "name_R1"}
        missing = sorted(required - set(p["columns"]))
        if missing:
            raise RuntimeError(f"{name} missing roster columns: {missing}")
        outputs[name] = {"url": url, "sha256": sha(data), "bytes": len(data), **p}

    for name in ("house_polls_historical.csv", "senate_polls_historical.csv", "generic_ballot_polls_historical.csv"):
        url = f"{FTE_POLLS}/{name}"
        data = fetch(url)
        cols, count, sample = csv_cycle_count(data)
        if count == 0:
            raise RuntimeError(f"{name} contains no cycle=2022 rows")
        outputs[name] = {"url": url, "sha256": sha(data), "bytes": len(data), "columns": cols, "cycle_2022_rows": count, "sample": sample}
    outputs["forecast_mirror_commit"] = FTE_FORECAST_MIRROR_COMMIT
    return outputs


def probe_medsl() -> dict:
    data = fetch(MEDSL_AL)
    names, rows, member = zip_csv_rows(data, limit=4000)
    if not rows:
        raise RuntimeError("MEDSL Alabama archive contains no rows")
    cols = list(rows[0])
    required = {"office", "party_simplified", "votes", "candidate", "district", "stage", "special", "state_po", "date"}
    missing = sorted(required - set(cols))
    if missing:
        raise RuntimeError(f"MEDSL Alabama missing result columns: {missing}")
    federal = [r for r in rows if (r.get("office") or "").upper() in {"US HOUSE", "US SENATE"}]
    signature = Counter(((r.get("office") or ""), (r.get("district") or ""), (r.get("stage") or ""), (r.get("special") or ""), (r.get("date") or "")) for r in federal)
    examples = []
    seen = set()
    for row in federal:
        key = (row.get("office"), row.get("district"), row.get("stage"), row.get("special"), row.get("date"), row.get("candidate"), row.get("party_simplified"))
        if key in seen:
            continue
        seen.add(key)
        examples.append({k: row.get(k) for k in ("office", "district", "stage", "special", "date", "candidate", "party_simplified", "mode", "votes")})
        if len(examples) >= 12:
            break
    return {
        "commit": MEDSL_COMMIT,
        "url": MEDSL_AL,
        "sha256": sha(data),
        "bytes": len(data),
        "zip_members": names,
        "csv_member": member,
        "columns": cols,
        "federal_signature_examples": [{"signature": list(k), "rows_in_probe": v} for k, v in signature.most_common(12)],
        "federal_row_examples": examples,
    }


def probe() -> None:
    print(json.dumps({
        "structural": probe_structural(),
        "fivethirtyeight": probe_fte(),
        "medsl": probe_medsl(),
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if not args.probe:
        raise SystemExit("2022 admission is fail-closed until the source probe passes; run with --probe")
    probe()


if __name__ == "__main__":
    main()
