#!/usr/bin/env python3
"""Post-replay diagnostics for MIDTERM SIGNALS Model Lab.

Runs only after scripts/model_lab.py has frozen checkpoint predictions. Outcomes
are diagnostic labels only and cannot enter the predictive model path.
"""
import csv, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'public/data/model-lab.json'; HIST=ROOT/'historical'
DAYS=(60,30,14,7,1); BANDS=(('45-55',.45,.55),('40-60',.40,.60),('30-70',.30,.70),('20-80',.20,.80)); MOVE=.10; CONF=.80

def results(year):
    out={}
    with (HIST/str(year)/'results.csv').open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            c=(r.get('race_code') or '').strip(); w=(r.get('winner_party') or '').strip().upper()
            if c and w in {'DEM','REP'}:
                if c in out: raise ValueError(f'duplicate result {year} {c}')
                out[c]=int(w=='DEM')
    return out

def bins(ps,ys):
    out=[]
    for i in range(10):
        lo=i/10; hi=(i+1)/10; ix=[j for j,p in enumerate(ps) if lo<=p<hi or (i==9 and p==1)]
        if ix:
            mp=sum(ps[j] for j in ix)/len(ix); actual=sum(ys[j] for j in ix)/len(ix)
            out.append({'lower':lo,'upper':hi,'count':len(ix),'mean_probability':round(mp,6),'observed_rate':round(actual,6),'calibration_residual':round(actual-mp,6)})
    if sum(x['count'] for x in out)!=len(ps): raise ValueError('calibration-bin denominator drift')
    return out

def metrics(preds,res):
    if not preds:return {'state':'unavailable','n':0}
    codes=[p['race_code'] for p in preds]
    if len(codes)!=len(set(codes)) or any(c not in res for c in codes): raise ValueError('invalid diagnostic sample')
    ps=[float(p['dem_probability']) for p in preds]; ys=[res[c] for c in codes]; bb=bins(ps,ys)
    ll=lambda p,y:-(y*math.log(max(1e-15,min(1-1e-15,p)))+(1-y)*math.log(max(1e-15,min(1-1e-15,1-p))))
    mp=sum(ps)/len(ps); actual=sum(ys)/len(ys)
    return {'state':'scored','n':len(ps),'brier':round(sum((p-y)**2 for p,y in zip(ps,ys))/len(ps),8),'log_loss':round(sum(ll(p,y) for p,y in zip(ps,ys))/len(ps),8),'accuracy':round(sum((p>=.5)==bool(y) for p,y in zip(ps,ys))/len(ps),6),'mean_dem_probability':round(mp,6),'actual_dem_win_rate':round(actual,6),'calibration_error':round(actual-mp,6),'mean_absolute_bin_calibration_error':round(sum(b['count']*abs(b['calibration_residual']) for b in bb)/len(ps),6),'calibration':bb}

def enrich_score(cp,res):
    s=cp.get('score') or {}; preds=cp.get('predictions') or []
    if cp.get('state')!='scored' or s.get('state')!='scored': return
    if len(preds)!=s.get('n'): raise ValueError('scored denominator differs from predictions')
    base=metrics(preds,res)
    for k in ('brier','log_loss'):
        if abs(float(s[k])-float(base[k]))>1e-8: raise ValueError(f'{k} changed in post-replay recomputation')
    for k in ('accuracy','mean_dem_probability','actual_dem_win_rate','calibration_error','mean_absolute_bin_calibration_error','calibration'): s[k]=base[k]
    bands=[]
    for label,lo,hi in BANDS:
        bands.append({'band':label,'lower':lo,'upper':hi,'definition':'nested',**metrics([p for p in preds if lo<=float(p['dem_probability'])<=hi],res)})
    safe={'band':'safe-outside-20-80','lower':None,'upper':None,'definition':'complement',**metrics([p for p in preds if float(p['dem_probability'])<.2 or float(p['dem_probability'])>.8],res)}; bands.append(safe)
    if next(x for x in bands if x['band']=='20-80')['n']+safe['n']!=len(preds): raise ValueError('competitive/safe partition drift')
    s['competitive_bands']=bands
    polled=[p for p in preds if int(p.get('poll_count') or 0)>0]; unpolled=[p for p in preds if int(p.get('poll_count') or 0)==0]
    if len(polled)+len(unpolled)!=len(preds): raise ValueError('poll partition drift')
    s['polling']={'interpretation':'conditional comparison; polling is endogenous to competitiveness, not a causal treatment estimate','polled':metrics(polled,res),'unpolled':metrics(unpolled,res)}
    chambers={}; n=0
    for chamber in ('house','senate'):
        subset=[p for p in preds if (p.get('race_type') or '').lower()==chamber]; n+=len(subset); chambers[chamber]=metrics(subset,res) if subset else {'state':'unavailable','n':0,'reason':'no_admitted_races_at_checkpoint'}
    if n!=len(preds): raise ValueError('chamber partition drift')
    s['chambers']=chambers
    misses=[]
    for p in preds:
        y=res[p['race_code']]; wp=float(p['dem_probability']) if y else float(p['rep_probability']); correct=(float(p['dem_probability'])>=.5)==bool(y)
        if not correct:
            misses.append({'race_code':p['race_code'],'race_type':p.get('race_type'),'winner':'DEM' if y else 'REP','predicted_dem_probability':p['dem_probability'],'winner_probability':round(wp,6),'predicted_winner_probability':round(1-wp,6),'surprise':round(1-wp,6),'confident_miss':1-wp>=CONF})
    misses.sort(key=lambda x:x['surprise'],reverse=True); s['misses']=misses[:25]; s['confident_miss_threshold']=CONF; s['confident_miss_count']=sum(m['confident_miss'] for m in misses)

