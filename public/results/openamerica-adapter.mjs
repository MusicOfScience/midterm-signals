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
// Preserve the fact that two different contests can share a model identifier.
// Never combine counts across different feeds, never average two providers,
// and never turn a counting leader into a called winner.
export function combineFeeds(feeds){
  const grouped=new Map(),ambiguous=new Set();
  for(const feed of feeds){
    if(!feed||!Array.isArray(feed.races))continue;
    const local=new Map();
    for(const item of feed.races){
      if(!item||!item.model_code)continue;
      const arr=local.get(item.model_code)||[];arr.push(item);local.set(item.model_code,arr);
    }
    for(const [key,items] of local){
      if(items.length>1){ambiguous.add(key);continue}
      const prior=grouped.get(key)||[];prior.push({...items[0],_feed:feed.source||"unknown"});grouped.set(key,prior);
    }
  }
  const priority={thepeoplestally:2,openamerica:1};
  const races=[];
  for(const [key,choices] of grouped){
    if(ambiguous.has(key))continue;
    const ranked=choices.slice().sort((a,b)=>{
      if(Boolean(a.called)!==Boolean(b.called))return Number(b.called)-Number(a.called);
      const aVotes=a.votes_total>0,bVotes=b.votes_total>0;
      if(aVotes!==bVotes)return Number(bVotes)-Number(aVotes);
      const ta=Date.parse(a.source_updated_at||""),tb=Date.parse(b.source_updated_at||"");
      if(Number.isFinite(ta)&&Number.isFinite(tb)&&Math.abs(tb-ta)>3600000)return tb-ta;
      return (priority[b._feed]||0)-(priority[a._feed]||0);
    });
    races.push(ranked[0]);
  }
  const used=feeds.filter(f=>f&&f.races?.length);
  const timestamps=used.map(f=>f.source_updated_at).filter(x=>x&&Number.isFinite(Date.parse(x))).sort();
  return {schema_version:1,source:used.map(f=>f.source).join(" + ")||"unavailable",
    fetched_at:new Date().toISOString(),source_updated_at:timestamps.at(-1)||null,
    state:races.some(r=>r.votes_total>0)?"reporting":"awaiting_results",ambiguous_keys:[...ambiguous],races};
}
