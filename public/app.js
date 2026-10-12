let MODEL=null;
const $=(s,r=document)=>r.querySelector(s);
const $$=(s,r=document)=>[...r.querySelectorAll(s)];
const pct=v=>`${(100*v).toFixed(v>0.995||v<0.005?1:0)}%`;
const signed=v=>`${v>=0?'D +':'R +'}${Math.abs(v).toFixed(1)}`;

function setView(view){
  $$('[data-panel]').forEach(x=>x.classList.toggle('hidden',x.dataset.panel!==view));
  $$('#nav button').forEach(x=>x.classList.toggle('active',x.dataset.view===view));
  $('#nav').classList.remove('open'); $('#menuButton').setAttribute('aria-expanded','false');
  history.replaceState(null,'',`#${view}`); window.scrollTo({top:0,behavior:'smooth'});
  if(view==='history') loadHistory();
}
document.addEventListener('click',e=>{const t=e.target.closest('[data-view]');if(t){e.preventDefault();setView(t.dataset.view)}});
$('#menuButton').addEventListener('click',()=>{const open=$('#nav').classList.toggle('open');$('#menuButton').setAttribute('aria-expanded',String(open))});

function miniRace(r){
 const p=r.dem_probability; const lead=p>=.5?'D':'R'; const win=Math.max(p,1-p);
 return `<div class="race-mini"><div class="race-code">${r.race_code}</div><div class="race-names"><b>${r.dem_candidate||'—'} <span class="muted">vs</span> ${r.rep_candidate||'—'}</b><small>${r.rating} · model margin ${signed(r.forecast_margin_d_minus_r)}</small></div><div class="race-prob ${lead==='D'?'margin-pos':'margin-neg'}">${pct(win)}<small>${lead} WIN</small></div></div>`;
}
function raceRows(rows){
 const body=rows.map(r=>{const p=r.dem_probability;return `<div class="race-row" data-p="${p}" data-type="${r.race_type}"><div class="race-code">${r.race_code}</div><div class="candidate"><span class="party-label dem">D</span>${r.dem_candidate||'—'}</div><div class="candidate"><span class="party-label rep">R</span>${r.rep_candidate||'—'}</div><div class="probcell"><strong class="${p>=.5?'margin-pos':'margin-neg'}">${pct(Math.max(p,1-p))}</strong><div class="rating">${p>=.5?'D':'R'} win</div></div><div class="${r.forecast_margin_d_minus_r>=0?'margin-pos':'margin-neg'}">${signed(r.forecast_margin_d_minus_r)}</div><div class="rating">${r.rating}</div></div>`}).join('');
 return `<div class="race-row header"><div>RACE</div><div>DEMOCRAT / ALIGNED</div><div>REPUBLICAN</div><div>WIN PROB.</div><div>MARGIN</div><div>RATING</div></div>${body}`;
}
function chamberStrip(ch){return `<div class="strip-stat"><strong>${pct(ch.dem_control_probability)}</strong><span>Dem control</span></div><div class="strip-stat"><strong>${ch.expected_dem_seats}</strong><span>Expected Dem seats</span></div><div class="strip-stat"><strong>${ch.dem_seats_80_interval[0]}–${ch.dem_seats_80_interval[1]}</strong><span>80% Dem seat range</span></div><div class="strip-stat"><strong>${ch.simulations.toLocaleString()}</strong><span>Simulations</span></div>`}
function fillSummary(m){
 if(m.schema_version!=='0.2.0') throw new Error(`Waiting for v0.2 forecast; found ${m.schema_version}`);
 const h=m.summary.house,s=m.summary.senate;
 $('#daysToElection').textContent=m.days_to_election;
 $('#houseDemProb').textContent=pct(h.dem_control_probability); $('#houseRepProb').textContent=pct(h.rep_control_probability);
 $('#houseDemSeats').textContent=h.expected_dem_seats; $('#houseRange').textContent=`${h.dem_seats_80_interval[0]}–${h.dem_seats_80_interval[1]}`; $('#houseSeatBar').style.width=`${h.expected_dem_seats/435*100}%`;
 $('#senateDemProb').textContent=pct(s.dem_control_probability); $('#senateRepProb').textContent=pct(s.rep_control_probability);
 $('#senateDemSeats').textContent=s.expected_dem_seats; $('#senateRange').textContent=`${s.dem_seats_80_interval[0]}–${s.dem_seats_80_interval[1]}`; $('#senateSeatBar').style.width=`${s.expected_dem_seats}%`;
 $('#gcb').textContent=signed(m.national_environment.generic_ballot_d_minus_r); $('#pollGcb').textContent=signed(m.national_environment.generic_ballot_d_minus_r);
 $('#coverage').textContent=m.races.length.toString(); $('#simulationCount').textContent=h.simulations.toLocaleString();
 $('#generatedAt').textContent=new Date(m.generated_at).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short',timeZone:'UTC'})+' UTC';
 $('#pollCountText').textContent=`${m.national_environment.polls_in_35_day_window} polls in the current 35-day aggregation window.`;
 $('#tippingList').innerHTML=m.tipping_point_house.slice(0,10).map(miniRace).join(''); $('#senateBattles').innerHTML=m.senate_battlegrounds.slice(0,10).map(miniRace).join('');
 $('#houseStrip').innerHTML=chamberStrip(h); $('#senateStrip').innerHTML=chamberStrip(s);
 const house=m.races.filter(r=>r.race_type==='house').sort((a,b)=>Math.abs(a.dem_probability-.5)-Math.abs(b.dem_probability-.5));
 const senate=m.races.filter(r=>r.race_type==='senate').sort((a,b)=>Math.abs(a.dem_probability-.5)-Math.abs(b.dem_probability-.5));
 $('#houseTable').innerHTML=raceRows(house); $('#senateTable').innerHTML=raceRows(senate); $('#allTable').innerHTML=raceRows([...house,...senate].sort((a,b)=>Math.abs(a.dem_probability-.5)-Math.abs(b.dem_probability-.5)));
 $('#pollList').innerHTML=m.national_environment.recent_polls.map(p=>`<div class="poll-row"><div><b>${p.pollster}</b><br><small>${p.end_date}${p.sponsor_lean?` · sponsor lean ${p.sponsor_lean}`:''}</small></div><div class="poll-n"><small>n=${p.n||'—'}</small></div><div><small>D ${p.dem} / R ${p.rep}</small></div><strong class="${p.margin>=0?'margin-pos':'margin-neg'}">${signed(p.margin)}</strong></div>`).join('');
 $('#methodGrid').innerHTML=Object.entries(m.methodology).map(([k,v])=>`<article class="panel method-card"><span class="eyebrow">${k.replaceAll('_',' ')}</span><h2>${k.replaceAll('_',' ')}</h2><p>${v}</p></article>`).join('');
 $('#limitations').innerHTML=m.limitations.map(x=>`<li>${x}</li>`).join('');
 $('#provenanceList').innerHTML=Object.entries(m.provenance).map(([k,v])=>`<dt>${k.replaceAll('_',' ')}</dt><dd>${Array.isArray(v)?v.join(', '):v}</dd>`).join('');
 const d=m.change_since_previous_run;
 if(d){const bits=[];bits.push(`House expected Democratic seats ${d.house_expected_dem>0?'rose':'fell'} ${Math.abs(d.house_expected_dem).toFixed(1)}`);bits.push(`Senate ${d.senate_expected_dem>0?'rose':'fell'} ${Math.abs(d.senate_expected_dem).toFixed(1)}`);bits.push(`generic ballot moved ${d.generic_ballot_margin>=0?'D':'R'} ${Math.abs(d.generic_ballot_margin).toFixed(1)}`);$('#briefHeadline').textContent='Model movement since the previous run';$('#briefText').textContent=bits.join(' · ')+'.';$('#briefingBody').innerHTML=`<h2>${$('#briefHeadline').textContent}</h2><p>${$('#briefText').textContent}</p>`}else{$('#briefHeadline').textContent='Production baseline';$('#briefText').textContent=`House: ${pct(h.dem_control_probability)} Democratic control. Senate: ${pct(s.dem_control_probability)} Democratic control. National generic ballot: ${signed(m.national_environment.generic_ballot_d_minus_r)}.`;$('#briefingBody').innerHTML=`<h2>Production baseline</h2><p>${$('#briefText').textContent}</p>`}
 $('#liveStatus').classList.add('live'); $('#liveStatus span:last-child').textContent='Forecast live';
}
function setupFilter(inputId,selectId,tableId){
 const run=()=>{const q=$(`#${inputId}`).value.trim().toLowerCase(),mode=$(`#${selectId}`).value;$$(`#${tableId} .race-row:not(.header)`).forEach(row=>{const p=Number(row.dataset.p),type=row.dataset.type;let ok=!q||row.textContent.toLowerCase().includes(q);if(mode==='competitive')ok=ok&&p>=.3&&p<=.7;if(mode==='tossup')ok=ok&&p>=.45&&p<=.55;if(mode==='dem')ok=ok&&p>.5;if(mode==='rep')ok=ok&&p<.5;if(mode==='house'||mode==='senate')ok=ok&&type===mode;row.classList.toggle('hidden',!ok)})};
 $(`#${inputId}`).addEventListener('input',run);$(`#${selectId}`).addEventListener('change',run);
}
setupFilter('houseSearch','houseFilter','houseTable');setupFilter('senateSearch','senateFilter','senateTable');setupFilter('allSearch','allFilter','allTable');
async function loadHistory(){
 const box=$('#historyList'); if(box.dataset.loaded)return; box.dataset.loaded='1';
 try{const idx=await fetch('./data/history/index.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));const files=idx.snapshots.slice(0,12);const snaps=await Promise.all(files.map(f=>fetch(`./data/history/${f}`,{cache:'no-store'}).then(r=>r.json()).catch(()=>null)));box.innerHTML=snaps.filter(s=>s?.summary).map(s=>`<div class="history-item"><div><strong>${new Date(s.generated_at).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'})}</strong><br><small>${s.model}</small></div><div><small>House D control</small><br><strong>${pct(s.summary.house.dem_control_probability)}</strong></div><div><small>Senate D control</small><br><strong>${pct(s.summary.senate.dem_control_probability)}</strong></div><div><small>Generic ballot</small><br><strong>${signed(s.national_environment.generic_ballot_d_minus_r)}</strong></div></div>`).join('')||'<p class="muted">No v0.2 snapshots yet.</p>'}catch(e){box.innerHTML='<p class="muted">History index will appear after the first forecast refresh.</p>'}
}
async function boot(){
 try{const r=await fetch('./data/forecast.json',{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);MODEL=await r.json();fillSummary(MODEL)}catch(e){console.error(e);$('#liveStatus span:last-child').textContent='Forecast refresh pending';$('#briefHeadline').textContent='v0.2 production refresh running';$('#briefText').textContent='The all-race model is refreshing in GitHub Actions. This page will populate automatically when the v0.2 snapshot lands.'}
 const v=location.hash.slice(1); if(v&&$(`[data-panel="${v}"]`))setView(v);
}
boot();
