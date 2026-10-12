#!/usr/bin/env python3
"""Read-only availability diagnostics for public MIDTERM SIGNALS sources."""
from __future__ import annotations
import json
import sys
import urllib.error
import urllib.request

SOURCES = [
    ("track_generic", "https://www.trackthevote.net/generic-ballot"),
    ("track_senate", "https://www.trackthevote.net/senate"),
    ("track_home", "https://www.trackthevote.net/"),
    ("cook_house_ratings", "https://www.cookpolitical.com/ratings/house-race-ratings"),
    ("cook_senate_ratings", "https://www.cookpolitical.com/ratings/senate-race-ratings"),
    ("house_history", "https://history.house.gov/Institution/Election-Statistics/Election-Statistics/"),
]

def check(name, url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "MIDTERM-SIGNALS-source-health/0.1 (+https://github.com/MusicOfScience/midterm-signals)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status = int(response.status)
            return {"id": name, "url": url, "status": status, "health": "ok" if status < 400 else "degraded"}
    except urllib.error.HTTPError as exc:
        health = "restricted" if exc.code in (401, 403) else "degraded"
        return {"id": name, "url": url, "status": exc.code, "health": health}
    except Exception as exc:
        return {"id": name, "url": url, "status": None, "health": "degraded", "error": type(exc).__name__}

results = [check(*source) for source in SOURCES]
print(json.dumps({"sources": results}, indent=2))
if all(r["health"] == "degraded" for r in results): sys.exit("all public source routes degraded")
