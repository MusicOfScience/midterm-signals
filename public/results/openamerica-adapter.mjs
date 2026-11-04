// Browser-only secondary adapter. Open America permits direct CORS display
// of state-office counts. Do not republish its complete feed as a data service.
import {modelKeyFromSource} from "./desk-core.mjs";
const expectedOffice={House:"house",Senate:"senate"};
export function normaliseOpenAmerica(raw){
  if(!raw||raw.api!==1||raw.year!==2026||!expectedOffice[raw.office]||
     !raw.races||typeof raw.races!=="object"||Array.isArray(raw.races))
    throw new Error("Open America API contract/year/office mismatch");
  const races=[];
  for(const [seat,v] of Object.entries(raw.races)){
    if(!v||!Array.isArray(v.cands))continue;
    const sourceId=raw.office==="House"?"H-"+seat:"S-"+seat.replace(/-special$/i,"-sp");
    const code=modelKeyFromSource(sourceId);
    if(!code)continue;
    const candidates=v.cands.filter(c=>c&&typeof c==="object").map(c=>({
      name:String(c.n||""),party:String(c.p||"?").toUpperCase(),
      votes:Number.isSafeInteger(c.v)&&c.v>=0?c.v:0,winner:false
    }));
    if(!candidates.length)continue;
    const total=candidates.reduce((s,c)=>s+c.votes,0);
    const leader=total>0?candidates.reduce((a,c)=>c.votes>a.votes?c:a,candidates[0]):null;
    races.push({race_id:sourceId,model_code:code,chamber:expectedOffice[raw.office],
      state:code.slice(0,2),candidates,votes_total:total,leader,called:false,winner:null,called_by:null,
      source_name:"Official state election offices via Open America",
      source_url:"https://openamerica.io/elections/api/",
      source_updated_at:typeof raw.as_of==="string"?raw.as_of:null,
      reporting_unit_pct:typeof v.pct_in==="number"?v.pct_in:null});
  }
  return {schema_version:1,source:"openamerica",source_updated_at:raw.as_of||null,
    fetched_at:new Date().toISOString(),state:races.some(r=>r.votes_total>0)?"reporting":"awaiting_results",races};
}
export function combineFeeds(feeds){
  const all=new Map(),priority={thepeoplestally:2,openamerica:1};
  for(const feed of feeds){
    if(!feed||!Array.isArray(feed.races))continue;
    const within=new Map();
    for(const r of feed.races){
      const entries=within.get(r.model_code)||[];entries.push(r);within.set(r.model_code,entries);
    }
    for(const [key,entries] of within){
      const choices=all.get(key)||[];
      if(entries.length>1){all.set(key,entries);continue}
      if(choices.length>1)continue;
      choices.push({...entries[0],_feed:feed.source});
      all.set(key,choices);
    }
  }
  const races=[];
  for(const choices of all.values()){
    if(choices.length===1){races.push(choices[0]);continue}
    const reported=choices.filter(r=>r.votes_total>0);
    const pool=reported.length?reported:choices;
    const best=[...pool].sort((a,b)=>(priority[b._feed]||0)-(priority[a._feed]||0))[0];
    races.push(best);
  }
  const actual=feeds.filter(f=>f&&f.races?.length);
  return {schema_version:1,source:actual.map(f=>f.source).join(" + ")||"unavailable",
    fetched_at:new Date().toISOString(),source_updated_at:actual.map(f=>f.source_updated_at).filter(Boolean).sort().at(-1)||null,
    state:races.some(r=>r.votes_total>0)?"reporting":"awaiting_results",races};
}
