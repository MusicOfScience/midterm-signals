#!/usr/bin/env python3
"""Acquire and normalize the 2018 Model Lab corpus.

This script is intentionally one-shot and fail-closed. It never runs as part of
the live forecast refresh. Source URLs are commit-pinned where possible; the
Downballot/Daily Kos district sheet is accepted only when its raw SHA-256 equals
a separately recorded public fingerprint.
"""
from __future__ import annotations
import csv, hashlib, io, json, re, urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'historical'/'2018'; RAW=OUT/'raw'
UA='MIDTERM-SIGNALS historical corpus audit/1.0 (+https://github.com/MusicOfScience/midterm-signals)'
K5='47fd763f01de196586ca6e8f2ecb221e873b62ed'; FTE_MIRROR='fe795fa790446b9c478de4b21a1df488ef8d1bf3'; MEDSL='fe67c056502fc09ddb1ace2ff8f87c53233a744e'
SOURCES={
 'house_forecast':f'https://raw.githubusercontent.com/k5cents/models-markets/{K5}/data/raw/models/house_district_forecast.csv',
 'senate_forecast':f'https://raw.githubusercontent.com/k5cents/models-markets/{K5}/data/raw/models/senate_seat_forecast.csv',
 'members':f'https://raw.githubusercontent.com/k5cents/models-markets/{K5}/data/new/members.csv',
 'winner_crosscheck':f'https://raw.githubusercontent.com/k5cents/models-markets/{K5}/data/new/results.csv',
 'house_polls':f'https://raw.githubusercontent.com/markjrieke/2022-midterm-forecasts/{FTE_MIRROR}/data/polls/src/fte/house_polls_historical.csv',
 'senate_polls':f'https://raw.githubusercontent.com/markjrieke/2022-midterm-forecasts/{FTE_MIRROR}/data/polls/src/fte/senate_polls_historical.csv',
 'generic_polls':f'https://raw.githubusercontent.com/markjrieke/2022-midterm-forecasts/{FTE_MIRROR}/data/polls/src/fte/generic_ballot_polls_historical.csv',
 'house_results':f'https://raw.githubusercontent.com/MEDSL/constituency-returns/{MEDSL}/1976-2018-house.csv',
 'senate_results':f'https://raw.githubusercontent.com/MEDSL/constituency-returns/{MEDSL}/1976-2018-senate.csv',
 'president_results':f'https://raw.githubusercontent.com/MEDSL/constituency-returns/{MEDSL}/1976-2016-president.csv',
 'district_presidential':'https://docs.google.com/spreadsheets/d/1zLNAuRqPauss00HDz4XbTH2HqsCzMe0pR8QmD1K8jk8/export?format=csv',
}
DISTRICT_SHEET_SHA256='1ac29ca1575210f62470732cacd2b8d0203b6219ef5223bf12ae309f54f7a23e'

def fetch(name,url):
    req=urllib.request.Request(url,headers={'User-Agent':UA}); data=urllib.request.urlopen(req,timeout=120).read(); RAW.mkdir(parents=True,exist_ok=True); (RAW/f'{name}.csv').write_bytes(data); return data

def rows(data): return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
def fnum(v):
    try:return float(str(v or '').replace('%','').strip())
    except:return None

def iso(v):
    s=str(v or '').strip()
    for fmt in ('%Y-%m-%d','%m/%d/%y','%m/%d/%Y'):
        try:return __import__('datetime').datetime.strptime(s,fmt).date().isoformat()
        except:pass
    return ''
def party(v):
    s=str(v or '').strip().upper()
    if s.startswith('D'):return 'DEM'
    if s.startswith('R'):return 'REP'
    return s

def district_code(state,district):
    st=str(state or '').strip().upper(); d=str(district or '').strip().upper()
    if not st:return ''
    if d in ('','0','00','AL','AT-LARGE'): return f'{st}-01'
    try:return f'{st}-{int(float(d)):02d}'
    except:return f'{st}-{d.zfill(2)}'

def race_from_538(row,chamber):
    if chamber=='house': return district_code(row.get('state'),row.get('district'))
    race=(row.get('state') or '').strip().upper(); seat=str(row.get('seat') or row.get('seat_name') or '1')
    m=re.search(r'(\d+)',seat); return f'{race}-S{m.group(1) if m else "1"}' if race else ''

