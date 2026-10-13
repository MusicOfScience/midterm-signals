const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n = (value,digits=2) => value == null ? '—' : Number(value).toFixed(digits);
const pct = (value,digits=1) => value == null ? '—' : `${(Number(value)*100).toFixed(digits)}%`;
let payload = null;

const diffLabels={within_5pp:'≤5 pp prior',five_to_10pp:'>5–10 pp prior',ten_to_20pp:'>10–20 pp prior',over_20pp:'>20 pp prior'};

function selection(){
  const scored=(payload?.cycles||[]).filter(c=>c.state==='scored');
  const year=Number($('diagCycle')?.value || scored.at(-1)?.cycle);
  const days=Number($('diagCheckpoint')?.value || 1);
  const cycle=scored.find(c=>Number(c.cycle)===year) || scored.at(-1);
  const checkpoint=(cycle?.checkpoints||[]).find(c=>Number(c.days_to_election)===days) || (cycle?.checkpoints||[]).at(-1);
  return {cycle,checkpoint};
}

function metricCells(row){
  if(!row || row.state!=='scored') return `<td>${row?.n||0}</td><td colspan="5">Unavailable</td>`;
  return `<td>${row.n}</td><td>${n(row.raw_poll?.mae_pp)}</td><td>${n(row.prior?.mae_pp)}</td><td>${n(row.full_model?.mae_pp)}</td><td>${pct(row.one_poll_share)}</td><td>${pct(row.one_pollster_share)}</td>`;
}

function difficultyRows(rows){
  return (rows||[]).map(r=>`<tr><th scope="row">${esc(diffLabels[r.band]||r.band)}</th>${metricCells(r)}</tr>`).join('');
}

function interactionRows(rows){
  return (rows||[]).map(r=>{
    const label=`${r.prior_competitiveness==='within_10pp'?'Prior ≤10 pp':'Prior >10 pp'} · ${r.sparsity==='sparse'?'sparse':'2+ sources/polls'}`;
    return `<tr><th scope="row">${esc(label)}</th>${metricCells(r)}</tr>`;
  }).join('');
}

function regionRows(rows){
  return (rows||[]).map(r=>`<tr><th scope="row">${esc(r.region)}</th>${metricCells(r)}<td>${r.competitive_prior_n ?? 0}</td></tr>`).join('');
}

function render(){
  const panel=$('sparsityInteractionPanel');
  if(!panel) return;
  const {cycle,checkpoint}=selection();
  const diag=checkpoint?.score?.sparsity_interaction;
  const house=diag?.house_only;
  if(!diag || diag.state!=='scored' || !house || house.state!=='scored'){
    panel.innerHTML='<p class="muted">Polling sparsity × race-difficulty diagnostic unavailable for this checkpoint.</p>';
    return;
  }
  const headers='<th>Cell</th><th>n</th><th>Raw poll MAE</th><th>Prior MAE</th><th>Full model MAE</th><th>1-poll share</th><th>1-pollster share</th>';
  panel.innerHTML=`<div class="warning-note"><strong>Difficulty is defined before race polls and before outcomes.</strong> The audit uses the absolute structural+generic prior margin. A sparse/high-error cell is descriptive evidence, not proof that another poll would have caused a better forecast.</div>
    <h3>Did thin polling land on the hard races?</h3>
    <p class="method-note">House-only for the clean cross-cycle comparison. Headline “competitive” means the frozen pre-poll prior was within 10 percentage points. Geography uses fixed Northeast / Midwest / South / West state assignments.</p>
    <h3>By pre-poll difficulty</h3>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr>${headers}</tr></thead><tbody>${difficultyRows(house.by_prior_difficulty)}</tbody></table></div>
    <h3>Poll count × prior competitiveness</h3>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr>${headers}</tr></thead><tbody>${interactionRows(house.poll_depth_x_prior_competitiveness)}</tbody></table></div>
    <h3>Pollster count × prior competitiveness</h3>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr>${headers}</tr></thead><tbody>${interactionRows(house.source_count_x_prior_competitiveness)}</tbody></table></div>
    <h3>Geography</h3>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr>${headers}<th>Prior ≤10 pp n</th></tr></thead><tbody>${regionRows(house.by_region)}</tbody></table></div>
    <p class="muted">${cycle?.cycle} · ${checkpoint?.days_to_election}d · House n=${house.n}. Difficulty/sparsity/geography frozen pre-outcome; evaluation only; model effect NONE.</p>`;
}

fetch('/data/model-lab.json',{cache:'no-store'})
  .then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()})
  .then(data=>{
    payload=data;
    render();
    for(const id of ['diagCycle','diagCheckpoint']) $(id)?.addEventListener('change',render);
  })
  .catch(err=>{
    if($('sparsityInteractionPanel')) $('sparsityInteractionPanel').innerHTML=`<p>Sparsity interaction diagnostic unavailable: ${esc(err.message)}</p>`;
  });
