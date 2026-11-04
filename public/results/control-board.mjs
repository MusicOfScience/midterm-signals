// Independent civicAPI chamber-control and a separately timed Guardian checkpoint.
import {controlDesk,reconcileReference,SENATE_HOLDOVERS} from "./control-core.mjs";
const $=id=>document.getElementById(id);
const fmt=n=>new Intl.NumberFormat("en-US").format(n);
const melbourne=value=>{
 if(!value)return "Unknown time";
 const d=new Date(value);
 return Number.isFinite(d.getTime())?d.toLocaleString("en-AU",{timeZone:"Australia/Melbourne",day:"numeric",month:"short",hour:"2-digit",minute:"2-digit",hour12:false,timeZoneName:"short"}):"Unknown time";
};
let latestRender=0;
const referencePromise=fetch("/data/newsroom-checkpoints.json",{cache:"no-store"}).then(r=>{
 if(!r.ok)throw Error("Newsroom reference unavailable");
 return r.json();
}).catch(()=>null);
const set=(id,value)=>{$(id).textContent=String(value)};
const showRows=entries=>{
 const frag=document.createDocumentFragment();
 for(const fields of entries){
  const tr=document.createElement("tr");
  for(const value of fields){
   const td=document.createElement("td");td.textContent=String(value);tr.append(td);
  }
  frag.append(tr);
 }
 $("compareRows").replaceChildren(frag);
};
function paintSegments(id,chamber){
 const bar=$(id),fragment=document.createDocumentFragment(),words=[];
 for(const part of chamber.segments){
  words.push(part.count+" "+part.label.toLowerCase());
  if(!part.count)continue;
  const el=document.createElement("span");el.className=part.id;
  el.style.flexBasis=(100*part.count/chamber.total)+"%";
  el.title=part.count+" "+part.label;
  el.setAttribute("aria-hidden","true");fragment.append(el);
 }
 bar.replaceChildren(fragment);
 bar.setAttribute("aria-label",chamber.total+" seats: "+words.join(", ")+".");
}
function showChambers(desk){
 const S=desk.senate,H=desk.house;
 set("senateD",fmt(S.D));set("senateR",fmt(S.R));
 set("houseD",fmt(H.D));set("houseR",fmt(H.R));
 set("senateVerdict",S.verdict.text+" · "+S.verdict.reason);
 set("houseVerdict",H.verdict.text+" · "+H.verdict.reason);
 paintSegments("senateSegments",S);paintSegments("houseSegments",H);
 set("senateBreakdown",SENATE_HOLDOVERS.D+" D-aligned holdovers (32 Democrats + two allied independents) + "+S.calledByParty.D+" D calls; "+SENATE_HOLDOVERS.R+" R holdovers + "+S.calledByParty.R+" R calls.");
 set("houseBreakdown",H.calledByParty.D+" D calls · "+H.calledByParty.R+" R calls · "+H.calledByParty.other+" other-party calls; "+H.uncalled+" unresolved.");
 set("senateUncalled",S.called+" / 35 contests called; "+S.uncalled+" uncalled. Among uncalled: "+S.leads.D+" D leads · "+S.leads.R+" R leads · "+S.leads.other+" other leads. Leads do not increase secured-seat totals.");
 set("houseUncalled",H.called+" / 435 contests called; among "+H.uncalled+" uncalled: "+H.leads.D+" D leads · "+H.leads.R+" R leads · "+H.leads.other+" other leads. No-vote races remain unresolved.");
 set("controlClock","Stored "+desk.source+" source: "+melbourne(desk.sourceUpdatedAt)+" Melbourne time · checked "+melbourne(desk.fetchedAt)+". Calls are not certifications.");
}
function showReconciliation(recon){
 const ref=recon.reference;
 if(!ref){
  set("compareState","NO REFERENCE");
  set("compareExplanation","The archived Guardian screenshot reference could not load.");
  showRows([["House","civicAPI only",recon.desk.house.D,recon.desk.house.R,recon.desk.house.called]]);
  set("compareDelta","No comparative conclusion without a verified reference.");
  return;
 }
 const d=recon.desk;
 showRows([
  ["House","civicAPI · "+melbourne(d.sourceUpdatedAt),fmt(d.house.D),fmt(d.house.R),d.house.called+" / 435"],
  ["House","Guardian · "+melbourne(ref.captured_at),fmt(ref.house.D),fmt(ref.house.R),ref.house.called+" / 435"],
  ["Senate","civicAPI · "+melbourne(d.sourceUpdatedAt),fmt(d.senate.D),fmt(d.senate.R),d.senate.called+" / 35"],
  ["Senate","Guardian · "+melbourne(ref.captured_at),fmt(ref.senate.D),fmt(ref.senate.R),ref.senate.called+" / 35"]
 ]);
 const label=recon.state==="aligned"?"MATCHING CLOSE-TIME TOTALS":recon.state==="near-time-difference"?"NEAR-TIME DISCREPANCY":recon.state==="historical-only"?"HISTORICAL REFERENCE ONLY":"COMPARISON WITHHELD";
 set("compareState",label);
 const delta=v=>v===0?"0":(v>0?"+":"")+v;
 if(recon.deltas){
  const H=recon.deltas.house,S=recon.deltas.senate;
  set("compareExplanation","The publisher snapshots were "+recon.minutesApart+" minutes apart. Not exactly synchronised.");
  set("compareDelta","civicAPI − Guardian: House D "+delta(H.D)+", R "+delta(H.R)+", called "+delta(H.called)+". Senate D-aligned "+delta(S.D)+", R "+delta(S.R)+", contests called "+delta(S.called)+". "+recon.note);
 }else{
  set("compareExplanation","Guardian screenshot captured "+melbourne(ref.captured_at)+"; civicAPI source time "+melbourne(d.sourceUpdatedAt)+".");
  set("compareDelta",recon.note||"No meaningful comparison can be established without contemporaneous data.");
 }
}
async function render(){
 const version=++latestRender,data=window.__MS_RESULTS__;
 if(!data?.sources?.[0])return;
 const feed=data.sources[0],desk=controlDesk(feed);
 showChambers(desk);
 const reference=await referencePromise;
 if(version!==latestRender)return;
 showReconciliation(reconcileReference(feed,reference));
}
function showError(error){
 set("compareState","CONTROL BOARD ERROR");
 set("compareExplanation","The observation-only control board could not load: "+error.message);
}
window.addEventListener("ms:results-updated",()=>{render().catch(showError)});
render().catch(showError);
