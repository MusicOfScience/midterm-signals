#!/usr/bin/env python3
"""Acquire and normalize the 2022 Model Lab corpus.

This starts in fail-closed probe mode. It verifies the actual block-level
schema and Census 118th-Congress geography before national normalization is
allowed to run. No result data are opened and no historical score is produced
in probe mode.
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

UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"
DRA_COMMIT = "d631d7430242b40e4a35e761449b23062da56da9"  # placeholder is never fetched; see DRA_PIN below
DRA_PIN = "main"
DRA_REPO = "dra2020/block_data"
CENSUS_BEF = "https://www2.census.gov/programs-surveys/decennial/rdo/mapping-files/2023/118-congressional-district-bef/cd118.zip"


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


def resolve_dra_commit() -> str:
    obj = github_json(f"https://api.github.com/repos/{DRA_REPO}/commits/{DRA_PIN}")
    value = obj.get("sha") or ""
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise RuntimeError("could not resolve DRA commit")
    return value


def latest_election_md(commit: str, state: str) -> tuple[str, str]:
    tree = github_json(f"https://api.github.com/repos/{DRA_REPO}/git/trees/{commit}?recursive=1")
    pat = re.compile(rf"^2020_Geography/{state}/Election_Data_Block_{state}\.v(\d+)\.md$")
    matches = []
    for item in tree.get("tree", []):
        m = pat.match(item.get("path", ""))
        if m:
            matches.append((int(m.group(1)), item["path"]))
    if not matches:
        raise RuntimeError(f"no DRA election block reference for {state}")
    _, path = max(matches)
    md = fetch(f"https://raw.githubusercontent.com/{DRA_REPO}/{commit}/{path}").decode("utf-8")
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


def probe() -> None:
    commit = resolve_dra_commit()
    md_path, dra_url = latest_election_md(commit, "AL")
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
    if not geoid_candidates:
        raise RuntimeError("DRA Alabama exposes no obvious block identifier")

    bef = fetch(CENSUS_BEF)
    bef_names, bef_cols, bef_file, bef_delim = bef_header(bef)
    print(json.dumps({
        "state": "AL",
        "dra_commit": commit,
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
