// Opportunistic browser adapter for the public, CC BY 4.0 People's Tally snapshot.
// A network failure never overwrites the checked repository snapshot.
import {modelKeyFromSource} from "./desk-core.mjs";
function party(p){const x=String(p||"").trim().toUpperCase();return x==="D"||x==="DEM"||x==="DEMOCRATIC"?"D":x==="R"||x==="REP"||x==="REPUBLICAN"?"R":x||"?"}
export function normaliseClient(raw){
  if(!raw||typeof raw.races!=="object"||raw.races===null||Array.isArray(raw.races))throw new Error("Invalid provider payload");
  const out=[];
  for(const [id,item] of Object.entries(raw.races)){
    const key=modelKeyFromSource(id);if(!key||!item||!Array.isArray(item.cands))continue;
    const candidates=item.cands.map(c=>({name:String(c.name||""),party:party(c.party),
      votes:Number.isSafeInteger(c.votes)&&c.votes>=0?c.votes:0,winner:c.winner===true}));
    const total=candidates.reduce((a,c)=>a+c.votes,0),leader=total?candidates.reduce((a,c)=>c.votes>a.votes?c:a,candidates[0]):null;
    const caller=typeof item.called_by==="string"?item.called_by.trim():"";
    const winner=caller?candidates.find(c=>c.winner)||null:null;
    out.push({race_id:id,model_code:key,chamber:id.startsWith("H-")?"house":"senate",state:key.slice(0,2),
      candidates,votes_total:total,leader,called:Boolean(winner),winner,called_by:winner?caller:null,
      source_url:typeof item.url==="string"&&item.url.startsWith("https://")?item.url:null,source_name:item.src||"The People's Tally"});
  }
  return {schema_version:1,source:"thepeoplestally",source_updated_at:raw.generated_at||null,
    fetched_at:new Date().toISOString(),state:out.some(r=>r.votes_total)?"reporting":"awaiting_results",races:out};
}