def parse_downballot(data):
    text=data.decode('utf-8-sig'); table=list(csv.reader(io.StringIO(text))); hdr=None
    for i,r in enumerate(table[:10]):
        low=[c.strip().lower() for c in r]
        if any(c in {'clinton','trump','obama','romney','mccain'} for c in low): hdr=i; break
    if hdr is None or hdr==0: raise RuntimeError('Downballot multi-year header not found')
    years=[c.strip() for c in table[hdr-1]]; names=[c.strip().lower() for c in table[hdr]]; pairs={}
    for i,y in enumerate(years):
        if y not in {'2008','2012','2016'}: continue
        dem=next((j for j in range(i,min(i+4,len(names))) if names[j] in {'clinton','obama','dem'}),None); rep=next((j for j in range(i,min(i+4,len(names))) if names[j] in {'trump','romney','mccain','rep'}),None)
        if dem is not None and rep is not None:pairs[int(y)]=(dem,rep)
    if set(pairs)!={2008,2012,2016}: raise RuntimeError(f'Downballot years missing: {pairs}')
    out={}
    for r in table[hdr+1:]:
        if not r:continue
        code=(r[0] or '').strip().upper()
        if not re.match(r'^[A-Z]{2}-(?:\d{2}|AL)$',code):continue
        code=code.replace('-AL','-01'); vals={}
        for y,(di,ri) in pairs.items():
            if max(di,ri)>=len(r):continue
            d,rp=fnum(r[di]),fnum(r[ri]); vals[y]=(d-rp) if d is not None and rp is not None else None
        if all(vals.get(y) is not None for y in (2008,2012,2016)): out[code]=vals
    if len(out)!=435: raise RuntimeError(f'Expected 435 structural districts, got {len(out)}')
    return out

def national_margins(president):
    out={}
    for y in (2008,2012,2016):
        d=r=0.0
        for row in president:
            if str(row.get('year'))!=str(y):continue
            p=(row.get('party') or '').lower(); votes=fnum(row.get('candidatevotes')) or 0
            if 'democrat' in p:d+=votes
            elif 'republican' in p:r+=votes
        if not d or not r: raise RuntimeError(f'Missing national presidential votes {y}')
        total=sum(fnum(x.get('candidatevotes')) or 0 for x in president if str(x.get('year'))==str(y))
        out[y]=round(100*(d-r)/total,6)
    return out

def build_results(house,senate):
    grouped=defaultdict(lambda:defaultdict(float))
    for chamber,data in [('house',house),('senate',senate)]:
        for row in data:
            if str(row.get('year'))!='2018' or (row.get('stage') or '').upper()!='GEN':continue
            code=district_code(row.get('state_po'),row.get('district')) if chamber=='house' else f"{(row.get('state_po') or '').upper()}-S{str(row.get('special') or '').upper()=='TRUE' and '2' or '1'}"
            p=party(row.get('party')); v=fnum(row.get('candidatevotes')) or 0
            if p in {'DEM','REP'}:grouped[code][p]+=v
    result=[]
    for code,v in sorted(grouped.items()):
        if not v.get('DEM') and not v.get('REP'):continue
        result.append({'race_code':code,'winner_party':'DEM' if v.get('DEM',0)>v.get('REP',0) else 'REP'})
    return result

def candidate_rows(forecast,chamber,structural,incumbents):
    by=defaultdict(dict)
    for row in forecast:
        model=(row.get('model') or '').lower()
        if model and model not in {'deluxe','classic'}:continue
        code=race_from_538(row,chamber); fd=iso(row.get('forecastdate'))
        if not code or not fd:continue
        name=(row.get('candidate') or row.get('candidate_name') or row.get('name') or '').strip(); p=party(row.get('party'))
        if p not in {'DEM','REP'}:continue
        key=(code,fd); by[key].setdefault(p,name)
    first={}
    for code,fd in sorted(by): first.setdefault(code,fd)
    out=[]
    for code,known in sorted(first.items()):
        candidates={}
        for (c,fd),ps in by.items():
            if c==code and fd<=known:candidates.update(ps)
        st=code[:2]; dist=code.split('-')[1] if chamber=='house' else ''
        incumbent=incumbents.get(code,'')
        vals=structural.get(code) if chamber=='house' else None
        if chamber=='senate': vals=structural.get(f'{st}-01')
        if not vals: continue
        out.append({'race_code':code,'race_type':chamber,'state':st,'district':dist,'known_date':known,'dem_name':candidates.get('DEM',''), 'rep_name':candidates.get('REP',''),'incumbent_party':incumbent,'same_party':'','margin_earliest':vals[2008],'margin_middle':vals[2012],'margin_latest':vals[2016]})
    return out

def incumbency_map(members):
    out={}
    for r in members:
        code=(r.get('race') or '').replace('-00','-01'); p=party(r.get('party'))
        if code and p in {'DEM','REP'}:out[code]=p
    return out