def movement(cps,res):
    by={int(cp['days_to_election']):{p['race_code']:p for p in cp.get('predictions',[])} for cp in cps if cp.get('state')=='scored'}
    if set(by)!=set(DAYS): return {'state':'unavailable','reason':'all_fixed_checkpoints_required'}
    common=set.intersection(*(set(by[d]) for d in DAYS))
    if any(set(by[d])!=common for d in DAYS): raise ValueError('fixed sample changed across checkpoints')
    transitions=[]
    for a,b in zip(DAYS,DAYS[1:]):
        moves=[]; toward=away=st=sa=0
        for c in common:
            m=(1 if res[c] else -1)*(float(by[b][c]['dem_probability'])-float(by[a][c]['dem_probability'])); moves.append(m); toward+=m>0; away+=m<0; st+=m>=MOVE; sa+=m<=-MOVE
        groups={}
        for label,codes in (('polled_at_later_checkpoint',[c for c in common if int(by[b][c].get('poll_count') or 0)>0]),('unpolled_at_later_checkpoint',[c for c in common if int(by[b][c].get('poll_count') or 0)==0])):
            dm=[(1 if res[c] else -1)*(float(by[b][c]['dem_probability'])-float(by[a][c]['dem_probability'])) for c in codes]; am=[abs(float(by[b][c]['dem_probability'])-float(by[a][c]['dem_probability'])) for c in codes]
            groups[label]={'n':len(codes),'mean_absolute_probability_change':round(sum(am)/len(am),6) if am else None,'mean_winner_directed_probability_change':round(sum(dm)/len(dm),6) if dm else None}
        if sum(g['n'] for g in groups.values())!=len(common): raise ValueError('poll-movement partition drift')
        transitions.append({'from_days':a,'to_days':b,'n':len(common),'mean_absolute_probability_change':round(sum(abs(m) for m in moves)/len(moves),6),'mean_winner_directed_probability_change':round(sum(moves)/len(moves),6),'toward_eventual_winner':toward,'away_from_eventual_winner':away,'strong_toward_eventual_winner':st,'strong_away_from_eventual_winner':sa,'polling_status_movement':groups,'polling_status_definition':'eligible race-level polling at the later checkpoint'})
    rows=[]
    for c in common:
        y=res[c]; sign=1 if y else -1; p60=float(by[60][c]['dem_probability']); p7=float(by[7][c]['dem_probability']); p1=float(by[1][c]['dem_probability']); final=by[1][c]; wp=float(final['dem_probability']) if y else float(final['rep_probability'])
        rows.append({'race_code':c,'race_type':final.get('race_type'),'winner':'DEM' if y else 'REP','winner_directed_change_60_to_1':round(sign*(p1-p60),6),'winner_directed_change_7_to_1':round(sign*(p1-p7),6),'late_absolute_change':round(abs(p1-p7),6),'strong_toward_winner':sign*(p1-p60)>=MOVE,'strong_away_from_winner':sign*(p1-p60)<=-MOVE,'large_late_swing':abs(p1-p7)>=MOVE,'final_winner_probability':round(wp,6),'final_confident_miss':wp<=1-CONF})
    return {'state':'scored','common_race_count':len(common),'movement_threshold':MOVE,'confident_miss_threshold':CONF,'transitions':transitions,'strongest_toward_eventual_winner':sorted(rows,key=lambda r:r['winner_directed_change_60_to_1'],reverse=True)[:15],'strongest_away_from_eventual_winner':sorted(rows,key=lambda r:r['winner_directed_change_60_to_1'])[:15],'large_late_swings':sorted((r for r in rows if r['large_late_swing']),key=lambda r:r['late_absolute_change'],reverse=True)[:20],'final_confident_misses':sorted((r for r in rows if r['final_confident_miss']),key=lambda r:r['final_winner_probability'])[:20]}

