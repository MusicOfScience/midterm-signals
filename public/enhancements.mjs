const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const pct=v=>Number.isFinite(v)?`${Math.round(v*100)}%`:'—';
const signed=v=>Number.isFinite(v)?`${v>=0?'D +':'R +'}${Math.abs(v).toFixed(1)}`:'—';
let modelPromise=null,historyPromise=null;
const model=()=>modelPromise??=fetch('/data/forecast.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(`forecast ${r.status}`);return r.json()});
const historySnapshots=()=>historyPromise??=(async()=>{const i=await fetch('/data/history/index.json',{cache:'no-store'}).then(r=>r.ok?r.json():{snapshots:[]});const names=(i.snapshots||[]).slice(0,36);return Promise.all(names.map(async file=>{try{return await fetch(`/data/history/${file}`,{cache:'no-store'}).then(r=>r.ok?r.json():null)}catch{return null}})).then(xs=>xs.filter(Boolean))})();

function mapValue(r,layer){
  const p=r.dem_probability??.5,side=p>=.5?'D':'R',winner=Math.max(p,1-p),delta=r.change?.dem_probability??0;
  if(layer==='margin')return {headline:signed(r.forecast_margin_d_minus_r),detail:`${pct(winner)} ${side} win`};
  if(layer==='movement')return {headline:Math.abs(delta)<.00005?'No change':`${delta>0?'D':'R'} ${Math.abs(delta*100).toFixed(1)} pp`,detail:`now ${pct(winner)} ${side}`};
  if(layer==='rating')return {headline:r.rating||'Unrated',detail:`${pct(winner)} ${side} win`};
  return {headline:`${pct(winner)} ${side}`,detail:r.rating||'Unrated'};
}
async function enhanceMap(){
  const grid=document.querySelector('#mapGrid'),layerSel=document.querySelector('#mapLayer'),chamberSel=document.querySelector('#mapChamber');
  if(!grid||!layerSel||!chamberSel||grid.dataset.v1Enhanced)return;
  grid.dataset.v1Enhanced='true';
  const data=await model();
  const render=()=>{
    let rows=(data.races||[]).filter(r=>r.race_type===chamberSel.value).sort((a,b)=>String(a.state).localeCompare(String(b.state))||String(a.district||'').localeCompare(String(b.district||''),undefined,{numeric:true}));
    if(grid.dataset.competitive==='true')rows=rows.filter(r=>(r.dem_probability??.5)>=.2&&(r.dem_probability??.5)<=.8);
    const layer=layerSel.value;
    grid.innerHTML=rows.map(r=>{const p=r.dem_probability??.5,side=p>=.5?'D':'R',cls=p>=.45&&p<=.55?'toss':side==='D'?'d-edge':'r-edge',v=mapValue(r,layer);return `<button class="race-tile ${cls}" type="button" data-enhanced-race="${esc(r.race_code)}" aria-label="${esc(r.race_code)}, ${esc(v.headline)}, ${esc(v.detail)}"><span class="symbol">${esc(r.race_code)} · ${esc(v.headline)}</span><small>${esc(v.detail)}</small></button>`}).join('');
  };
  layerSel.addEventListener('change',()=>setTimeout(render,0));
  grid.addEventListener('click',e=>{const b=e.target.closest('[data-enhanced-race]');if(b)location.href=`/?race=${encodeURIComponent(b.dataset.enhancedRace)}`});
  const comp=document.querySelector('#mapCompetitive');
  comp?.addEventListener('click',()=>{grid.dataset.competitive=grid.dataset.competitive==='true'?'false':'true';comp.textContent=grid.dataset.competitive==='true'?'Show all races':'Competitive only';setTimeout(render,0)});
  render();
}

function enhanceBuilder(){
  const root=document.querySelector('#assignments');
  if(!root||root.dataset.v1Restored)return;
  root.dataset.v1Restored='true';
  const encoded=new URLSearchParams(location.search).get('map');
  if(!encoded)return;
  try{
    const assignments=JSON.parse(atob(encoded));
    queueMicrotask(()=>{for(const [code,choice] of Object.entries(assignments)){const tile=[...root.querySelectorAll('.assignment')].find(x=>x.dataset.code===code);tile?.querySelector(`button[data-choice="${choice}"]`)?.click()}});
  }catch(err){console.warn('Invalid shared election map',err)}
}

async function enhanceHistory(){
  const list=document.querySelector('.history-list');
  if(!list||list.dataset.v1Enhanced)return;
  list.dataset.v1Enhanced='true';
  list.addEventListener('click',async e=>{
    const b=e.target.closest('[data-history-file]'); if(!b)return;
    const file=b.dataset.historyFile; if(!file)return;
    b.setAttribute('aria-busy','true');
    try{
      const snap=await fetch(`/data/history/${encodeURIComponent(file)}`,{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(r.status);return r.json()});
      let detail=document.querySelector('#snapshotDetail');
      if(!detail){detail=document.createElement('section');detail.id='snapshotDetail';detail.className='section panel panel-pad';list.closest('.panel')?.after(detail)}
      const h=snap.summary?.house||{},s=snap.summary?.senate||{},g=snap.national_environment?.generic_ballot_d_minus_r;
      const close=(snap.races||[]).slice().sort((a,b)=>Math.abs((a.dem_probability??.5)-.5)-Math.abs((b.dem_probability??.5)-.5)).slice(0,6);
      detail.innerHTML=`<div class="eyebrow">SELECTED SNAPSHOT</div><h2>${esc(new Date(snap.generated_at).toLocaleString())}</h2><div class="facts-grid"><div class="fact"><b>${pct(h.dem_control_probability)}</b><span>House D control</span></div><div class="fact"><b>${Number.isFinite(h.expected_dem_seats)?h.expected_dem_seats.toFixed(1):'—'}</b><span>expected D House seats</span></div><div class="fact"><b>${pct(s.dem_control_probability)}</b><span>Senate D control</span></div><div class="fact"><b>${Number.isFinite(g)?signed(g):'—'}</b><span>generic ballot D−R</span></div></div><h3>Closest races then</h3><div class="race-grid">${close.map(r=>`<button class="race-tile ${r.dem_probability>=.5?'d-edge':'r-edge'}" type="button" data-enhanced-race="${esc(r.race_code)}"><span class="symbol">${esc(r.race_code)}</span><small>${pct(Math.max(r.dem_probability,1-r.dem_probability))} ${r.dem_probability>=.5?'D':'R'}</small></button>`).join('')}</div><p class="data-note">Immutable archived snapshot. This view does not recompute the past with today’s data.</p>`;
      detail.querySelectorAll('[data-enhanced-race]').forEach(x=>x.addEventListener('click',()=>location.href=`/?race=${encodeURIComponent(x.dataset.enhancedRace)}`));
      detail.scrollIntoView({block:'start'});
    }catch(err){console.error(err)}finally{b.removeAttribute('aria-busy')}
  });
}

async function enhanceRaceHistory(){
  const panels=[...document.querySelectorAll('.section.panel')];
  const panel=panels.find(x=>x.querySelector('.eyebrow')?.textContent.trim()==='PROBABILITY HISTORY');
  if(!panel||panel.dataset.v1Enhanced)return;
  panel.dataset.v1Enhanced='true';
  const code=new URLSearchParams(location.search).get('race')||location.pathname.split('/').filter(Boolean)[1];
  if(!code)return;
  try{
    const snaps=await historySnapshots();
    const points=snaps.map(s=>{const r=(s.races||[]).find(r=>String(r.race_code).toLowerCase()===String(code).toLowerCase());return r?{generated_at:s.generated_at,p:r.dem_probability}:null}).filter(Boolean).reverse();
    if(points.length<2)return;
    const body=panel.querySelector('.empty-state,.timeline-list');
    if(body)body.outerHTML=`<div class="timeline-list">${points.map(x=>`<div class="timeline"><small>${esc(new Date(x.generated_at).toLocaleDateString())}</small><div class="track"><span style="width:${Math.max(0,Math.min(100,x.p*100))}%"></span></div><strong>${pct(x.p)}</strong></div>`).join('')}</div>`;
  }catch(err){console.warn('Race history enhancement unavailable',err)}
}

let scheduled=false;
async function enhance(){if(scheduled)return;scheduled=true;requestAnimationFrame(async()=>{scheduled=false;try{await Promise.allSettled([enhanceMap(),enhanceHistory(),enhanceRaceHistory()]);enhanceBuilder()}catch(err){console.warn('v1 enhancement',err)}})}
new MutationObserver(enhance).observe(document.body,{childList:true,subtree:true});
enhance();
