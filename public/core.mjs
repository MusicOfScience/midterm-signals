export const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
export const pct=(v,digits=0)=>Number.isFinite(v)?`${(100*v).toFixed(digits)}%`:'—';
export const signed=(v,digits=1)=>Number.isFinite(v)?`${v>=0?'D +':'R +'}${Math.abs(v).toFixed(digits)}`:'—';
export const fmt=(v,digits=1)=>Number.isFinite(v)?Number(v).toFixed(digits):'—';
export const slugify=s=>String(s||'').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
export const raceLabel=r=>r?.race_type==='senate'?`${r.state} Senate`:r?.race_code||'Race';
export const winSide=r=>r.dem_probability>=0.5?'D':'R';
export const winProbability=r=>Math.max(r.dem_probability,1-r.dem_probability);
export const uncertaintyScore=r=>1-Math.abs((r.dem_probability??.5)-.5)*2;

export function erf(x){
  const sign=x<0?-1:1; x=Math.abs(x);
  const a1=.254829592,a2=-.284496736,a3=1.421413741,a4=-1.453152027,a5=1.061405429,p=.3275911;
  const t=1/(1+p*x);
  const y=1-(((((a5*t+a4)*t)+a3)*t+a2)*t+a1)*t*Math.exp(-x*x);
  return sign*y;
}
export const normalCdf=z=>.5*(1+erf(z/Math.SQRT2));
export const probabilityFromMargin=(margin,sigma)=>clamp(normalCdf(margin/Math.max(.01,sigma)),.001,.999);

export function seeded(seed=20261103){
  let x=seed>>>0;
  return ()=>{x=(1664525*x+1013904223)>>>0;return x/4294967296};
}
export function normalSample(rng){
  let u=0,v=0; while(u===0)u=rng(); while(v===0)v=rng();
  return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);
}
export function quantile(values,q){
  if(!values.length)return null;
  const a=[...values].sort((x,y)=>x-y),i=Math.round((a.length-1)*q); return a[i];
}
export function summarizeCounts(values,total,threshold){
  const mean=values.reduce((a,b)=>a+b,0)/Math.max(1,values.length);
  const control=values.filter(v=>v>=threshold).length/Math.max(1,values.length);
  const histogram={}; for(const v of values) histogram[v]=(histogram[v]||0)+1;
  const mode=Number(Object.entries(histogram).sort((a,b)=>b[1]-a[1]||Number(a[0])-Number(b[0]))[0]?.[0]??0);
  const interval=p=>[quantile(values,(1-p)/2),quantile(values,1-(1-p)/2)];
  return {dem_control_probability:control,rep_control_probability:1-control,expected_dem_seats:mean,expected_rep_seats:total-mean,median_dem_seats:quantile(values,.5),modal_dem_seats:mode,dem_seats_50_interval:interval(.5),dem_seats_80_interval:interval(.8),dem_seats_90_interval:interval(.9),dem_seats_95_interval:interval(.95),distribution:Object.entries(histogram).map(([seats,count])=>({seats:Number(seats),probability:count/values.length})).sort((a,b)=>a.seats-b.seats)};
}

export function runScenario(model,{houseSwing=0,senateSwing=0,genericBallotShift=0,overrides={}}={},n=6000){
  const races=model.races||[];
  const house=races.filter(r=>r.race_type==='house');
  const senate=races.filter(r=>r.race_type==='senate');
  const fixed=model.summary?.senate?.fixed_not_up_dem_seats??34;
  const rng=seeded(20261103+Math.round((houseSwing+senateSwing+genericBallotShift)*1000));
  const hc=[],sc=[]; let joint={dd:0,dr:0,rd:0,rr:0};
  for(let i=0;i<n;i++){
    const nh=normalSample(rng)*2.7,ns=normalSample(rng)*2.4;
    let hd=0;
    for(const r of house){
      const override=overrides[r.race_code];
      if(override==='D'){hd++;continue} if(override==='R')continue;
      const m=(r.forecast_margin_d_minus_r||0)+houseSwing+genericBallotShift+nh+normalSample(rng)*4.7;
      if(m>0)hd++;
    }
    let sd=fixed;
    for(const r of senate){
      const override=overrides[r.race_code];
      if(override==='D'){sd++;continue} if(override==='R')continue;
      if(r.same_party==='DEM'){sd++;continue} if(r.same_party==='REP')continue;
      const m=(r.forecast_margin_d_minus_r||0)+senateSwing+genericBallotShift+ns+normalSample(rng)*5;
      if(m>0)sd++;
    }
    hc.push(hd);sc.push(sd);
    const hD=hd>=218,sD=sd>=51; joint[hD?(sD?'dd':'dr'):(sD?'rd':'rr')]++;
  }
  const h=summarizeCounts(hc,435,218),s=summarizeCounts(sc,100,51);
  return {house:h,senate:s,joint_control:{dem_house_dem_senate:joint.dd/n,dem_house_rep_senate:joint.dr/n,rep_house_dem_senate:joint.rd/n,rep_house_rep_senate:joint.rr/n},simulations:n};
}

