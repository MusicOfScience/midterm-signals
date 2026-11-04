// MIDTERM SIGNALS Results Desk: pure, model-safe presentation calculations.
// No forecast probability, coefficient, or historical archive is mutated.
export const FROZEN_FORECAST = "/data/history/2026-11-03T192932Z.json";

export function modelKeyFromSource(id) {
  const h=/^H-([A-Z]{2})-(\d{1,2}|AL|00)$/i.exec(String(id||""));
  if(h)return h[1].toUpperCase()+"-"+(h[2].toUpperCase()==="AL"||h[2]==="00"?"01":h[2].padStart(2,"0"));
  const s=/^S-([A-Z]{2})(?:-(sp|special))?$/i.exec(String(id||""));
  if(s)return s[1].toUpperCase()+"-SEN";
  return null;
}

export function finite(value) {
  if(value===null||value===undefined||value==="")return null;
  const n=Number(value);
  return Number.isFinite(n)?n:null;
}
export function twoPartyMargin(candidates) {
  if(!Array.isArray(candidates))return null;
  let d=0,r=0,hasD=false,hasR=false;
  for(const c of candidates) {
    if(c.party==="D"){hasD=true;d+=finite(c.votes)??0}
    if(c.party==="R"){hasR=true;r+=finite(c.votes)??0}
  }
  if(!hasD||!hasR||d+r===0)return null;
  return 100*(d-r)/(d+r);
}
export function assemble(forecast, observed) {
  if(!Array.isArray(forecast?.races)||forecast.races.length<435)
    throw new Error("The frozen pre-election forecast is missing or incomplete.");
  const indexed=new Map();
  for(const o of observed?.races||[]) {
    if(!o||typeof o.model_code!=="string")continue;
    // An ambiguous pair of Senate special and regular contests must never be silently joined.
    if(indexed.has(o.model_code))indexed.set(o.model_code,null);
    else indexed.set(o.model_code,o);
  }
  return forecast.races.filter(r=>r.race_type==="house"||r.race_type==="senate").map(r=>{
    const o=indexed.get(r.race_code)||null;
    const votes=o?.votes_total>0?o.votes_total:null;
    const margin=votes?twoPartyMargin(o.candidates):null;
    const predicted=finite(r.forecast_margin_d_minus_r);
    const gap=margin===null||predicted===null?null:margin-predicted;
    const lead=votes?o.leader:null;
    return {id:r.race_code,office:r.race_type,state:r.state,district:r.district,
      candidateD:r.dem_candidate||"",candidateR:r.rep_candidate||"",
      forecast_margin:predicted,dem_probability:finite(r.dem_probability),
      rating:r.rating||"",votes,observed:o,
      lead:lead||null,called:Boolean(o?.called&&o?.called_by),
      winner:o?.called&&o?.called_by?o.winner:null,called_by:o?.called_by||null,
      observed_margin:margin,gap};
  });
}
export function totals(rows) {
  const reporting=rows.filter(r=>r.votes!==null);
  const called=rows.filter(r=>r.called);
  const count=(collection,party)=>collection.filter(r=>(collection===called?r.winner:r.lead)?.party===party).length;
  const house=rows.filter(r=>r.office==="house"),senate=rows.filter(r=>r.office==="senate");
  return {universe:rows.length,reporting:reporting.length,called:called.length,
    house:{reporting:house.filter(r=>r.votes!==null).length,calledD:house.filter(r=>r.called&&r.winner?.party==="D").length,
      calledR:house.filter(r=>r.called&&r.winner?.party==="R").length},
    senate:{reporting:senate.filter(r=>r.votes!==null).length,calledD:senate.filter(r=>r.called&&r.winner?.party==="D").length,
      calledR:senate.filter(r=>r.called&&r.winner?.party==="R").length},
    leadsD:count(reporting,"D"),leadsR:count(reporting,"R")};
}
export function filterRows(rows,{chamber="all",state="all",query="",reported=false,sort="status"}={}) {
  const q=query.toLowerCase().trim();
  const selected=rows.filter(r=>(chamber==="all"||r.office===chamber)
    &&(state==="all"||r.state===state)
    &&(!reported||r.votes!==null)
    &&(!q||[r.id,r.state,r.candidateD,r.candidateR,r.observed?.leader?.name].join(" ").toLowerCase().includes(q)));
  return selected.sort((a,b)=>{
    if(sort==="closest")return Math.abs(a.forecast_margin??999)-Math.abs(b.forecast_margin??999)||a.id.localeCompare(b.id);
    if(sort==="gap")return Math.abs(b.gap??-1)-Math.abs(a.gap??-1)||a.id.localeCompare(b.id);
    if(sort==="votes")return (b.votes??-1)-(a.votes??-1)||a.id.localeCompare(b.id);
    if(sort==="id")return a.id.localeCompare(b.id);
    return Number(b.called)-Number(a.called)||(b.votes??-1)-(a.votes??-1)||a.id.localeCompare(b.id);
  });
}
export const signed=n=>n===null||!Number.isFinite(n)?"—":(n>=0?"D +":"R +")+Math.abs(n).toFixed(1);
export function csvValue(value) {
  let s=String(value??"");
  // Keep exported CSV safe to open in spreadsheet software.
  if(/^[\s]*[=+\-@\t\r]/.test(s))s="'"+s;
  return '"'+s.replaceAll('"','""')+'"';
}
export function exportCsv(rows) {
  const headers=["race","chamber","state","district","votes_counted","counting_leader","called_winner","call_source","observed_two_party_d_minus_r_pp","pre_election_forecast_d_minus_r_pp","observed_minus_forecast_pp","observed_source"];
  const body=rows.map(r=>[r.id,r.office,r.state,r.district,r.votes,r.lead?.name,r.winner?.name,r.called_by,r.observed_margin?.toFixed(3),r.forecast_margin,r.gap?.toFixed(3),r.observed?.source_url].map(csvValue).join(","));
  return [headers.join(","),...body].join("\r\n")+"\r\n";
}