def poll_rows(raw,kind,chamber=None):
    out=[]
    for r in raw:
        cycle=str(r.get('cycle') or r.get('year') or '')
        if cycle and cycle!='2018':continue
        end=iso(r.get('end_date')); pub=iso(r.get('created_at') or r.get('publication_date') or '')
        if not end:continue
        base={'kind':kind,'publication_date':pub,'end_date':end,'pollster':r.get('pollster') or r.get('display_name') or '', 'rating':fnum(r.get('numeric_grade')) or 1.3,'n':fnum(r.get('sample_size')) or 800,'lean':party(r.get('partisan'))[:1] if r.get('partisan') else ''}
        if kind=='generic_ballot':
            dem=rep=None
            # 538 historical generic files are candidate rows; accept direct topline columns when present.
            for dk,rk in [('dem','rep'),('democrat','republican'),('dem_pct','rep_pct')]:
                if fnum(r.get(dk)) is not None and fnum(r.get(rk)) is not None: dem,rep=fnum(r.get(dk)),fnum(r.get(rk)); break
            if dem is None:
                a=party(r.get('party')); pct=fnum(r.get('pct') or r.get('answer'))
                if a in {'DEM','REP'} and pct is not None: base['_party']=a; base['_pct']=pct
                else: continue
            else: base.update({'dem':dem,'rep':rep,'margin':dem-rep}); out.append(base)
        else:
            code=race_from_538(r,chamber); p=party(r.get('party')); pct=fnum(r.get('pct'))
            if not code or p not in {'DEM','REP'} or pct is None:continue
            base.update({'race_code':code,'_party':p,'_pct':pct,'_name':r.get('candidate_name') or r.get('candidate') or ''}); out.append(base)
    # Collapse candidate-row polls using stable metadata keys.
    groups=defaultdict(dict); complete=[]
    for r in out:
        if '_party' not in r:complete.append(r);continue
        key=(r['kind'],r.get('race_code',''),r['pollster'],r['end_date'],str(r['n']),r.get('publication_date',''))
        groups[key][r['_party']]=r
    for key,ps in groups.items():
        if {'DEM','REP'}-ps.keys():continue
        d,rr=ps['DEM'],ps['REP']; row={k:v for k,v in d.items() if not k.startswith('_')}; row.update({'dem':d['_pct'],'rep':rr['_pct'],'margin':d['_pct']-rr['_pct']})
        if row['kind']=='race': row.update({'dem_name':d.get('_name',''),'rep_name':rr.get('_name','')})
        complete.append(row)
    return complete

def write_csv(path,data):
    if not data:raise RuntimeError(f'No rows for {path}')
    fields=[]
    for r in data:
        for k in r:
            if k not in fields:fields.append(k)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)

def main():
    blobs={name:fetch(name,url) for name,url in SOURCES.items()}
    if hashlib.sha256(blobs['district_presidential']).hexdigest()!=DISTRICT_SHEET_SHA256: raise RuntimeError('Downballot 2018 district sheet SHA-256 mismatch; refusing admission')
    structural=parse_downballot(blobs['district_presidential']); members=rows(blobs['members']); inc=incumbency_map(members); housef=rows(blobs['house_forecast']); senatef=rows(blobs['senate_forecast'])
    races=candidate_rows(housef,'house',structural,inc)+candidate_rows(senatef,'senate',structural,inc)
    hp=poll_rows(rows(blobs['house_polls']),'race','house'); sp=poll_rows(rows(blobs['senate_polls']),'race','senate'); gp=poll_rows(rows(blobs['generic_polls']),'generic_ballot'); polls=hp+sp+gp
    result=build_results(rows(blobs['house_results']),rows(blobs['senate_results'])); national=national_margins(rows(blobs['president_results']))
    if len([r for r in races if r['race_type']=='house'])!=435: raise RuntimeError(f'House roster incomplete: {len([r for r in races if r["race_type"]=="house"])}')
    if len(result)<468: raise RuntimeError(f'Result universe suspiciously small: {len(result)}')
    if not gp: raise RuntimeError('No 2018 generic-ballot polls normalized')
    write_csv(OUT/'races.csv',races); write_csv(OUT/'polls.csv',polls); write_csv(OUT/'results.csv',result)
    prov=[]
    for name,url in SOURCES.items(): prov.append({'name':name,'url':url,'sha256':hashlib.sha256(blobs[name]).hexdigest(),'bytes':len(blobs[name])})
    cfg={'cycle':2018,'election_date':'2018-11-06','corpus_state':'admitted','baseline_presidential_years':[2008,2012,2016],'national_presidential_margins':{'earliest':national[2008],'middle':national[2012],'latest':national[2016]},'provenance':prov,'admission':{'house_races':435,'total_races':len(races),'poll_rows':len(polls),'result_rows':len(result),'downballot_sha256_expected':DISTRICT_SHEET_SHA256,'notes':['Forecast probabilities from source archives are never imported as MIDTERM SIGNALS inputs.','First candidate appearance in the archived FiveThirtyEight daily forecast is used as conservative known_date.','MEDSL machine-readable constituency returns supply scoring outcomes; preserved 538 winner map is retained only as a cross-check.']}}
    (OUT/'cycle.json').write_text(json.dumps(cfg,indent=2)+'\n'); print(json.dumps(cfg['admission']))
if __name__=='__main__':main()