export function filterRaces(races,filters={}){
  const {chamber='all',state='all',party='all',minProb=0,maxProb=1,competitiveness='all',polling='all',movement='all',query=''}=filters;
  const q=String(query).trim().toLowerCase();
  return races.filter(r=>{
    if(chamber!=='all'&&r.race_type!==chamber)return false;
    if(state!=='all'&&r.state!==state)return false;
    const p=r.dem_probability??.5;
    if(p<minProb||p>maxProb)return false;
    if(party==='dem-held'&&r.seat_holder!=='DEM')return false;
    if(party==='rep-held'&&r.seat_holder!=='REP')return false;
    if(party==='dem-flip'&&!(r.seat_holder==='REP'&&p>.5))return false;
    if(party==='rep-flip'&&!(r.seat_holder==='DEM'&&p<.5))return false;
    if(competitiveness==='tossup'&&!(p>=.45&&p<=.55))return false;
    if(competitiveness==='competitive'&&!(p>=.3&&p<=.7))return false;
    if(competitiveness==='uncertain'&&!(p>=.4&&p<=.6))return false;
    if(polling==='recent'&&!r.latest_race_poll)return false;
    if(polling==='none'&&r.latest_race_poll)return false;
    const delta=r.change?.dem_probability??0;
    if(movement==='big'&&Math.abs(delta)<.05)return false;
    if(q&&!`${r.race_code} ${r.state} ${r.dem_candidate||''} ${r.rep_candidate||''} ${r.rating||''}`.toLowerCase().includes(q))return false;
    return true;
  });
}

export function searchRecords(model){
  if(Array.isArray(model.search_index)&&model.search_index.length)return model.search_index;
  const out=[]; const seen=new Set();
  for(const r of model.races||[]){
    out.push({type:'race',label:raceLabel(r),subtitle:`${r.dem_candidate||'—'} vs ${r.rep_candidate||'—'}`,key:r.race_code,terms:[r.race_code,r.state,r.dem_candidate,r.rep_candidate].filter(Boolean).join(' ')});
    for(const [party,name] of [['D',r.dem_candidate],['R',r.rep_candidate]]) if(name&&!seen.has(`c:${name}`)){seen.add(`c:${name}`);out.push({type:'candidate',label:name,subtitle:`${party} · ${raceLabel(r)}`,key:name,terms:`${name} ${r.state} ${r.race_code}`})}
  }
  const pollsters=new Set((model.polls||model.national_environment?.recent_polls||[]).map(p=>p.pollster).filter(Boolean));
  for(const p of pollsters)out.push({type:'pollster',label:p,subtitle:'Pollster',key:p,terms:p});
  for(const f of ['Cook Political Report','Inside Elections',"Sabato's Crystal Ball",'Silver Bulletin','Decision Desk HQ'])out.push({type:'forecaster',label:f,subtitle:'External forecaster',key:f,terms:f});
  return out;
}

export function scoreSearch(record,query){
  const q=String(query).trim().toLowerCase(); if(!q)return 0;
  const label=String(record.label||'').toLowerCase(),terms=String(record.terms||'').toLowerCase();
  if(label===q)return 100;if(label.startsWith(q))return 70;if(terms.includes(q))return 40;return 0;
}

export function buildElectionSummary(assignments,races,summary){
  const house=races.filter(r=>r.race_type==='house'),senate=races.filter(r=>r.race_type==='senate');
  const fixed=summary?.senate?.fixed_not_up_dem_seats??34;
  const count=(arr,base=0)=>arr.reduce((n,r)=>n+(assignments[r.race_code]==='D'?1:0),base);
  const unassigned=(arr)=>arr.filter(r=>!assignments[r.race_code]).length;
  const hd=count(house),sd=count(senate,fixed); return {houseDem:hd,houseRep:435-hd-unassigned(house),houseUnassigned:unassigned(house),senateDem:sd,senateRep:100-sd-unassigned(senate),senateUnassigned:unassigned(senate),houseControl:hd>=218?'D':435-hd-unassigned(house)>=218?'R':'Open',senateControl:sd>=51?'D':100-sd-unassigned(senate)>=50?'R':'Open'};
}
