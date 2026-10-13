#!/usr/bin/env python3
"""Build the leakage-gated 2022 Model Lab corpus and scoreability ledger.

The admitted 2022 sample is deliberately conservative. House races are scored
only when the frozen binary D/R party-control model can represent the race at
all five checkpoints. Senate races remain in the ledger but are excluded until
an election-eve raw poll stream covering the early checkpoints is admitted.

No election outcome is opened until predictive inputs and the scoreability
ledger have been constructed.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "historical" / "2022"
UA = "MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)"
ELECTION = date(2022, 11, 8)
CHECKPOINTS = [date(2022, 9, 9), date(2022, 10, 9), date(2022, 10, 25), date(2022, 11, 1), date(2022, 11, 7)]

DRA_REPO = "dra2020/block_data"
DRA_COMMIT = "7f29db811844c02ab726ffec9bb34865c73ef342"
CENSUS_BEF = "https://www2.census.gov/programs-surveys/decennial/rdo/mapping-files/2023/118-congressional-district-bef/cd118.zip"
ROSTER_REPO = "stephensond/election-night-2022"
ROSTER_COMMIT = "83f2c9867f319b921fa10ad04bc256d8106bc8f4"
ROSTER_BASE = f"https://raw.githubusercontent.com/{ROSTER_REPO}/{ROSTER_COMMIT}/input"
HOUSE_ROSTER_URL = f"{ROSTER_BASE}/house_district_toplines_2022.csv"
SENATE_ROSTER_URL = f"{ROSTER_BASE}/senate_state_toplines_2022.csv"
HOUSE_POLLS_REPO = "SRMG-Labs/us-election-data"
HOUSE_POLLS_COMMIT = "700713b32b30529331a95206bb06040b9ea62df3"
HOUSE_POLLS_URL = f"https://raw.githubusercontent.com/{HOUSE_POLLS_REPO}/{HOUSE_POLLS_COMMIT}/house_polls.csv"
GENERIC_REPO = "kentoyamada100/election-analytics-2022-midterms"
GENERIC_COMMIT = "3c9f718baf7fda26542b1d0542e5f032ca00db4f"
GENERIC_URL = f"https://raw.githubusercontent.com/{GENERIC_REPO}/{GENERIC_COMMIT}/analysis_data/1105_538_generic_ballot_polls.csv"
FTE_ARCHIVE_REPO = "fivethirtyeight/data"
FTE_ARCHIVE_COMMIT = "4c1ff5e3aef1816ae04af63218015066e186c147"
FTE_ARCHIVE_URL = f"https://raw.githubusercontent.com/{FTE_ARCHIVE_REPO}/{FTE_ARCHIVE_COMMIT}/pollster-ratings/2023/raw-polls.csv"
LEGISLATORS_REPO = "unitedstates/congress-legislators"
LEGISLATORS_COMMIT = "0d7d64369f9b01dc924415d570285e2dffe642ee"
LEGISLATORS_URL = f"https://raw.githubusercontent.com/{LEGISLATORS_REPO}/{LEGISLATORS_COMMIT}/legislators-current.yaml"
HOUSE_RESULTS_URL = "https://dataverse.harvard.edu/api/access/datafile/8963860"
NATIONAL = {"earliest": 3.86, "middle": 2.09, "latest": 4.46}

STATE_CODES = {
    "ALABAMA":"AL","ALASKA":"AK","ARIZONA":"AZ","ARKANSAS":"AR","CALIFORNIA":"CA",
    "COLORADO":"CO","CONNECTICUT":"CT","DELAWARE":"DE","FLORIDA":"FL","GEORGIA":"GA",
    "HAWAII":"HI","IDAHO":"ID","ILLINOIS":"IL","INDIANA":"IN","IOWA":"IA","KANSAS":"KS",
    "KENTUCKY":"KY","LOUISIANA":"LA","MAINE":"ME","MARYLAND":"MD","MASSACHUSETTS":"MA",
    "MICHIGAN":"MI","MINNESOTA":"MN","MISSISSIPPI":"MS","MISSOURI":"MO","MONTANA":"MT",
    "NEBRASKA":"NE","NEVADA":"NV","NEW HAMPSHIRE":"NH","NEW JERSEY":"NJ","NEW MEXICO":"NM",
    "NEW YORK":"NY","NORTH CAROLINA":"NC","NORTH DAKOTA":"ND","OHIO":"OH","OKLAHOMA":"OK",
    "OREGON":"OR","PENNSYLVANIA":"PA","RHODE ISLAND":"RI","SOUTH CAROLINA":"SC",
    "SOUTH DAKOTA":"SD","TENNESSEE":"TN","TEXAS":"TX","UTAH":"UT","VERMONT":"VT",
    "VIRGINIA":"VA","WASHINGTON":"WA","WEST VIRGINIA":"WV","WISCONSIN":"WI","WYOMING":"WY",
}
FIPS = {
    "AL":"01","AK":"02","AZ":"04","AR":"05","CA":"06","CO":"08","CT":"09","DE":"10","FL":"12","GA":"13",
    "HI":"15","ID":"16","IL":"17","IN":"18","IA":"19","KS":"20","KY":"21","LA":"22","ME":"23","MD":"24",
    "MA":"25","MI":"26","MN":"27","MS":"28","MO":"29","MT":"30","NE":"31","NV":"32","NH":"33","NJ":"34",
    "NM":"35","NY":"36","NC":"37","ND":"38","OH":"39","OK":"40","OR":"41","PA":"42","RI":"44","SC":"45",
    "SD":"46","TN":"47","TX":"48","UT":"49","VT":"50","VA":"51","WA":"53","WV":"54","WI":"55","WY":"56",
}
GRADE_SCORE = {
    "A+":3.0,"A":2.8,"A-":2.6,"A/B":2.5,"B+":2.4,"B":2.2,"B-":2.0,
    "B/C":1.8,"C+":1.6,"C":1.4,"C-":1.2,"C/D":1.0,"D+":0.9,"D":0.8,"D-":0.75,
}
D_KEYS = ("name_D1","name_D2","name_D3","name_D4")
R_KEYS = ("name_R1","name_R2","name_R3","name_R4")
I_KEYS = ("name_I1","name_O1")
PROVENANCE: list[dict] = []


def fetch(label: str, url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if not data:
        raise RuntimeError(f"empty source: {label}")
    PROVENANCE.append({"label": label, "url": url, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return data


def csv_rows(data: bytes, errors: str = "strict") -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors=errors))))


def parse_day(v) -> date | None:
    s = str(v or "").strip()
    if not s:
        return None
    s = s.split()[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def fnum(v, default=None):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def party(v: str | None) -> str:
    s = str(v or "").strip().upper()
    if s.startswith("DEM") or s in {"D","DFL"}: return "DEM"
    if s.startswith("REP") or s == "R": return "REP"
    if s.startswith("IND") or s == "I": return "IND"
    return s


def state_po(v: str | None) -> str:
    s = str(v or "").strip().upper()
    if len(s) == 2 and s.isalpha(): return s
    return STATE_CODES.get(s, "")


def district_code(st: str, district) -> str:
    st = state_po(st)
    raw = str(district or "").strip().upper()
    if not st: return ""
    if raw in {"", "0", "00", "AL", "AT-LARGE"}: return f"{st}-01"
    try: return f"{st}-{int(float(raw)):02d}"
    except ValueError: return ""


def grade_score(v) -> float:
    return GRADE_SCORE.get(str(v or "").strip().upper(), 1.3)


def norm_name(v: str | None) -> str:
    s = (v or "").lower()
    s = re.sub(r"[“”\"'’`]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def surname(v: str | None) -> str:
    bits = norm_name(v).split()
    return bits[-1] if bits else ""


def roster_code(row: dict, chamber: str) -> str:
    raw = str(row.get("district") or "").strip().upper()
    return raw.replace("-AL", "-01") if chamber == "house" else raw


def names(row: dict, keys) -> list[str]:
    return [str(row.get(k) or "").strip() for k in keys if str(row.get(k) or "").strip()]


def major_signature(row: dict) -> tuple:
    return (tuple(names(row, D_KEYS)), tuple(names(row, R_KEYS)))


def collapse_roster(data: bytes, chamber: str) -> dict[str, list[dict]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    variants: dict[tuple[str,date], list[dict]] = defaultdict(list)
    for row in reader:
        if str(row.get("cycle") or "") != "2022": continue
        d = parse_day(row.get("forecastdate")); code = roster_code(row, chamber)
        if d and code: variants[(code,d)].append(row)
    by_code: dict[str,list[dict]] = defaultdict(list); disagreements=[]
    for (code,d), group in variants.items():
        sigs={major_signature(r) for r in group}
        if len(sigs)!=1:
            disagreements.append((code,d.isoformat(),list(sigs)[:4])); continue
        row=max(group,key=lambda r: sum(bool(x) for x in names(r,D_KEYS+R_KEYS+I_KEYS)))
        row=dict(row); row["_day"]=d; row["_code"]=code; by_code[code].append(row)
    if disagreements: raise RuntimeError(f"roster disagreement across forecast variants: {disagreements[:8]}")
    for arr in by_code.values(): arr.sort(key=lambda r:r["_day"])
    expected=435 if chamber=="house" else 35
    if len(by_code)!=expected: raise RuntimeError(f"{chamber} roster expected {expected}, got {len(by_code)}")
    return dict(by_code)


def at_checkpoint(arr: list[dict], cp: date) -> dict | None:
    eligible=[r for r in arr if r["_day"]<=cp]
    return eligible[-1] if eligible else None


def structure_class(row: dict) -> tuple[str,str]:
    ds,rs=names(row,D_KEYS),names(row,R_KEYS)
    if ds and not rs: return "deterministic_dem",""
    if rs and not ds: return "deterministic_rep",""
    if len(ds)==1 and len(rs)==1: return "binary_dr",""
    if not ds and not rs: return "excluded","no_major_party_candidate"
    return "excluded","multi_major_candidate_structure"


def incumbent_snapshot(data: bytes) -> dict[tuple[str,str], list[dict]]:
    people=yaml.safe_load(data.decode("utf-8")); out=defaultdict(list)
    for p in people:
        nm=p.get("name") or {}; first=str(nm.get("first") or "").strip(); last=str(nm.get("last") or "").strip()
        official=str(nm.get("official_full") or "").strip(); nickname=str(nm.get("nickname") or "").strip(); aliases=set()
        for cand in (official,f"{first} {last}",f"{nickname} {last}" if nickname else ""):
            n=norm_name(cand)
            if n: aliases.add(n)
        for term in p.get("terms") or []:
            if term.get("type") not in {"rep","sen"}: continue
            start=parse_day(term.get("start")); end=parse_day(term.get("end"))
            if not start or not end or not (start<=date(2022,11,7)<=end): continue
            st=str(term.get("state") or "").upper(); par=party(term.get("party"))
            if st and par in {"DEM","REP"}: out[(term["type"],st)].append({"aliases":aliases,"party":par,"name":official or f"{first} {last}"})
    return dict(out)


def match_incumbents(row: dict, chamber: str, incumbents: dict) -> tuple[str,list[str],bool]:
    st=row["_code"][:2]; term_type="rep" if chamber=="house" else "sen"
    named=[(n,"DEM") for n in names(row,D_KEYS)]+[(n,"REP") for n in names(row,R_KEYS)]; matched=[]
    pool=incumbents.get((term_type,st),[]); surname_freq=defaultdict(int)
    for inc in pool:
        for a in inc["aliases"]:
            if a.split(): surname_freq[a.split()[-1]]+=1
    for candidate,side in named:
        cn=norm_name(candidate); cs=surname(candidate); candidates=[]
        for inc in pool:
            if cn in inc["aliases"]:
                candidates.append(inc); continue
            alias_surnames={a.split()[-1] for a in inc["aliases"] if a.split()}
            if cs and surname_freq[cs]==1 and cs in alias_surnames: candidates.append(inc)
        uniq={(x["name"],x["party"]) for x in candidates}
        if len(uniq)==1:
            nm,par=next(iter(uniq))
            if par!=side: raise RuntimeError(f"incumbent party mismatch {row['_code']}: {candidate} {side} vs {nm} {par}")
            matched.append((nm,par))
        elif len(uniq)>1:
            return "",[x[0] for x in sorted(uniq)],True
    parties={p for _,p in matched}; ambiguous=len(parties)>1
    return (next(iter(parties)) if len(parties)==1 else ""),[n for n,_ in matched],ambiguous


def build_scoreability(house_roster,senate_roster,incumbents):
    ledger=[]; admitted_house=[]
    for chamber,rosters in (("house",house_roster),("senate",senate_roster)):
        for code,arr in sorted(rosters.items()):
            classes={}; reason=""; inc_notes=set(); incumbent_party=""
            for cp in CHECKPOINTS:
                row=at_checkpoint(arr,cp)
                if not row:
                    classes[cp.isoformat()]="missing"; reason=reason or "roster_not_known_by_checkpoint"; continue
                cls,why=structure_class(row); classes[cp.isoformat()]=cls
                if why: reason=reason or why
                inc_party,inc_names,inc_ambig=match_incumbents(row,chamber,incumbents); inc_notes.update(inc_names)
                if inc_ambig: reason=reason or "ambiguous_incumbency_collision"
                if inc_party:
                    if incumbent_party and incumbent_party!=inc_party: reason=reason or "incumbency_changes_party_across_checkpoints"
                    incumbent_party=inc_party
            if chamber=="senate": reason=reason or "historical_poll_stream_incomplete_before_2022-10-18"
            if code=="GA-S3": reason=reason or "post_election_runoff"
            admitted=not reason
            ledger.append({"race_code":code,"race_type":chamber,"admitted":"true" if admitted else "false","exclusion_reason":reason,
                           "incumbent_party":incumbent_party,"matched_incumbents":"|".join(sorted(inc_notes)),
                           **{f"class_{(ELECTION-cp).days}d":classes.get(cp.isoformat(),"") for cp in CHECKPOINTS}})
            if chamber=="house" and admitted: admitted_house.append((code,arr,incumbent_party))
    if not admitted_house: raise RuntimeError("scoreability ledger admitted zero House races")
    return ledger,admitted_house


def latest_dra_refs() -> dict[str,tuple[str,str]]:
    tree=json.loads(fetch("DRA tree",f"https://api.github.com/repos/{DRA_REPO}/git/trees/{DRA_COMMIT}?recursive=1").decode()); refs={}
    for st in FIPS:
        pat=re.compile(rf"^2020_Geography/{st}/Election_Data_Block_{st}\.v(\d+)\.md$"); candidates=[]
        for item in tree.get("tree",[]):
            m=pat.match(item.get("path",""))
            if m: candidates.append((int(m.group(1)),item["path"]))
        if not candidates: raise RuntimeError(f"no DRA block source for {st}")
        _,path=max(candidates); md=fetch(f"DRA ref {st}",f"https://raw.githubusercontent.com/{DRA_REPO}/{DRA_COMMIT}/{path}").decode()
        m=re.search(r"https://data\.dra2020\.net/[^)\s]+\.zip",md)
        if not m: raise RuntimeError(f"no DRA URL in {path}")
        refs[st]=(path,m.group(0))
    return refs


def split_bef(tmp: Path) -> dict[str,Path]:
    data=fetch("Census 118th district block equivalency",CENSUS_BEF,timeout=600)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        candidates=[n for n in z.namelist() if "national" in n.lower() and not n.endswith("/")]
        if not candidates: candidates=[n for n in z.namelist() if n.lower().endswith((".txt",".csv"))]
        if not candidates: raise RuntimeError("Census BEF has no national table")
        text=io.TextIOWrapper(z.open(candidates[0]),encoding="utf-8-sig",errors="replace",newline="")
        first=text.readline(); delim="|" if first.count("|")>=first.count(",") else ","; header=next(csv.reader([first],delimiter=delim))
        if not {"GEOID","CDFP"}.issubset(header): raise RuntimeError(f"unexpected Census BEF columns: {header}")
        writers={}; handles={}; paths={}
        try:
            for st,fips in FIPS.items():
                p=tmp/f"bef-{st}.csv"; h=p.open("w",newline=""); writers[fips]=csv.writer(h); handles[fips]=h; paths[st]=p
            reader=csv.DictReader(text,fieldnames=header,delimiter=delim)
            for row in reader:
                geoid=str(row.get("GEOID") or "").strip(); cd=str(row.get("CDFP") or "").strip(); fips=geoid[:2]
                if fips in writers and geoid and cd: writers[fips].writerow((geoid,cd))
        finally:
            for h in handles.values(): h.close()
    return paths


def structural_priors() -> dict:
    refs=latest_dra_refs()
    with tempfile.TemporaryDirectory() as td:
        paths=split_bef(Path(td)); districts={}
        for st in sorted(FIPS):
            mapping={}
            with paths[st].open(newline="") as fh:
                for geoid,cd in csv.reader(fh): mapping[geoid]=cd
            _,url=refs[st]; data=fetch(f"DRA blocks {st}",url,timeout=600)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                members=[n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX/")]
                if not members: raise RuntimeError(f"{st}: DRA zip has no CSV")
                text=io.TextIOWrapper(z.open(members[0]),encoding="utf-8-sig",errors="replace",newline=""); reader=csv.DictReader(text)
                required={"GEOID","E_12_PRES_Dem","E_12_PRES_Rep","E_16_PRES_Dem","E_16_PRES_Rep","E_20_PRES_Dem","E_20_PRES_Rep"}
                if not required.issubset(reader.fieldnames or []): raise RuntimeError(f"{st}: missing DRA columns {sorted(required-set(reader.fieldnames or []))}")
                dsum=defaultdict(lambda:defaultdict(float)); seen=joined=0
                for row in reader:
                    geoid=str(row.get("GEOID") or "").strip(); seen+=1; cd=mapping.get(geoid)
                    if cd is None: continue
                    joined+=1
                    for yr in (12,16,20):
                        dsum[cd][f"{yr}d"]+=fnum(row.get(f"E_{yr}_PRES_Dem"),0.0) or 0.0
                        dsum[cd][f"{yr}r"]+=fnum(row.get(f"E_{yr}_PRES_Rep"),0.0) or 0.0
                if seen and joined/seen<0.995: raise RuntimeError(f"{st}: DRA/Census GEOID join only {joined}/{seen}")
                for cd,vals in dsum.items():
                    rc=district_code(st,cd); margins={}
                    for yr,key in ((12,"earliest"),(16,"middle"),(20,"latest")):
                        d,r=vals[f"{yr}d"],vals[f"{yr}r"]
                        if d+r<=0: raise RuntimeError(f"{rc}: empty {yr} presidential denominator")
                        margins[key]=100*(d-r)/(d+r)
                    districts[rc]=margins
    if len(districts)!=435: raise RuntimeError(f"expected 435 redistricted House structural priors, got {len(districts)}")
    return districts


def build_races(admitted_house,district_priors) -> list[dict]:
    rows=[]
    for code,arr,incumbent_party in admitted_house:
        prior=district_priors.get(code)
        if not prior: raise RuntimeError(f"missing structural prior for {code}")
        previous=None
        for src in arr:
            if src["_day"]>CHECKPOINTS[-1]: continue
            ds,rs=names(src,D_KEYS),names(src,R_KEYS); cls,why=structure_class(src)
            if why: continue
            sig=(tuple(ds),tuple(rs),incumbent_party,cls)
            if sig==previous: continue
            previous=sig; same="DEM" if cls=="deterministic_dem" else "REP" if cls=="deterministic_rep" else ""
            rows.append({"race_code":code,"race_type":"house","state":code[:2],"district":code.split("-")[1],"known_date":src["_day"].isoformat(),
                         "dem_name":ds[0] if ds else "(No Democrat)","rep_name":rs[0] if rs else "(No Republican)","ind_name":"","ind_caucus":"",
                         "incumbent_party":incumbent_party,"same_party":same,"margin_earliest":round(prior["earliest"],6),
                         "margin_middle":round(prior["middle"],6),"margin_latest":round(prior["latest"],6)})
    by=defaultdict(list)
    for r in rows: by[r["race_code"]].append(r)
    active=[]
    for cp in CHECKPOINTS: active.append(sum(1 for arr in by.values() if any(parse_day(r["known_date"])<=cp for r in arr)))
    if len(set(active))!=1 or active[0]!=len(admitted_house): raise RuntimeError(f"fixed House sample failed across checkpoints: {active}")
    return rows


def publication_date(row:dict,end:date|None)->str:
    c=parse_day(row.get("created_at"))
    if not c or not end: return ""
    return c.isoformat() if 0<=(c-end).days<=14 else ""


def build_house_polls(data:bytes,admitted_codes:set[str])->list[dict]:
    groups=defaultdict(list)
    for r in csv_rows(data):
        if str(r.get("cycle") or "")!="2022" or str(r.get("office_type") or "")!="U.S. House" or str(r.get("stage") or "").lower()!="general": continue
        if parse_day(r.get("election_date"))!=ELECTION or str(r.get("ranked_choice_reallocated") or "").lower()=="true": continue
        st=state_po(r.get("state")); code=district_code(st,r.get("seat_number"))
        if code not in admitted_codes: continue
        q=(r.get("poll_id"),r.get("question_id"),r.get("population_full") or r.get("population"),code); groups[q].append(r)
    out=[]
    for (_,_,_,code),grp in groups.items():
        dem=[r for r in grp if party(r.get("party"))=="DEM"]; rep=[r for r in grp if party(r.get("party"))=="REP"]
        if len(dem)!=1 or len(rep)!=1: continue
        d,r=dem[0],rep[0]; end=parse_day(d.get("end_date"))
        if not end or end>ELECTION: continue
        dv=fnum(d.get("pct")); rv=fnum(r.get("pct"))
        if dv is None or rv is None: continue
        out.append({"kind":"race_poll","race_code":code,"publication_date":publication_date(d,end) or end.isoformat(),"end_date":end.isoformat(),
                    "pollster":d.get("display_name") or d.get("pollster") or "","rating":grade_score(d.get("fte_grade")),"n":fnum(d.get("sample_size"),800) or 800,
                    "lean":party(d.get("partisan")) if party(d.get("partisan")) in {"DEM","REP"} else "","dem_name":d.get("candidate_name") or d.get("answer") or "",
                    "rep_name":r.get("candidate_name") or r.get("answer") or "","dem":dv,"rep":rv,"margin":dv-rv})
    if not out: raise RuntimeError("no normalized House race polls")
    return out


def build_generic(base:bytes,supplement:bytes)->list[dict]:
    combined={}
    for r in csv_rows(base):
        if str(r.get("cycle") or "")!="2022": continue
        end=parse_day(r.get("end_date"))
        if not end or end>ELECTION: continue
        combined[(r.get("poll_id"),r.get("question_id"),r.get("population_full") or r.get("population"),end.isoformat())]=r
    for r in csv_rows(supplement,errors="replace"):
        if str(r.get("cycle") or "")!="2022" or str(r.get("type_simple") or "")!="House-G" or str(r.get("location") or "").upper()!="US": continue
        end=parse_day(r.get("polldate") or r.get("end_date")); ed=parse_day(r.get("electiondate") or r.get("election_date"))
        if not end or end<=date(2022,11,4) or end>ELECTION or ed!=ELECTION: continue
        if party(r.get("cand1_party"))=="DEM" and party(r.get("cand2_party"))=="REP": dem,rep=fnum(r.get("cand1_pct")),fnum(r.get("cand2_pct"))
        elif party(r.get("cand2_party"))=="DEM" and party(r.get("cand1_party"))=="REP": dem,rep=fnum(r.get("cand2_pct")),fnum(r.get("cand1_pct"))
        else: continue
        if dem is None or rep is None: continue
        adapted={"poll_id":r.get("poll_id"),"question_id":r.get("question_id") or r.get("race"),"population":r.get("population") or "",
                 "display_name":r.get("pollster") or "","fte_grade":"","sample_size":r.get("samplesize") or "","partisan":"",
                 "end_date":end.isoformat(),"created_at":end.isoformat(),"dem":dem,"rep":rep}
        combined[(adapted["poll_id"],adapted["question_id"],adapted["population"],end.isoformat())]=adapted
    out=[]
    for r in combined.values():
        end=parse_day(r.get("end_date") or r.get("polldate")); dem=fnum(r.get("dem")); rep=fnum(r.get("rep"))
        if not end or end>ELECTION or dem is None or rep is None: continue
        out.append({"kind":"generic_ballot","race_code":"","publication_date":publication_date(r,end) or end.isoformat(),"end_date":end.isoformat(),
                    "pollster":r.get("display_name") or r.get("pollster") or "","rating":grade_score(r.get("fte_grade")),"n":fnum(r.get("sample_size"),800) or 800,
                    "lean":party(r.get("partisan")) if party(r.get("partisan")) in {"DEM","REP"} else "","dem_name":"","rep_name":"","dem":dem,"rep":rep,"margin":dem-rep})
    if not out or max(parse_day(r["end_date"]) for r in out)<date(2022,11,6): raise RuntimeError("generic-ballot composite does not reach election eve")
    return out


def result_winners(data:bytes)->dict[str,str]:
    grouped=defaultdict(list)
    for r in csv_rows(data,errors="replace"):
        if str(r.get("year") or "")!="2022" or str(r.get("stage") or "").upper()!="GEN": continue
        code=district_code(r.get("state_po") or r.get("state"),r.get("district"))
        if code: grouped[code].append(r)
    winners={}
    for code,grp in grouped.items():
        bycand=defaultdict(lambda:{"votes":0.0,"parties":set()})
        for r in grp:
            cand=norm_name(r.get("candidate"))
            if not cand: continue
            bycand[cand]["votes"]+=fnum(r.get("candidatevotes"),0.0) or 0.0; p=party(r.get("party") or r.get("party_simplified"))
            if p: bycand[cand]["parties"].add(p)
        if not bycand: continue
        winner=max(bycand.items(),key=lambda kv:kv[1]["votes"])[1]; parties=winner["parties"]
        side="DEM" if "DEM" in parties else "REP" if "REP" in parties else ""
        if side: winners[code]=side
    return winners


def write_csv(path:Path,rows:list[dict],fields:list[str]):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k:r.get(k,"") for k in fields})


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    house_roster_data=fetch("2022 dated House roster",HOUSE_ROSTER_URL,timeout=600); senate_roster_data=fetch("2022 dated Senate roster",SENATE_ROSTER_URL,timeout=600)
    incumbents=incumbent_snapshot(fetch("pre-election congressional membership",LEGISLATORS_URL)); house_roster=collapse_roster(house_roster_data,"house"); senate_roster=collapse_roster(senate_roster_data,"senate")
    ledger,admitted_house=build_scoreability(house_roster,senate_roster,incumbents)
    races=build_races(admitted_house,structural_priors())
    admitted_codes={c for c,_,_ in admitted_house}
    polls=build_house_polls(fetch("FiveThirtyEight House polls election-eve mirror",HOUSE_POLLS_URL),admitted_codes)
    polls+=build_generic(fetch("FiveThirtyEight generic ballot 2022-11-05 snapshot",GENERIC_URL),fetch("FiveThirtyEight 2023 raw-polls late generic supplement",FTE_ARCHIVE_URL))
    # Results are fetched only after all predictive inputs and admission decisions exist.
    winners=result_winners(fetch("MIT Election Data and Science Lab House 1976-2022",HOUSE_RESULTS_URL,timeout=600)); missing=sorted(admitted_codes-set(winners))
    if missing: raise RuntimeError(f"admitted House outcomes missing: {missing}")
    results=[{"race_code":c,"winner_party":winners[c]} for c in sorted(admitted_codes)]
    for row in ledger: row["outcome_party"]=winners.get(row["race_code"],"") if row["race_type"]=="house" else ""
    write_csv(OUT/"races.csv",races,["race_code","race_type","state","district","known_date","dem_name","rep_name","ind_name","ind_caucus","incumbent_party","same_party","margin_earliest","margin_middle","margin_latest"])
    write_csv(OUT/"polls.csv",polls,["kind","race_code","publication_date","end_date","pollster","rating","n","lean","dem_name","rep_name","dem","rep","margin"])
    write_csv(OUT/"results.csv",results,["race_code","winner_party"])
    write_csv(OUT/"scoreability-ledger.csv",ledger,["race_code","race_type","admitted","exclusion_reason","incumbent_party","matched_incumbents","class_60d","class_30d","class_14d","class_7d","class_1d","outcome_party"])
    admitted=len(results); excluded_house=sum(r["race_type"]=="house" and r["admitted"]=="false" for r in ledger); excluded_senate=sum(r["race_type"]=="senate" and r["admitted"]=="false" for r in ledger)
    cfg={"cycle":2022,"election_date":"2022-11-08","corpus_state":"admitted","scope":"House races passing the fixed five-checkpoint scoreability ledger; Senate excluded pending complete early historical poll stream.",
         "baseline_presidential_years":[2012,2016,2020],"national_presidential_margins":NATIONAL,
         "scoreability":{"universe":470,"admitted_house":admitted,"excluded_house":excluded_house,"excluded_senate":excluded_senate,"fixed_sample_across_checkpoints":True,"ledger":"scoreability-ledger.csv"},
         "poll_archive_rules":{"house_race_polls":"raw FiveThirtyEight election-eve snapshot committed 2022-11-07","generic_ballot":"2022-11-05 raw snapshot plus first-party raw-polls rows ending 2022-11-05..07","forbidden_retrospective_fields":["cand1_actual","cand2_actual","margin_actual","error","bias","rightcall"],"senate":"excluded: admitted archive does not cover the 60- and 30-day checkpoints completely"},
         "provenance":PROVENANCE,"note":"Historical evaluation only. No replay result may alter the frozen 2026 model contract."}
    (OUT/"cycle.json").write_text(json.dumps(cfg,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"state":"admitted","admitted_house":admitted,"excluded_house":excluded_house,"excluded_senate":excluded_senate,"race_versions":len(races),"poll_rows":len(polls),"generic_latest":max(r["end_date"] for r in polls if r["kind"]=="generic_ballot")},indent=2))

if __name__=="__main__": main()
