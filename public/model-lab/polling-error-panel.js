const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n = (value,digits=2) => value == null ? '—' : Number(value).toFixed(digits);
const signedPP = (value,digits=2) => value == null ? '—' : `${Number(value)>=0?'+':''}${Number(value).toFixed(digits)} pp`;
const pct = (value,digits=1) => value == null ? '—' : `${(Number(value)*100).toFixed(digits)}%`;
let payload = null;

function selection(){
  const scored=(payload?.cycles||[]).filter(c=>c.state==='scored');
  const year=Number($('diagCycle')?.value || scored.at(-1)?.cycle);
  const days=Number($('diagCheckpoint')?.value || 1);
  const cycle=scored.find(c=>Number(c.cycle)===year) || scored.at(-1);
  const checkpoint=(cycle?.checkpoints||[]).find(c=>Number(c.days_to_election)===days) || (cycle?.checkpoints||[]).at(-1);
  return {cycle,checkpoint};
}

function errorRow(label,s){
  if(!s || s.state!=='scored') return `<tr><th scope="row">${esc(label)}</th><td colspan="7">Unavailable</td></tr>`;
  const raw=s.raw_race_poll_aggregate||{};
  const prior=s.structural_plus_generic_prior||{};
  const full=s.published_full_model_margin||{};
  const compare=s.model_comparison||{};
  return `<tr><th scope="row">${esc(label)}</th><td>${s.n}</td><td>${n(raw.mae_pp)}</td><td>${signedPP(raw.mean_error_d_minus_r_pp)}</td><td>${n(prior.mae_pp)}</td><td>${n(full.mae_pp)}</td><td class="${Number(compare.mae_delta_full_minus_raw_poll_pp)<0?'good-delta':Number(compare.mae_delta_full_minus_raw_poll_pp)>0?'bad-delta':''}">${signedPP(compare.mae_delta_full_minus_raw_poll_pp)}</td><td>${pct(raw.winner_call_accuracy)} → ${pct(full.winner_call_accuracy)}</td></tr>`;
}

function forensicRows(diag){
  return (diag?.forensics?.largest_raw_poll_errors||[]).slice(0,10).map(r=>`<tr><td>${esc(r.race_code)}</td><td>${signedPP(r.raw_poll_margin_d_minus_r)}</td><td>${signedPP(r.result_margin_d_minus_r)}</td><td>${signedPP(r.raw_poll_error_d_minus_r_pp)}</td><td>${signedPP(r.full_model_margin_d_minus_r)}</td><td>${signedPP(r.full_abs_error_minus_poll_abs_error_pp)}</td><td>${r.poll_count}</td></tr>`).join('');
}

function render(){
  const panel=$('pollErrorPanel');
  if(!panel) return;
  const {cycle,checkpoint}=selection();
  const diag=checkpoint?.score?.polling_error;
  if(!diag || diag.state!=='scored'){
    panel.innerHTML='<p class="muted">Raw polling-error decomposition unavailable for this checkpoint.</p>';
    return;
  }
  const rows=[errorRow('All polled races',diag.all_polled),errorRow('House only',diag.house_only),errorRow('Senate only',diag.senate_only)].join('');
  const forensic=forensicRows(diag);
  const missing=diag.missing_result_margin_races||[];
  panel.innerHTML=`<div class="warning-note"><strong>Poll error is not a causal diagnosis.</strong> This compares the exact race-poll aggregate available to the frozen model with the certified two-party result margin. It can expose direction and size of error; it cannot by itself tell us whether pollster mix, turnout, sampling, mode or electorate change caused it.</div>
    <h3>Poll → result → model</h3>
    <p class="method-note">Margin error is measured in percentage points of Democratic minus Republican two-party margin. <strong>Positive bias means too Democratic; negative means too Republican.</strong> The full-model comparison asks whether blending polls with the frozen prior moved the estimate closer to the certified margin.</p>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Same-race sample</th><th>n</th><th>Raw poll MAE</th><th>Raw poll bias</th><th>Prior MAE</th><th>Full model MAE</th><th>Δ full − poll MAE</th><th>Winner call: poll → full</th></tr></thead><tbody>${rows}</tbody></table></div>
    <h3>Largest raw polling misses</h3>
    ${forensic?`<div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Race</th><th>Poll margin</th><th>Result margin</th><th>Poll error</th><th>Full margin</th><th>Δ |error| full − poll</th><th>Polls</th></tr></thead><tbody>${forensic}</tbody></table></div>`:'<p class="muted">No eligible polling-error rows.</p>'}
    <p class="muted">${cycle?.cycle} · ${checkpoint?.days_to_election}d · ${diag.n} scored polled races.${missing.length?` ${missing.length} polled race${missing.length===1?'':'s'} had no lawful certified D/R margin and ${missing.length===1?'was':'were'} excluded rather than treated as zero.`:''} Evaluation only; model effect NONE.</p>`;
}

fetch('/data/model-lab.json',{cache:'no-store'})
  .then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()})
  .then(data=>{
    payload=data;
    render();
    for(const id of ['diagCycle','diagCheckpoint']) $(id)?.addEventListener('change',render);
  })
  .catch(err=>{
    if($('pollErrorPanel')) $('pollErrorPanel').innerHTML=`<p>Raw polling-error diagnostic unavailable: ${esc(err.message)}</p>`;
  });
