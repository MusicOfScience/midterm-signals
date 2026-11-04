import {analyse,ageLabel,comparability,percent,signedMargin,stateInsight,swingStudy} from "./v2-core.mjs";
import {drawStateMap} from "./geo-map.mjs";
const $=id=>document.getElementById(id);
const SVGNS="http://www.w3.org/2000/svg";
const n=(tag,text,cls)=>{const el=document.createElement(tag);el.textContent=text??"";if(cls)el.className=cls;return el};
const num=x=>new Intl.NumberFormat("en-US").format(x??0);
let latest=null,renderVersion=0;
const current=()=>window.__MS_RESULTS__||latest;
function chart(rows){
 const cell=$("marginScatter"),compared=rows.filter(r=>r.votes!==null&&Number.isFinite(r.observed_margin)&&Number.isFinite(r.forecast_margin));
 if(compared.length<3){cell.replaceChildren(n("p","Only "+compared.length+" comparable races currently reporting. Three are required before a plot is published. No missing returns are imputed."));return}
 const subset=[...compared];
 const limit=Math.max(10,...subset.flatMap(r=>[Math.abs(r.observed_margin),Math.abs(r.forecast_margin)]));
 const span=Math.min(100,Math.ceil(limit/10)*10),W=760,H=276,pad={l:54,r:30,t:24,b:45};
 const X=v=>pad.l+(v+span)/(2*span)*(W-pad.l-pad.r),Y=v=>H-pad.b-(v+span)/(2*span)*(H-pad.t-pad.b);
 const svg=document.createElementNS(SVGNS,"svg");
 svg.setAttribute("viewBox","0 0 "+W+" "+H);svg.setAttribute("class","plot-svg");svg.setAttribute("role","img");
 svg.setAttribute("aria-label","Scatter plot of frozen forecast D minus R against observed D minus R in "+subset.length+" reporting races");
 const create=(tag,attrs,text)=>{const el=document.createElementNS(SVGNS,tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;svg.append(el);return el};
 create("rect",{x:pad.l,y:pad.t,width:W-pad.l-pad.r,height:H-pad.t-pad.b,fill:"#f3f0e9"});
 for(const v of [-span,-span/2,0,span/2,span]){
  create("line",{x1:X(v),y1:pad.t,x2:X(v),y2:H-pad.b,stroke:"#d3cec2","stroke-width":1});
  create("line",{x1:pad.l,y1:Y(v),x2:W-pad.r,y2:Y(v),stroke:"#d3cec2","stroke-width":1});
  create("text",{x:X(v),y:H-pad.b+17,"font-size":10,fill:"#5f6058","text-anchor":"middle"},v.toFixed(0));
  create("text",{x:pad.l-10,y:Y(v)+4,"font-size":10,fill:"#5f6058","text-anchor":"end"},v.toFixed(0));
 }
 create("line",{x1:X(-span),y1:Y(-span),x2:X(span),y2:Y(span),stroke:"#8a837a","stroke-dasharray":"6 4","stroke-width":1.5});
 for(const r of subset){
  const circle=create("circle",{cx:X(r.forecast_margin),cy:Y(r.observed_margin),r:4.2,fill:r.gap>=0?"#315d82":"#9c453e",opacity:.7});
  const title=document.createElementNS(SVGNS,"title");title.textContent=r.id+": predicted "+signedMargin(r.forecast_margin)+"; observed "+signedMargin(r.observed_margin)+"; provisional difference "+r.gap.toFixed(1)+" pp";circle.append(title);
 }
 create("text",{x:W/2,y:H-7,"font-size":12,fill:"#343733","text-anchor":"middle"},"Frozen predicted D−R (pp)");
 create("text",{x:17,y:H/2,"font-size":12,fill:"#343733","text-anchor":"middle",transform:"rotate(-90 17 "+H/2+")"},"Observed D−R (pp)");
 cell.replaceChildren(svg,n("p",subset.length+" races plotted (complete comparable universe). Blue points show more Democratic votes than the model predicted, red more Republican. Dashed diagonal = agreement. Incomplete counts are not final forecast errors.","chart-key"));
}
function ledger(data){
 const list=[],cache=data.sources?.[0];
 list.push({name:"Stored national snapshot · "+(cache?.source||"unknown"),state:cache?.races?.some(r=>r.votes_total>0)?cache.races.filter(r=>r.votes_total>0).length+" races with published vote counts":"No stored votes yet",asOf:cache?.source_updated_at});
 for(const o of data.sourceChecks||[]){
  const health=o.health;
  const status=health
   ?(health.stale?"Provider reports STALE":health.live?"Provider reports LIVE":health.final?"All available precincts reported (NOT certified)":health.counting?"Counting; provider freshness not live":"No votes in this feed")
   :o.success?(o.published?"Returns published":"Reachable; no returns published"):"Unavailable from this browser";
  list.push({name:o.name,state:status+(health?.races!==null&&health?.races!==undefined?" · "+health.races+" source races":""),
    asOf:o.asOf});
 }
 $("sourceLedger").replaceChildren(...list.map(item=>{
  const row=n("div",null,"source-row");row.append(n("strong",item.name),n("span",item.state+(item.asOf?" · "+ageLabel(item.asOf).label:" · source time unavailable")));return row;
 }));
}
function header(data){
 const info=analyse(data.rows||[]),age=ageLabel(data.feed?.source_updated_at),badge=$("freshnessFlag");
 const label=!info.seen?"NO OBSERVED COUNTS":age.state==="unknown"?"COUNTS PRESENT · AGE UNKNOWN":"COUNTS · "+age.label.toUpperCase();
 badge.className="pill "+(info.seen?age.state:"unknown");badge.textContent=label;
 const alert=$("coverageAlert"),title=$("coverageAlertTitle"),message=$("coverageAlertText");
 const coverage=Math.round(100*info.seen/(info.tracked||470));
 if(info.seen===0){
   alert.className="coverage-alert stale";title.textContent="No national results have reached this dashboard.";
   message.textContent="That is a feed failure or coverage gap, not evidence that no votes have been counted. Use AP-backed newsroom results for national race calls.";
 }else if(age.state==="stale"||age.state==="unknown"){
   alert.className="coverage-alert stale";title.textContent="The stored count may be stale ("+coverage+"% of tracked races report votes).";
   message.textContent="Refreshing this page does not make old results current. Compare the source timestamp with independently published AP results.";
 }else if(info.seen<info.tracked){
   alert.className="coverage-alert";title.textContent="Partial national reporting: "+info.seen+" of "+info.tracked+" tracked races have votes.";
   message.textContent="civicAPI counts and calls may differ from AP/DDHQ coverage. The percentage measures races with votes, not ballots counted. Missing races are not zero-vote results.";
 }else{
   alert.className="coverage-alert ok";title.textContent="All tracked races have reported some votes.";
   message.textContent="Returns remain unofficial. One reported vote is not a completed count. civicAPI calls are independent of AP decisions.";
 }
 ledger(data);
}
function selection(data){
 const rows=data.rows||[],state=$("state").value,layer=$("mapLayer").value;
 const subset=state==="all"?rows:rows.filter(r=>r.state===state),a=analyse(subset);
 const info=state==="all"?null:stateInsight(rows,state,layer);
 $("selectedTitle").textContent=state==="all"?"United States":$("state").selectedOptions[0]?.textContent||state;
 $("selectTracked").textContent=num(a.tracked);$("selectReporting").textContent=num(a.seen);$("selectCalled").textContent=num(a.called);
 $("selectInterpretation").textContent=state==="all"
 ?a.statesWithCount+" of "+a.statesTracked+" tracked states have at least one reporting contest. This is geographic coverage, not turnout completeness, precinct coverage or national vote share."
 :a.seen+" of "+a.tracked+" races report votes; "+a.called+" have named-source calls. "+(!info?.counted?"No two-party return available for this map layer.":layer==="coverage"?"A race reporting any votes does not imply its ballots have finished counting.":info.margin!==null?"Two-party D−R "+signedMargin(info.margin)+" among the reporting "+layer+" races only. Not a statewide projection.":"No comparable D/R vote margin in this layer.");
}
function research(data){
 const a=analyse(data.rows||[]),ratio=a.tracked?100*a.seen/a.tracked:0,quality=$("countQuality");
 const bar=n("div",null,"progress"),fill=n("div",null,"progress-fill");fill.style.width=ratio+"%";bar.append(fill);
 const line=(label,value)=>{const row=n("div",null,"stat-row");row.append(n("span",label),n("strong",num(value)));return row};
 quality.replaceChildren(n("div",ratio.toFixed(1)+"%","big-value"),n("p",num(a.seen)+" / "+num(a.tracked)+" contests with any published vote. This is NOT the percentage of ballots counted."),bar,
  line("Comparable D/R race returns",a.comparable),line("Unknown reporting-unit coverage",a.unknownPrecinct),
  n("p","A national popular vote share or electoral swing cannot be inferred from incomplete and selectively covered districts."));
 const d=$("discrepancy"),study=swingStudy(data.rows||[]);
 d.replaceChildren(...(study.state==="insufficient"
  ?[n("div","WITHHELD","big-value"),n("p",study.n+" races meet the ≥95% reporting-units criterion (minimum five)."),n("p","Without sufficient near-complete returns, a headline model error would be misleading.")]
  :[n("div",(study.medianGap>=0?"+":"")+study.medianGap.toFixed(1)+" pp","big-value"),n("p","Median provisional observed-minus-predicted margin, "+study.n+" qualifying races."),n("p",study.note)]));
 chart(data.rows||[]);
}
let mapVersion=0;
async function map(data){
 const version=++mapVersion,layer=$("mapLayer").value,selected=$("state").value;
 await drawStateMap($("stateMap"),{rows:data.rows,layer,selected,onSelect:code=>{
  $("state").value=$("state").value===code?"all":code;
  $("state").dispatchEvent(new Event("input",{bubbles:true}));
 }});
 if(version===mapVersion){const legend=document.querySelector(".map-legend");if(legend)legend.hidden=layer!=="coverage";}
}
function details(row){
 const lens=$("raceLens"),out=$("raceLensContent"),items=[];
 const status=comparability(row);
 items.push(n("p",row.id+" · "+row.office.toUpperCase()+" · "+row.candidateD+" (D) / "+row.candidateR+" (R)"));
 items.push(n("p","Frozen model: "+signedMargin(row.forecast_margin)+" predicted margin, "+(row.dem_probability===null?"unknown":percent(100*row.dem_probability))+" Democratic probability."));
 items.push(n("p",row.votes===null?"No observed votes supplied.":"Observed "+num(row.votes)+" votes, D−R "+signedMargin(row.observed_margin)+". "+(row.called?"Called by "+row.called_by+".":"Uncalled; any leader is provisional.")));
 items.push(n("p",status.text));
 if(row.observed?.reporting_unit_pct!==null&&row.observed?.reporting_unit_pct!==undefined){
   items.push(n("p","Reporting metric: "+row.observed.reporting_unit_pct+"% of "+(row.observed.reporting_unit||"source-defined reporting units")+". Not a verified percentage of all ballots counted."));
 }
 const candidates=row.observed?.candidates||[];
 if(candidates.length){
  const table=n("table"),head=n("thead"),hr=n("tr");for(const label of ["Candidate","Party","Votes"])hr.append(n("th",label));head.append(hr);table.append(head);
  const body=n("tbody");
  for(const c of [...candidates].sort((a,b)=>(b.votes||0)-(a.votes||0))){const tr=n("tr");tr.append(n("td",c.name),n("td",c.party),n("td",num(c.votes)));body.append(tr)}
  table.append(body);items.push(table);
 }
 if(row.observed?.source_url?.startsWith("https://")){const p=n("p"),link=n("a","Open reported source");link.href=row.observed.source_url;link.rel="noopener noreferrer";link.target="_blank";p.append(link);items.push(p)}
 items.push(n("p","Method: counting can progress unevenly by county, vote method or race. Reporting units at 100% still do not constitute certification."));
 out.replaceChildren(...items);$("lensTitle").textContent=row.id+" · race detail";lens.hidden=false;
 lens.scrollIntoView({block:"nearest",behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"});
}
function update(){
 const data=current();if(!data?.rows)return;latest=data;header(data);selection(data);research(data);map(data);
}
function urlState(){
 const url=new URL(location.href);for(const [key,value]of Object.entries({state:$("state").value,layer:$("mapLayer").value,chamber:$("chamber").value})){
  if(value==="all"||(key==="layer"&&value==="coverage"))url.searchParams.delete(key);else url.searchParams.set(key,value);
 }
 $("shareView").href=url.toString();
}
function onFilter(){const data=current();if(data?.rows){selection(data);map(data)}urlState();}
function start(){
 const args=new URL(location.href).searchParams;
 if(["coverage","house","senate"].includes(args.get("layer")))$("mapLayer").value=args.get("layer");
 for(const id of ["mapLayer","state","chamber"])$(id).addEventListener("input",onFilter);
 $("shareView").addEventListener("click",async e=>{
  if(!navigator.clipboard?.writeText)return;e.preventDefault();
  try{await navigator.clipboard.writeText($("shareView").href);$("shareView").textContent="Link copied";setTimeout(()=>$("shareView").textContent="Copy a link to this view",1800)}
  catch{location.href=$("shareView").href}
 });
 document.addEventListener("click",e=>{const b=e.target.closest("button[data-race]");if(!b)return;const d=current(),r=d?.rows?.find(x=>x.id===b.dataset.race);if(r)details(r)});
 $("closeLens").addEventListener("click",()=>{$("raceLens").hidden=true;$("browseTitle").scrollIntoView({block:"nearest"})});
 window.addEventListener("ms:results-updated",update);window.addEventListener("ms:results-filtered",onFilter);
 urlState();if(current()?.rows)update();
}
start();
