#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FORECAST=ROOT/'public/data/forecast.json'
STATUS=ROOT/'public/data/status.json'


def fail(msg:str)->None:
    raise SystemExit(f'forecast validation failed: {msg}')


def main()->None:
    if not FORECAST.exists():
        fail('missing public/data/forecast.json')
    f=json.loads(FORECAST.read_text())
    if f.get('schema_version')!='1.0.0': fail(f"unexpected schema {f.get('schema_version')}")
    if f.get('production_forecast')!='published': fail('forecast not published')
    if f.get('election_date')!='2026-11-03': fail('unexpected election date')
    races=f.get('races') or []
    house=[r for r in races if r.get('race_type')=='house']
    senate=[r for r in races if r.get('race_type')=='senate']
    if len(house)!=435: fail(f'House universe incomplete: {len(house)}')
    if len(senate)<33: fail(f'Senate universe incomplete: {len(senate)}')
    codes=[r.get('race_code') for r in races]
    if len(codes)!=len(set(codes)): fail('duplicate race_code')
    for r in races:
        p=r.get('dem_probability')
        q=r.get('rep_probability')
        if not isinstance(p,(int,float)) or not 0<=p<=1: fail(f"invalid D probability {r.get('race_code')}")
        if not isinstance(q,(int,float)) or not 0<=q<=1: fail(f"invalid R probability {r.get('race_code')}")
        if abs((p+q)-1)>0.002: fail(f"probabilities do not sum to one {r.get('race_code')}")
        if r.get('poll_count',0)!=len(r.get('polls') or []): fail(f"poll_count mismatch {r.get('race_code')}")
    for chamber,total,threshold in [('house',435,218),('senate',100,51)]:
        s=f['summary'][chamber]
        if abs((s['expected_dem_seats']+s['expected_rep_seats'])-total)>.2: fail(f'{chamber} expected seat total')
        for key in ['dem_seats_50_interval','dem_seats_80_interval','dem_seats_90_interval','dem_seats_95_interval']:
            lo,hi=s[key]
            if not 0<=lo<=hi<=total: fail(f'{chamber} invalid {key}')
        if not s.get('distribution'): fail(f'{chamber} distribution missing')
        mass=sum(x['probability'] for x in s['distribution'])
        if abs(mass-1)>.002: fail(f'{chamber} distribution mass {mass}')
        if s.get('control_threshold_dem')!=threshold: fail(f'{chamber} control threshold')
    joint=f['summary'].get('joint_control') or {}
    if abs(sum(joint.values())-1)>.002: fail('joint control probabilities do not sum to one')
    prov=f.get('provenance') or {}
    for key in ['upstream_commit','input_sha256','file_sha256','retrieved_at']:
        if not prov.get(key): fail(f'missing provenance {key}')
    sources=f.get('source_health') or []
    if not sources: fail('source health missing')
    allowed={'current','stale','unavailable','degraded','restricted'}
    if any(s.get('state') not in allowed for s in sources): fail('invalid source state')
    if f.get('model_health',{}).get('historical_backtests',{}).get('2018',{}).get('state')!='unavailable': fail('2018 backtest must remain explicitly unavailable until reconstructed')
    if f.get('model_health',{}).get('historical_backtests',{}).get('2022',{}).get('state')!='unavailable': fail('2022 backtest must remain explicitly unavailable until reconstructed')
    if f.get('external_forecasters',{}).get('configured_count',0)!=0:
        if not any(r.get('external_forecasters') for r in races): fail('external source count configured without race data')
    if not STATUS.exists(): fail('status.json missing')
    status=json.loads(STATUS.read_text())
    if status.get('release')!='PROD v1.0': fail('status release not v1.0')
    print(f"MIDTERM SIGNALS forecast validation passed: {len(house)} House + {len(senate)} Senate races; model {f.get('model')}")

if __name__=='__main__': main()
