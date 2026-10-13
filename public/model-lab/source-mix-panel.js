const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n = (value,digits=2) => value == null ? '—' : Number(value).toFixed(digits);
const signedPP = (value,digits=2) => value == null ? '—' : `${Number(value)>=0?'+':''}${Number(value).toFixed(digits)} pp`;
const pct = (value,digits=1) => value == null ? '—' : `${(Number(value)*100).toFixed(digits)}%`;
let payload = null;

const labels = {
  one_poll:'1 poll', two_polls:'2 polls', three_four_polls:'3–4 polls', five_plus_polls:'5+ polls',
  one_pollster:'1 pollster', two_pollsters:'2 pollsters', three_plus_pollsters:'3+ pollsters',
  single_source:'Single source', concentrated_multi:'Multi-source, ≥⅔ top share', diversified_multi:'Multi-source, <⅔ top share',
  no_partisan_labeled:'No D/R-labelled source', mixed_partisan_labeled:'Mixed labelled / unlabelled', all_partisan_labeled:'All weight D/R-labelled'
};

function selection(){
  const scored=(payload?.cycles||[]).filter(c=>c.state==='scored');
  const year=Number($('diagCycle')?.value || scored.at(-1)?.cycle);
  const days=Number($('diagCheckpoint')?.value || 1);
  const cycle=scored.find(c=>Number(c.cycle)===year) || scored.at(-1);
  const checkpoint=(cycle?.checkpoints||[]).find(c=>Number(c.days_to_election)===days) || (cycle?.checkpoints||[]).at(-1);
  return {cycle,checkpoint};
}

function bandRows(rows){
  return (rows||[]).map(r=>{
    if(r.state!=='scored') return `<tr><th scope="row">${esc(labels[r.band]||r.band)}</th><td>${r.n||0}</td><td colspan="6">Unavailable</td></tr>`;
    const raw=r.raw_poll||{};
    return `<tr><th scope="row">${esc(labels[r.band]||r.band)}</th><td>${r.n}</td><td>${n(raw.mae_pp)}</td><td>${signedPP(raw.mean_error_d_minus_r_pp)}</td><td>${pct(raw.winner_call_accuracy)}</td><td>${n(r.mean_poll_count,1)}</td><td>${n(r.mean_unique_pollsters,1)}</td><td>${pct(r.mean_top_source_weight_share)}</td></tr>`;
  }).join('');
}

function table(title, rows, note=''){
  return `<h3>${esc(title)}</h3>${note?`<p class="method-note">${note}</p>`:''}<div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Band</th><th>n</th><th>Raw poll MAE</th><th>Bias D−R</th><th>Winner call</th><th>Mean polls</th><th>Mean pollsters</th><th>Mean top-source share</th></tr></thead><tbody>${bandRows(rows)}</tbody></table></div>`;
}

function pollsterRows(block){
  return (block?.pollsters?.reported_pollsters||[]).slice(0,20).map(r=>{
    const e=r.source_margin_error||{};
    return `<tr><td>${esc(r.pollster)}</td><td>${r.n_race_sources}</td><td>${n(e.mae_pp)}</td><td>${signedPP(e.mean_error_d_minus_r_pp)}</td><td>${pct(e.winner_call_accuracy)}</td><td>${pct(r.mean_model_weight_share)}</td><td>${n(r.mean_rating,2)}</td><td>${pct(r.mean_partisan_labeled_weight_share)}</td></tr>`;
  }).join('');
}

function render(){
  const panel=$('sourceMixPanel');
  if(!panel) return;
  const {cycle,checkpoint}=selection();
  const diag=checkpoint?.score?.source_mix;
  const house=diag?.house_only;
  if(!diag || diag.state!=='scored' || !house || house.state!=='scored'){
    panel.innerHTML='<p class="muted">Pollster/source-mix decomposition unavailable for this checkpoint.</p>';
    return;
  }
  const pollsters=pollsterRows(house);
  const pmeta=house.pollsters||{};
  panel.innerHTML=`<div class="warning-note"><strong>Source mix is observational, not a pollster league table.</strong> Races attract different amounts and kinds of polling. Bands are assigned from the exact polling stream before results are joined, and pollsters are ordered by sample size rather than by error.</div>
    <h3>Where is polling error concentrated?</h3>
    <p class="method-note">House-only for clean cross-cycle comparison. “Partisan-labelled” means the historical source explicitly marks a poll D or R. Blank or N is treated only as <strong>not labelled partisan</strong>, not asserted to be neutral. Polling mode is unavailable in this historical corpus.</p>
    ${table('By polling depth',house.by_poll_depth,'Fixed bands: 1, 2, 3–4 and 5+ eligible polls at the checkpoint.')}
    ${table('By number of pollsters',house.by_unique_pollsters,'Repeated polls from one house do not become multiple independent sources.')}
    ${table('By source concentration',house.by_source_concentration,'A multi-source race is “concentrated” when the largest pollster supplies at least two-thirds of exact model poll weight.')}
    ${table('By partisan-labelled weight',house.by_partisan_label_share,'This describes the admitted source stream; it does not infer sponsor effects causally.')}
    <h3>Pollster race-source diagnostics</h3>
    <p class="method-note">Each pollster contributes at most one weighted race-source observation per race/checkpoint. Only pollsters with at least ${pmeta.minimum_distinct_race_sources ?? 5} distinct race-sources are reported. Rows are ordered by sample size, then name, never by error.</p>
    ${pollsters?`<div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Pollster</th><th>Race-sources</th><th>MAE</th><th>Bias D−R</th><th>Winner call</th><th>Mean model weight</th><th>Mean rating</th><th>D/R-labelled share</th></tr></thead><tbody>${pollsters}</tbody></table></div>`:'<p class="muted">No pollster clears the fixed minimum sample at this checkpoint.</p>'}
    <p class="muted">${cycle?.cycle} · ${checkpoint?.days_to_election}d · House n=${house.n}. ${pmeta.reported_pollster_count ?? 0}/${pmeta.all_pollster_count ?? 0} pollsters clear the fixed reporting threshold. Evaluation only; model effect NONE.</p>`;
}

fetch('/data/model-lab.json',{cache:'no-store'})
  .then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()})
  .then(data=>{
    payload=data;
    render();
    for(const id of ['diagCycle','diagCheckpoint']) $(id)?.addEventListener('change',render);
  })
  .catch(err=>{
    if($('sourceMixPanel')) $('sourceMixPanel').innerHTML=`<p>Source-mix diagnostic unavailable: ${esc(err.message)}</p>`;
  });
