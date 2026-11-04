import {FROZEN_FORECAST,assemble,totals,filterRows,signed,exportCsv} from "./desk-core.mjs";
const $=id=>document.getElementById(id);
const states={AL:"Alabama",AK:"Alaska",AZ:"Arizona",AR:"Arkansas",CA:"California",CO:"Colorado",CT:"Connecticut",DE:"Delaware",DC:"District of Columbia",FL:"Florida",GA:"Georgia",HI:"Hawaii",ID:"Idaho",IL:"Illinois",IN:"Indiana",IA:"Iowa",KS:"Kansas",KY:"Kentucky",LA:"Louisiana",ME:"Maine",MD:"Maryland",MA:"Massachusetts",MI:"Michigan",MN:"Minnesota",MS:"Mississippi",MO:"Missouri",MT:"Montana",NE:"Nebraska",NV:"Nevada",NH:"New Hampshire",NJ:"New Jersey",NM:"New Mexico",NY:"New York",NC:"North Carolina",ND:"North Dakota",OH:"Ohio",OK:"Oklahoma",OR:"Oregon",PA:"Pennsylvania",RI:"Rhode Island",SC:"South Carolina",SD:"South Dakota",TN:"Tennessee",TX:"Texas",UT:"Utah",VT:"Vermont",VA:"Virginia",WA:"Washington",WV:"West Virginia",WI:"Wisconsin",WY:"Wyoming"};
let rows=[],feed=null,forecast=null,loaded=false;
const ui={chamber:"all",state:"all",query:"",sort:"status",reported:false};
const fmt=n=>n===null?"—":new Intl.NumberFormat("en-US").format(n);
const date=v=>{if(!v)return "Not published";const d=new Date(v);return Number.isFinite(d.getTime())?d.toLocaleString("en-AU",{timeZone:"Australia/Melbourne",day:"numeric",month:"short",hour:"2-digit",minute:"2-digit",hour12:false,timeZoneName:"short"}):String(v)};
async function json(path) {const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);try{const r=await fetch(path,{cache:"no-store",signal:controller.signal});if(!r.ok)throw new Error("HTTP "+r.status+" from "+path);return await r.json()}finally{clearTimeout(timer)}}
function node(tag,text,className){const el=document.createElement(tag);el.textContent=text??"";if(className)el.className=className;return el}
function cell(tr,value,kind){const td=node("td",value,kind||"");tr.append(td);return td}
function row(r){
  const tr=document.createElement("tr"),race=cell(tr,""),a=node("a",r.id,"race-id");
  a.href="/?view=race&race="+encodeURIComponent(r.id);race.append(a);
  const cand=node("small",[r.candidateD?("D: "+r.candidateD):null,r.candidateR?("R: "+r.candidateR):null].filter(Boolean).join(" · "));
  race.append(cand);
  const o=r.observed;
  const status=cell(tr,"");
  if(r.called){
    status.append(node("span","Called: "+(r.winner?.name||r.winner?.party||"winner"),"status-text"));
    status.append(node("small","By "+r.called_by));
  }else if(r.votes!==null){
    status.append(node("span",(r.lead?.name||r.lead?.party||"Count reported")+" leads","status-text"));
    status.append(node("small","Uncalled · counting lead only"));
  }else{status.append(node("span","No votes reported","unavailable"))}
  if(o?.source_url?.startsWith("https://")){const link=node("a","Source","");link.href=o.source_url;link.target="_blank";link.rel="noopener noreferrer";const sourceWrap=node("small","");sourceWrap.append(link);status.append(sourceWrap)}
  const inspect=node("button","Inspect race","inspect-race");inspect.type="button";inspect.dataset.race=r.id;const inspectWrap=node("small","");inspectWrap.append(inspect);status.append(inspectWrap);
  cell(tr,fmt(r.votes),"numeric");
  cell(tr,signed(r.observed_margin),"numeric");
  cell(tr,signed(r.forecast_margin),"numeric");
  cell(tr,r.gap===null?"—":(r.gap>=0?"+":"")+r.gap.toFixed(1)+" pp*","numeric");
  return tr;
}
function controls(){for(const id of ["chamber","state","sort"])ui[id]=$(id).value;ui.query=$("query").value;ui.reported=$("reported").checked}
function redraw() {
  if(!loaded)return;controls();const selected=filterRows(rows,ui);
  $("rowCount").textContent=selected.length+" of "+rows.length+" races";
  const frag=document.createDocumentFragment();
  if(!selected.length){const tr=node("tr");const td=cell(tr,"No races meet these filters.");td.colSpan=6;frag.append(tr)}
  else for(const r of selected)frag.append(row(r));
  $("raceRows").replaceChildren(frag);
  for(const button of $("stateTiles").querySelectorAll("button"))button.classList.toggle("active",button.dataset.state===ui.state);
  window.dispatchEvent(new Event("ms:results-filtered"));
}
function setState(state){$("state").value=state;redraw()}
function makeTiles() {
  const stateRows=new Map();
  for(const r of rows){const entry=stateRows.get(r.state)||{total:0,reported:0};entry.total++;if(r.votes!==null)entry.reported++;stateRows.set(r.state,entry)}
  const frag=document.createDocumentFragment();
  for(const [code,name] of Object.entries(states)){
    const summary=stateRows.get(code)||{total:0,reported:0};
    if(!summary.total)continue;
    const b=node("button",code,(summary.reported?"has-count ":"")+"");
    b.type="button";b.dataset.state=code;b.title=name+": "+summary.reported+"/"+summary.total+" races with counts";
    b.setAttribute("aria-label",code+" — "+b.title);b.addEventListener("click",()=>setState(ui.state===code?"all":code));frag.append(b);
  }
  $("stateTiles").replaceChildren(frag);
  $("coverage").textContent="Dot = at least one contest with reported votes";
}
function summary(){
  const t=totals(rows);
  $("mReporting").textContent=t.reporting+" / "+t.universe;
  $("mUniverse").textContent="House "+t.house.reporting+" / 435 · Senate "+t.senate.reporting+" / "+rows.filter(x=>x.office==="senate").length;
  $("mHouse").textContent=t.house.calledD+" D · "+t.house.calledR+" R";
  $("mSenate").textContent=t.senate.calledD+" D · "+t.senate.calledR+" R";
  $("mLeads").textContent=t.leadsD+" D · "+t.leadsR+" R";
  const seen=t.reporting>0;
  $("feedStatus").textContent=seen
    ?"Vote counts available for "+t.reporting+" contests; all uncalled leads remain provisional."
    :feed?.state==="source_unavailable"?"Results feed unavailable; forecasts shown for orientation only."
    :"Awaiting verified vote counts. Showing the frozen model as a geographic index.";
  $("feedClock").textContent="Stored publisher: "+(feed?.source||"unavailable")+" · Published at: "+date(feed?.source_updated_at)+" · Fetched at: "+date(feed?.fetched_at)+" · Frozen model: 3 Nov 2026 19:29 UTC · Race calls: civicAPI, not AP";
}
async function refresh(){
  if($("refresh").disabled)return;
  $("refresh").disabled=true;
  try {
    // The checked, same-origin snapshot is the reproducible fallback.
    const cached=await json("/data/observed-results.json?ts="+Date.now());
    feed=cached;
    // Render reproducible same-origin data immediately; cross-origin feeds may be slow.
    rows=assemble(forecast,feed);loaded=true;summary();makeTiles();redraw();
    window.__MS_RESULTS__={rows,feed,sources:[cached],sourceChecks:[]};window.dispatchEvent(new Event("ms:results-updated"));
    // Opportunistic direct refresh; if the third-party site blocks CORS or fails,
    // we do not replace the last checked snapshot with an error or empty result.
    const {normaliseClient}=await import("./live-adapter.mjs");
    const {normaliseOpenAmerica,combineFeeds}=await import("./openamerica-adapter.mjs");
    const requests=await Promise.allSettled([
      json("https://thepeoplestally.com/data/results.json"),
      json("https://openamerica.io/elections/results.json?year=2026&office=House"),
      json("https://openamerica.io/elections/results.json?year=2026&office=Senate")
    ]);
    const sources=[cached];
    if(requests[0].status==="fulfilled")try{sources.push(normaliseClient(requests[0].value))}catch(_){}
    for(const index of [1,2])if(requests[index].status==="fulfilled")
      try{sources.push(normaliseOpenAmerica(requests[index].value))}catch(_){}
    feed=combineFeeds(sources);
    rows=assemble(forecast,feed);loaded=true;summary();makeTiles();redraw();
    const sourceNames=["The People's Tally direct","Open America / House","Open America / Senate"];
    const sourceChecks=requests.map((r,i)=>({name:sourceNames[i],success:r.status==="fulfilled",
      published:r.status==="fulfilled"&&(i===0?Object.keys(r.value?.races||{}).length:Object.keys(r.value?.races||{}).length)>0,
      asOf:r.status==="fulfilled"?(r.value.generated_at||r.value.as_of||null):null,
      health:r.status==="fulfilled"&&i>0?{live:r.value.live===true,stale:r.value.stale===true,counting:r.value.counting===true,final:r.value.final===true,
       races:typeof r.value.counts?.races==="number"?r.value.counts.races:null}:null,
      note:r.status==="fulfilled"?"Responded":"Not reachable from this browser"}));
    window.__MS_RESULTS__={rows,feed,sources,sourceChecks};
    window.dispatchEvent(new Event("ms:results-updated"));
  }catch(e){$("feedStatus").textContent="Could not load results snapshot: "+e.message;$("feedClock").textContent="The stored forecasts remain available in the archive."}
  finally{$("refresh").disabled=false}
}
async function init(){
  const params=new URLSearchParams(location.search);
  if(["all","house","senate"].includes(params.get("chamber")))ui.chamber=params.get("chamber");
  if(Object.hasOwn(states,params.get("state")))ui.state=params.get("state");
  $("chamber").value=ui.chamber;
  $("state").append(...Object.entries(states).map(([code,name])=>{const o=document.createElement("option");o.value=code;o.textContent=name+" ("+code+")";return o}));
  $("state").value=ui.state;
  for(const id of ["chamber","state","query","sort","reported"])$(id).addEventListener("input",redraw);
  $("filters").addEventListener("submit",e=>e.preventDefault());
  $("export").addEventListener("click",()=>{
    const csv=exportCsv(filterRows(rows,ui)),blob=new Blob([csv],{type:"text/csv;charset=utf-8"});
    const link=document.createElement("a"),url=URL.createObjectURL(blob);link.href=url;link.download="midterm-signals-observed-2026.csv";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $("refresh").addEventListener("click",refresh);
  try {
    forecast=await json(FROZEN_FORECAST);
    if(!Array.isArray(forecast.races)||forecast.races.length<470)throw new Error("Race index incomplete");
    await refresh();
    // One-minute user-facing refresh; GitHub's archived snapshot remains available.
    setInterval(()=>{if(document.visibilityState==="visible")refresh()},60000);
  }catch(e){$("feedStatus").textContent="Frozen model unavailable: "+e.message;$("feedClock").textContent="No election results will be compared with an unfrozen forecast."}
}
init();
