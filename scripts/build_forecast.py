#!/usr/bin/env python3
"""Build MIDTERM SIGNALS' 2026 House/Senate baseline forecast.

This model deliberately consumes *inputs*, not another forecaster's probabilities.
The upstream data mirror is ElectIndex's public 2026 input repository.  We pin
all reads to one upstream git SHA, then apply our own documented transformation,
poll aggregation and Monte Carlo simulation.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import statistics
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "data" / "forecast.json"
STATUS = ROOT / "public" / "data" / "status.json"
HIST = ROOT / "public" / "data" / "history"
UPSTREAM_REPO = "ElectIndex/26_us_forecast_data"
API_COMMIT = f"https://api.github.com/repos/{UPSTREAM_REPO}/commits/main"
RAW = "https://raw.githubusercontent.com/{repo}/{sha}/{name}"
USER_AGENT = "MIDTERM-SIGNALS/0.2 (+https://github.com/MusicOfScience/midterm-signals)"
ELECTION_DATE = date(2026, 11, 3)
NAT_PRES = {2016: 2.09, 2020: 4.46, 2024: -1.47}
CURRENT_SENATE = {"DEM": 47, "REP": 53}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def csv_rows(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        v = row.get(key, "")
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def parse_day(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def surname(name: str) -> str:
    if not name or name.startswith("("):
        return ""
    bits = [b.strip(".,'") for b in name.lower().replace("-", " ").split()]
    return bits[-1] if bits else ""


def candidate_match(poll_name: str, race_name: str) -> bool:
    if not poll_name or not race_name:
        return False
    p = poll_name.lower()
    if "generic" in p:
        return True
    s = surname(race_name)
    return bool(s and s in p)


def poll_weight(row: dict[str, str], latest: date, half_life: float) -> float:
    d = parse_day(row.get("end_date", ""))
    if not d:
        return 0.0
    age = max(0, (latest - d).days)
    rating = clamp(f(row, "rating", 1.3), 0.75, 3.0)
    n = max(250.0, f(row, "n", 800.0))
    sponsor = row.get("lean", "").strip().upper()
    sponsor_mult = 0.68 if sponsor in {"D", "R"} else 1.0
    return math.exp(-math.log(2) * age / half_life) * (rating / 1.5) ** 1.15 * math.sqrt(n / 1000.0) * sponsor_mult


def aggregate_gcb(rows: list[dict[str, str]], asof: date) -> tuple[float, list[dict], int]:
    usable = []
    for r in rows:
        d = parse_day(r.get("end_date", ""))
        if d and d <= asof and (asof - d).days <= 35:
            usable.append(r)
    if not usable:
        raise RuntimeError("No recent generic-ballot polls")
    latest = max(parse_day(r["end_date"]) for r in usable if parse_day(r["end_date"]))
    num = den = 0.0
    for r in usable:
        w = poll_weight(r, latest, 11.0)
        num += w * (f(r, "dem") - f(r, "rep"))
        den += w
    avg = num / den
    recent = sorted(usable, key=lambda r: r["end_date"], reverse=True)[:14]
    shown = [{
        "pollster": r["pollster"], "end_date": r["end_date"],
        "dem": round(f(r, "dem"), 1), "rep": round(f(r, "rep"), 1),
        "margin": round(f(r, "dem") - f(r, "rep"), 1),
        "n": int(f(r, "n", 0)), "rating": round(f(r, "rating", 0), 1),
        "sponsor_lean": r.get("lean", "") or None,
    } for r in recent]
    return avg, shown, len(usable)


def race_poll_average(rows: list[dict[str, str]], race: dict[str, str], asof: date) -> tuple[float | None, float, int, str | None]:
    code = race["race_code"]
    chosen = []
    for r in rows:
        if r.get("race_code") != code:
            continue
        d = parse_day(r.get("end_date", ""))
        if not d or d > asof or (asof - d).days > 55:
            continue
        if race.get("dem_name") and not candidate_match(r.get("dem_name", ""), race.get("dem_name", "")):
            continue
        if race.get("rep_name") and not candidate_match(r.get("rep_name", ""), race.get("rep_name", "")):
            continue
        chosen.append(r)
    if not chosen:
        return None, 0.0, 0, None
    latest = max(parse_day(r["end_date"]) for r in chosen if parse_day(r["end_date"]))
    num = den = 0.0
    for r in chosen:
        w = poll_weight(r, latest, 13.0)
        num += w * f(r, "margin")
        den += w
    if not den:
        return None, 0.0, 0, None
    avg = num / den
    blend = clamp(0.27 * math.sqrt(len(chosen)), 0.20, 0.86)
    freshness = math.exp(-max(0, (asof - latest).days) / 28.0)
    blend *= 0.75 + 0.25 * freshness
    return avg, blend, len(chosen), latest.isoformat()


def rating(p: float) -> str:
    q = max(p, 1 - p)
    side = "D" if p >= 0.5 else "R"
    if q < 0.55:
        return "Toss-up"
    if q < 0.70:
        return f"Lean {side}"
    if q < 0.90:
        return f"Likely {side}"
    return f"Safe {side}"


def relative_lean(h: dict[str, str]) -> float:
    m16 = f(h, "margin_2016") - NAT_PRES[2016]
    m20 = f(h, "margin_2020") - NAT_PRES[2020]
    m24 = f(h, "margin_2024") - NAT_PRES[2024]
    return 0.05 * m16 + 0.20 * m20 + 0.75 * m24


def race_model(race: dict[str, str], hist: dict[str, dict[str, str]], poll_rows: list[dict[str, str]], gcb: float, asof: date) -> dict:
    code = race["race_code"]
    h = hist.get(code)
    if not h:
        h = hist.get(race.get("state", ""))
    if not h:
        raise RuntimeError(f"No historical baseline for {code}")
    lean = relative_lean(h)
    inc = race.get("incumbent_party", "").upper()
    inc_adj = 1.0 if inc == "DEM" else -1.0 if inc == "REP" else 0.0
    if race.get("race_type") == "senate":
        inc_adj *= 1.15
    prior = lean + gcb + inc_adj
    poll_margin, pweight, pcount, plast = race_poll_average(poll_rows, race, asof)
    margin = prior if poll_margin is None else (1 - pweight) * prior + pweight * poll_margin
    dem_name = race.get("dem_name", "")
    rep_name = race.get("rep_name", "")
    ind_name = race.get("ind_name", "")
    ind_caucus = race.get("ind_caucus", "").upper()
    aligned_ind = bool(ind_name and ind_caucus == "DEM" and (not dem_name or dem_name.startswith("(No Democrat)")))
    dem_display = ind_name if aligned_ind else dem_name
    same_party = race.get("same_party", "").upper()
    if same_party == "DEM":
        p_dem = 0.999; margin = 50.0
    elif same_party == "REP":
        p_dem = 0.001; margin = -50.0
    elif (not dem_name or dem_name.startswith("(No Democrat)")) and not aligned_ind:
        p_dem = 0.001; margin = min(margin, -35.0)
    elif not rep_name or rep_name.startswith("(No Republican)"):
        p_dem = 0.999; margin = max(margin, 35.0)
    else:
        base_sigma = 6.3 if race.get("race_type") == "house" else 7.2
        sigma = max(3.1, base_sigma * (1 - 0.42 * pweight))
        p_dem = clamp(normal_cdf(margin / sigma), 0.001, 0.999)
    dshare = clamp(50 + margin / 2, 1.0, 99.0)
    return {
        "race_code": code, "race_type": race["race_type"], "state": race.get("state"), "district": race.get("district"),
        "dem_candidate": dem_display or None, "rep_candidate": rep_name or None, "incumbent_party": inc or None,
        "seat_holder": race.get("seat_holder") or None, "dem_probability": round(p_dem, 4), "rep_probability": round(1-p_dem, 4),
        "forecast_margin_d_minus_r": round(margin, 2), "dem_two_party_vote": round(dshare, 1), "rep_two_party_vote": round(100-dshare, 1),
        "rating": rating(p_dem), "relative_partisan_lean_d_minus_r": round(lean, 2), "prior_margin": round(prior, 2),
        "poll_average_margin": round(poll_margin, 2) if poll_margin is not None else None, "poll_weight": round(pweight, 3),
        "poll_count": pcount, "latest_race_poll": plast, "presidential_margin_2024": round(f(h, "margin_2024"), 2),
        "aligned_independent": aligned_ind, "rcv": race.get("rcv", "").lower() == "true", "three_way": race.get("threeway", "").lower() == "true",
        "same_party": same_party or None,
    }


def quantile(vals: list[int], q: float) -> int:
    vals = sorted(vals)
    if not vals: return 0
    return vals[int(round((len(vals)-1)*q))]


def simulate(house: list[dict], senate: list[dict], senate_up_holders: dict[str, int], n: int = 30000) -> tuple[dict, dict]:
    rng = random.Random(20261103)
    house_counts=[]; senate_counts=[]; house_control=senate_control=0
    fixed_d = CURRENT_SENATE["DEM"] - senate_up_holders.get("DEM", 0)
    for _ in range(n):
        national_house=rng.gauss(0,2.7); national_senate=rng.gauss(0,2.4)
        hd=sum(1 for r in house if r["forecast_margin_d_minus_r"] + national_house + rng.gauss(0,4.7) > 0)
        sd=fixed_d
        for r in senate:
            m=r["forecast_margin_d_minus_r"] + national_senate + rng.gauss(0,5.0)
            if r.get("same_party") == "DEM": sd += 1
            elif r.get("same_party") == "REP": pass
            elif m > 0: sd += 1
        house_counts.append(hd); senate_counts.append(sd)
        house_control += hd >= 218; senate_control += sd >= 51
    hmean=statistics.fmean(house_counts); smean=statistics.fmean(senate_counts)
    return ({"dem_control_probability":round(house_control/n,4),"rep_control_probability":round(1-house_control/n,4),"expected_dem_seats":round(hmean,1),"expected_rep_seats":round(435-hmean,1),"dem_seats_80_interval":[quantile(house_counts,.10),quantile(house_counts,.90)],"simulations":n,"control_threshold_dem":218},
            {"dem_control_probability":round(senate_control/n,4),"rep_control_probability":round(1-senate_control/n,4),"expected_dem_seats":round(smean,1),"expected_rep_seats":round(100-smean,1),"dem_seats_80_interval":[quantile(senate_counts,.10),quantile(senate_counts,.90)],"simulations":n,"control_threshold_dem":51,"fixed_not_up_dem_seats":fixed_d})


def main() -> None:
    now=datetime.now(timezone.utc); asof=min(now.date(),ELECTION_DATE)
    commit_meta=json.loads(fetch(API_COMMIT)); sha=commit_meta["sha"]
    names=["races.csv","historical.csv","gcb_polls.csv","race_polls.csv"]
    raw={name:fetch(RAW.format(repo=UPSTREAM_REPO,sha=sha,name=name)) for name in names}
    inputs_hash=hashlib.sha256(b"".join(raw[n] for n in names)).hexdigest()
    races=csv_rows(raw["races.csv"]); historical=csv_rows(raw["historical.csv"]); gcbs=csv_rows(raw["gcb_polls.csv"]); race_polls=csv_rows(raw["race_polls.csv"])
    hist={r["code"]:r for r in historical}
    gcb,recent_gcb,gcb_count=aggregate_gcb(gcbs,asof)
    target=[r for r in races if r.get("race_type") in {"house","senate"}]
    modeled=[race_model(r,hist,race_polls,gcb,asof) for r in target]
    house=[r for r in modeled if r["race_type"]=="house"]; senate=[r for r in modeled if r["race_type"]=="senate"]
    if len(house)!=435: raise RuntimeError(f"Expected 435 House races, got {len(house)}")
    if len(senate)<33: raise RuntimeError(f"Expected at least 33 Senate races, got {len(senate)}")
    senate_up_holders=defaultdict(int)
    for r in races:
        if r.get("race_type")=="senate" and r.get("seat_holder") in {"DEM","REP"}: senate_up_holders[r["seat_holder"]]+=1
    hsum,ssum=simulate(house,senate,dict(senate_up_holders))
    all_competitive=sorted(modeled,key=lambda r:abs(r["dem_probability"]-.5))
    tipping=[r for r in all_competitive if r["race_type"]=="house"][:15]
    sen_battles=[r for r in all_competitive if r["race_type"]=="senate"][:12]
    previous=None
    if OUT.exists():
        try: previous=json.loads(OUT.read_text())
        except Exception: previous=None
    deltas=None
    if previous and previous.get("summary"):
        try:
            deltas={"house_expected_dem":round(hsum["expected_dem_seats"]-previous["summary"]["house"]["expected_dem_seats"],1),"senate_expected_dem":round(ssum["expected_dem_seats"]-previous["summary"]["senate"]["expected_dem_seats"],1),"generic_ballot_margin":round(gcb-previous["national_environment"]["generic_ballot_d_minus_r"],1)}
        except Exception: deltas=None
    out={"schema_version":"0.2.0","model":"MIDTERM SIGNALS baseline-v0.2","production_forecast":"published","generated_at":now.isoformat().replace("+00:00","Z"),"election_date":ELECTION_DATE.isoformat(),"days_to_election":max(0,(ELECTION_DATE-now.date()).days),"summary":{"house":hsum,"senate":ssum},"national_environment":{"generic_ballot_d_minus_r":round(gcb,2),"polls_in_35_day_window":gcb_count,"recent_polls":recent_gcb,"historical_2024_presidential_d_minus_r":NAT_PRES[2024]},"tipping_point_house":tipping,"senate_battlegrounds":sen_battles,"races":modeled,"change_since_previous_run":deltas,"methodology":{"partisan_lean":"5% 2016 + 20% 2020 + 75% 2024 district/state presidential margin, each centred on that year's national D-R margin","national_environment":"35-day generic-ballot poll average with exponential recency decay, sample-size and pollster-quality weighting; partisan-sponsored polls downweighted","incumbency":"+1.0 D / -1.0 R House; 1.15x in Senate","race_polling":"nominee-matched polls from the last 55 days blended with the prior; weight rises sub-linearly with poll count and is capped","probabilities":"normal-error race model plus 30,000 correlated Monte Carlo chamber simulations","qualitative_news":"not an input to numerical probabilities","senate_control":"Democratic caucus requires 51 seats because the vice president is Republican"},"provenance":{"upstream_input_mirror":UPSTREAM_REPO,"upstream_commit":sha,"input_sha256":inputs_hash,"files":names,"note":"MIDTERM SIGNALS consumes factual/curated inputs from the upstream data repository, not its forecast outputs. Numerical transformations and simulations are performed here."},"limitations":["This is a transparent baseline model, not a claim of certainty.","Candidate-quality effects beyond incumbency are not yet separately estimated.","Third-party and ranked-choice transfer behaviour is simplified in the chamber model.","Race polls are used only when the poll matchup matches the current major-party nominees; missing polling remains missing.","The model can be wrong together across many races; correlated national error is therefore simulated explicitly."]}
    OUT.parent.mkdir(parents=True,exist_ok=True); HIST.mkdir(parents=True,exist_ok=True)
    text=json.dumps(out,indent=2)+"\n"; OUT.write_text(text)
    STATUS.write_text(json.dumps({"schema_version":2,"project":"MIDTERM SIGNALS","election_date":ELECTION_DATE.isoformat(),"generated_at":out["generated_at"],"production_forecast":"published","publication_label":"LIVE BASELINE · MODEL v0.2","model":out["model"],"simulations":out["summary"]["house"]["simulations"],"house_all_435_accounted_for":len(house)==435,"senate_contests_accounted_for":len(senate),"upstream_commit":sha,"input_sha256":inputs_hash,"qualitative_news_changes_probabilities":False,"limitations":out["limitations"]},indent=2)+"\n")
    stamp=now.strftime("%Y-%m-%dT%H%M%SZ"); (HIST/f"{stamp}.json").write_text(text)
    snapshots=sorted([x.name for x in HIST.glob("*.json") if x.name!="index.json"],reverse=True)
    (HIST/"index.json").write_text(json.dumps({"snapshots":snapshots[:120]},indent=2)+"\n")
    print(f"Built {len(house)} House + {len(senate)} Senate races; GCB D-R {gcb:+.2f}; upstream {sha[:10]}")

if __name__ == "__main__": main()
