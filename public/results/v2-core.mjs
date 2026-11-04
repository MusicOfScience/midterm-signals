// MIDTERM SIGNALS / Results Desk v2 – observation-only analysis.
// Every computed margin is provisional unless externally certified.
// Never infer national vote shares from incomplete geographic coverage.
const isValid=n=>typeof n==="number"&&Number.isFinite(n);
export function percent(value,places=1) {
  return isValid(value)?value.toFixed(places)+"%":"—";
}
export function signedMargin(value) {
  return !isValid(value)?"—":(value>=0?"D +":"R +")+Math.abs(value).toFixed(1);
}
export function ageLabel(date,now=Date.now()) {
  if(!date)return {label:"Timestamp unavailable",state:"unknown",hours:null};
  const parsed=Date.parse(date);if(!Number.isFinite(parsed))return {label:"Invalid source timestamp",state:"unknown",hours:null};
  const hours=Math.max(0,(now-parsed)/3600000);
  return {label:hours<1?Math.round(hours*60)+" min old":hours<24?hours.toFixed(1)+" h old":Math.floor(hours/24)+" d old",
    state:hours<=3?"recent":hours<=12?"delayed":"stale",hours};
}
export function hasTwoParty(r) {
  const cs=r?.observed?.candidates||[];
  return cs.some(c=>c.party==="D")&&cs.some(c=>c.party==="R");
}
export function stateInsight(rows,state,layer="coverage") {
  const all=rows.filter(r=>r.state===state&&(layer==="senate"?r.office==="senate":layer==="house"?r.office==="house":true));
  const counted=all.filter(r=>r.votes!==null);
  const withMargin=counted.filter(r=>hasTwoParty(r));
  const observedD=withMargin.reduce((s,r)=>s+r.observed.candidates.filter(c=>c.party==="D").reduce((n,c)=>n+(Number(c.votes)||0),0),0);
  const observedR=withMargin.reduce((s,r)=>s+r.observed.candidates.filter(c=>c.party==="R").reduce((n,c)=>n+(Number(c.votes)||0),0);
  const margin=observedD+observedR>0?100*(observedD-observedR)/(observedD+observedR):null;
  const pct=all.length?100*counted.length/all.length:null;
  const ambiguous=all.some(r=>r.observed===null&&r.votes===null&&r.ambiguous);
  return {state,tracked:all.length,counted:counted.length,coverage:pct,twoPartyRaces:withMargin.length,
    observedD,observedR,margin,called:all.filter(r=>r.called).length,ambiguous};
}
export function analyse(rows) {
  const seen=rows.filter(r=>r.votes!==null);
  const called=rows.filter(r=>r.called);
  const comparable=seen.filter(r=>isValid(r.observed_margin)&&isValid(r.forecast_margin));
  const reliable=comparable.filter(r=>isValid(r.observed?.reporting_unit_pct)&&r.observed.reporting_unit_pct>=95);
  const unknownPrecinct=seen.filter(r=>!isValid(r.observed?.reporting_unit_pct)).length;
  const sourceCount={};
  for(const r of seen)sourceCount[r.observed?.source_name||"Unspecified source"]=(sourceCount[r.observed?.source_name||"Unspecified source"]||0)+1;
  const top=[...comparable].sort((a,b)=>Math.abs(b.gap)-Math.abs(a.gap)).slice(0,6);
  const byState=new Map();
  for(const r of rows){if(!byState.has(r.state))byState.set(r.state,0);if(r.votes!==null)byState.set(r.state,byState.get(r.state)+1)}
  return {tracked:rows.length,seen:seen.length,called:called.length,comparable:comparable.length,
    reliable:reliable.length,unknownPrecinct,sourceCount,top,
    statesWithCount:[...byState.values()].filter(n=>n>0).length,statesTracked:byState.size};
}
export function splitFeedStates(sources) {
  return sources.map(s=>{const races=Array.isArray(s?.races)?s.races:[],n=races.filter(r=>r.votes_total>0).length;
    return {id:s.source||"unknown",reporting:n,races:races.length,asOf:s.source_updated_at||null,
      fetchedAt:s.fetched_at||null,health:s.health||"unknown",url:s.source_url||null};
  });
}
export function comparability(row) {
  if(row.votes===null)return {state:"no-votes",text:"No observed returns"};
  if(!isValid(row.observed_margin))return {state:"non-comparable",text:"Two-party margin unavailable"};
  const pct=row.observed?.reporting_unit_pct;
  if(isValid(pct))return {state:pct>=99.9?"near-complete":"provisional",text:pct>=99.9?"Reporting units 100% · not certified":percent(pct)+" reporting units · provisional"};
  return {state:"unknown-coverage",text:"Reporting-unit coverage unknown · provisional"};
}
export function swingStudy(rows) {
  // These are vote count discrepancies, NOT historical 2024-26 swing.
  const eligible=rows.filter(r=>r.votes!==null&&isValid(r.gap)&&isValid(r.observed?.reporting_unit_pct)&&r.observed.reporting_unit_pct>=95);
  if(eligible.length<5)return {state:"insufficient",n:eligible.length,note:"At least five comparable races with 95%+ reporting units are required. This does not imply certification."};
  const gaps=eligible.map(r=>r.gap).sort((a,b)=>a-b);
  const median=gaps.length%2?gaps[(gaps.length-1)/2]:(gaps[gaps.length/2-1]+gaps[gaps.length/2])/2;
  return {state:"provisional",n:eligible.length,medianGap:median,
    note:"Median observed minus frozen-model margin in qualifying races; not a national swing or a final forecast score."};
}
