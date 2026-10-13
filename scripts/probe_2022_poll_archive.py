#!/usr/bin/env python3
"""Find and verify election-week Wayback captures of FiveThirtyEight 2022 polls."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.parse
import urllib.request

UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"
BASE = "https://projects.fivethirtyeight.com/polls-page/data"
FILES = ("house_polls.csv", "senate_polls.csv", "generic_ballot_polls.csv")
CUTOFF = "20221109000000"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if not data:
        raise RuntimeError(f"empty response: {url}")
    return data


def capture_for(original: str) -> dict:
    params = urllib.parse.urlencode({
        "url": original,
        "from": "20221101",
        "to": "20221115",
        "output": "json",
        "fl": "timestamp,original,statuscode,digest,length",
        "filter": "statuscode:200",
        "collapse": "digest",
    })
    cdx = f"https://web.archive.org/cdx/search/cdx?{params}"
    rows = json.loads(fetch(cdx).decode("utf-8"))
    if len(rows) < 2:
        raise RuntimeError(f"no election-week Wayback captures for {original}")
    header = rows[0]
    items = [dict(zip(header, r)) for r in rows[1:]]
    before = [x for x in items if x["timestamp"] <= CUTOFF]
    chosen = max(before or items, key=lambda x: x["timestamp"] if before else "0") if before else min(items, key=lambda x: x["timestamp"])
    timestamp = chosen["timestamp"]
    archive = f"https://web.archive.org/web/{timestamp}id_/{original}"
    data = fetch(archive)
    text = data.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(text))
    count = 0
    sample = []
    for row in reader:
        if str(row.get("cycle") or "").strip() == "2022":
            count += 1
            if len(sample) < 3:
                sample.append(row)
    if count == 0:
        raise RuntimeError(f"Wayback capture has no cycle=2022 rows: {archive}")
    return {
        "original": original,
        "cdx": cdx,
        "capture": archive,
        "timestamp": timestamp,
        "wayback_digest": chosen.get("digest"),
        "wayback_length": chosen.get("length"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "columns": reader.fieldnames or [],
        "cycle_2022_rows": count,
        "sample": sample,
    }


def main() -> None:
    out = {}
    for name in FILES:
        out[name] = capture_for(f"{BASE}/{name}")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