def band(score,label): return next((b for b in score.get('competitive_bands',[]) if b.get('band')==label),{})
def compare(cycles):
    rows=[]
    for cy in cycles:
        if cy.get('state')!='scored': continue
        cp={int(x['days_to_election']):x for x in cy['checkpoints']}; best=min(DAYS,key=lambda d:cp[d]['score']['brier']); d71=cp[1]['score']['brier']-cp[7]['score']['brier']
        rows.append({'cycle':cy['cycle'],'best_brier_checkpoint_days':best,'best_brier':cp[best]['score']['brier'],**{f'brier_{d}d':cp[d]['score']['brier'] for d in DAYS},'brier_change_14d_to_7d':round(cp[7]['score']['brier']-cp[14]['score']['brier'],8),'brier_change_7d_to_1d':round(d71,8),'brier_change_14d_to_1d':round(cp[1]['score']['brier']-cp[14]['score']['brier'],8),'final_week_direction':'improved' if d71<0 else 'weakened' if d71>0 else 'flat','gcb_14d':cp[14].get('generic_ballot_margin_d_minus_r'),'gcb_7d':cp[7].get('generic_ballot_margin_d_minus_r'),'gcb_1d':cp[1].get('generic_ballot_margin_d_minus_r'),'gcb_change_7d_to_1d':round(float(cp[1]['generic_ballot_margin_d_minus_r'])-float(cp[7]['generic_ballot_margin_d_minus_r']),4),'polled_races_14d':cp[14]['score']['polling']['polled']['n'],'polled_races_7d':cp[7]['score']['polling']['polled']['n'],'polled_races_1d':cp[1]['score']['polling']['polled']['n'],'competitive_20_80_brier_14d':band(cp[14]['score'],'20-80').get('brier'),'competitive_20_80_brier_7d':band(cp[7]['score'],'20-80').get('brier'),'competitive_20_80_brier_1d':band(cp[1]['score'],'20-80').get('brier'),'confident_misses_1d':cp[1]['score']['confident_miss_count']})
    hyp=[('late_generic_ballot_movement','diagnostic_exposed','14d, 7d and 1d generic-ballot margins'),('race_poll_composition','diagnostic_exposed','polling partitions and movement by polling status'),('pollster_mix','not_yet_decomposed','requires poll-source composition diagnostic'),('structural_priors_redistricting','not_yet_identified','requires pre-specified structural-only counterfactual'),('systematic_polling_error','not_yet_identified','requires poll-margin error decomposition'),('safe_seat_weighting','diagnostic_exposed','fixed competitive bands versus safe complement'),('late_overreaction','diagnostic_exposed_not_causal','7d→1d winner-directed movement and late swings'),('changing_race_coverage','diagnostic_exposed','polled counts at 14d, 7d and 1d')]
    return {'state':'scored' if len(rows)>=2 else 'partial','cycles':rows,'interpretation':'Cross-cycle contrasts are descriptive; race mix, chamber scope and polling availability differ, so they do not establish causation.','hypotheses':[{'id':a,'state':b,'evidence':c} for a,b,c in hyp]}

def enrich(p):
    if p.get('model_contract',{}).get('state')!='verified' or tuple(p.get('checkpoints_days_to_election',[]))!=DAYS: raise ValueError('model/checkpoint contract not verified')
    for cy in p.get('cycles',[]):
        if cy.get('state')!='scored': continue
        res=results(int(cy['cycle'])); cps=cy['checkpoints']
        if [int(x['days_to_election']) for x in cps]!=list(DAYS): raise ValueError('checkpoint sequence drift')
        for cp in cps: enrich_score(cp,res)
        cy['movement']=movement(cps,res); cy['chamber_scope']={}
        for chamber in ('house','senate'):
            counts=[cp['score']['chambers'][chamber]['n'] for cp in cps]; cy['chamber_scope'][chamber]={'state':'scored' if min(counts)>0 else 'unavailable','race_counts_by_checkpoint':counts,'reason':None if min(counts)>0 else 'no_admitted_complete_chamber_replay'}
    p['schema_version']='1.1.0'; p['diagnostic_contract']={'competitive_bands':[{'label':a,'lower':b,'upper':c,'nested':True} for a,b,c in BANDS],'safe_definition':'p_dem < 0.20 or p_dem > 0.80','calibration_bin_width':.10,'movement_threshold':MOVE,'confident_miss_threshold':CONF,'rule':'Thresholds are fixed before reviewing results and are not model coefficients.'}
    p['metric_definitions'].update({'accuracy':'Share of races where the side at or above 50% won; secondary to proper scoring rules.','calibration':'Fixed 10-point bins comparing mean Democratic probability with observed Democratic win rate.','calibration_residual':'Observed Democratic win rate minus mean forecast probability.','mean_absolute_bin_calibration_error':'Count-weighted mean absolute residual across occupied fixed bins.','polling_partitions':'Conditional performance with versus without eligible race-level polls; not causal.','winner_directed_movement':'Post-outcome forensic sign on frozen probability movement; positive means toward eventual winner.'})
    guard='Post-replay diagnostics read certified outcomes only after checkpoint predictions are frozen; they cannot alter predictive inputs or coefficients.'
    if guard not in p['leakage_guards']: p['leakage_guards'].append(guard)
    p['cross_cycle']=compare(p.get('cycles',[])); return p

def main():
    p=json.loads(OUT.read_text()); OUT.write_text(json.dumps(enrich(p),indent=2)+'\n'); print(json.dumps({'output':str(OUT),'schema_version':'1.1.0'}))
if __name__=='__main__': main()
