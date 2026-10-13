const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (value, digits=1) => value == null ? '—' : `${(Number(value)*100).toFixed(digits)}%`;
const pp = (value, digits=1) => value == null ? '—' : `${(Number(value)*100).toFixed(digits)} pp`;
const num = (value, digits=3) => value == null ? '—' : Number(value).toFixed(digits);
let labData = null;

function stateLabel(state){
  return ({unavailable:'UNSCORED',unscored:'UNSCORED',partial:'PARTIAL',scored:'SCORED'})[state] || String(state || 'UNKNOWN').toUpperCase();
}

function cycleCard(cycle, fixedDays){
  const checkpoints = new Map((cycle.checkpoints || []).map(c => [Number(c.days_to_election), c]));
  const rail = fixedDays.map(days => {
    const cp = checkpoints.get(Number(days));
    const ok = cp?.state === 'scored';
    return `<div class="checkpoint ${ok?'ok':''}" title="${esc(cp?.state || 'not admitted')}"><strong>${days}d</strong><span>${ok?'scored':cp?'blocked':'awaiting'}</span></div>`;
  }).join('');
  const blockers = (cycle.blocking_reasons || []).length
    ? `<ul class="blockers">${cycle.blocking_reasons.map(b => `<li>${esc(b)}</li>`).join('')}</ul>`
    : '';
  const scored = (cycle.checkpoints || []).filter(c => c?.score?.state === 'scored');
  const latest = scored.length ? scored[scored.length - 1] : null;
  const metrics = latest ? `<div class="metric-grid">
      <div class="metric"><span>Brier</span><strong>${num(latest.score.brier,4)}</strong></div>
      <div class="metric"><span>Log loss</span><strong>${num(latest.score.log_loss,4)}</strong></div>
      <div class="metric"><span>Races</span><strong>${latest.score.n}</strong></div>
      <div class="metric"><span>Checkpoint</span><strong>${latest.days_to_election}d</strong></div>
    </div>` : `<p class="muted">No performance metric exists yet. That is the correct output until the historical evidence clears every gate.</p>`;
  const chamber = cycle.chamber_scope || {};
  const senateNote = chamber.senate?.state === 'unavailable'
    ? `<p class="scope-note"><strong>Senate:</strong> unavailable for this admitted replay; it is not counted as zero.</p>`
    : '';
  return `<article class="lab-card cycle-card">
    <div class="cycle-top"><div><div class="eyebrow">ELECTION CYCLE</div><div class="cycle-year">${esc(cycle.cycle)}</div></div><span class="status-pill ${esc(cycle.state)}">${stateLabel(cycle.state)}</span></div>
    <div class="checkpoint-rail" aria-label="Replay checkpoints">${rail}</div>
    ${metrics}${senateNote}${blockers}
  </article>`;
}

function metricCells(s){
  if(!s || s.state!=='scored') return `<td>${esc(s?.n ?? 0)}</td><td colspan="6">Unavailable</td>`;
  return `<td>${s.n}</td><td>${num(s.brier,4)}</td><td>${num(s.log_loss,4)}</td><td>${pct(s.accuracy)}</td><td>${pct(s.mean_dem_probability)}</td><td>${pct(s.actual_dem_win_rate)}</td><td>${pp(s.calibration_error)}</td>`;
}

function calibrationSvg(score){
  const bins = score?.calibration || [];
  if (!bins.length) return '';
  const w=620,h=390,pad=54, innerW=w-pad*2, innerH=h-pad*2;
  const x=v=>pad+Number(v)*innerW, y=v=>h-pad-Number(v)*innerH;
  const grid=[0,.25,.5,.75,1].map(v=>`<line class="grid" x1="${x(v)}" y1="${y(0)}" x2="${x(v)}" y2="${y(1)}"/><line class="grid" x1="${x(0)}" y1="${y(v)}" x2="${x(1)}" y2="${y(v)}"/><text x="${x(v)}" y="${h-20}" text-anchor="middle">${Math.round(v*100)}%</text><text x="22" y="${y(v)+4}">${Math.round(v*100)}%</text>`).join('');
  const points=bins.map(b=>[x(b.mean_probability),y(b.observed_rate),Math.max(4,Math.min(11,3+Math.sqrt(Number(b.count))))]);
  const path=points.map((p,i)=>`${i?'L':'M'} ${p[0]} ${p[1]}`).join(' ');
  return `<svg class="cal-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Calibration chart: forecast probability versus observed win rate; point size reflects sample count">
    ${grid}<line class="ideal" x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"/><path class="series" d="${path}"/>${points.map(p=>`<circle class="point" cx="${p[0]}" cy="${p[1]}" r="${p[2]}"/>`).join('')}
    <text x="${w/2}" y="${h-2}" text-anchor="middle">Forecast Democratic win probability</text><text transform="translate(13 ${h/2}) rotate(-90)" text-anchor="middle">Observed Democratic win rate</text>
  </svg>`;
}

function selected(){
  if(!labData) return {};
  const year=Number($('diagCycle')?.value);
  const days=Number($('diagCheckpoint')?.value);
  const cycle=(labData.cycles||[]).find(c=>Number(c.cycle)===year) || (labData.cycles||[]).at(-1);
  const cp=(cycle?.checkpoints||[]).find(c=>Number(c.days_to_election)===days) || (cycle?.checkpoints||[]).at(-1);
  return {cycle,cp};
}

function renderCalibration(){
  const {cycle,cp}=selected();
  if(cp?.score?.state!=='scored'){
    $('calibrationPanel').innerHTML='<div class="empty-state"><strong>No scored checkpoint selected.</strong></div>';
    return;
  }
  const s=cp.score;
  const rows=(s.calibration||[]).map(b=>`<tr><td>${Math.round(b.lower*100)}–${Math.round(b.upper*100)}%</td><td>${b.count}</td><td>${pct(b.mean_probability)}</td><td>${pct(b.observed_rate)}</td><td>${pp(b.calibration_residual)}</td></tr>`).join('');
  $('calibrationPanel').innerHTML=`<div class="metric-grid"><div class="metric"><span>Cycle</span><strong>${cycle.cycle}</strong></div><div class="metric"><span>Checkpoint</span><strong>${cp.days_to_election}d</strong></div><div class="metric"><span>Brier</span><strong>${num(s.brier,4)}</strong></div><div class="metric"><span>Bin calibration error</span><strong>${pct(s.mean_absolute_bin_calibration_error)}</strong></div></div>
    ${calibrationSvg(s)}
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Forecast bin</th><th>n</th><th>Mean forecast</th><th>Actual D win rate</th><th>Residual</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted">Logistic calibration intercept ${num(s.calibration_intercept)} · slope ${num(s.calibration_slope)}. Ideal: 0 and 1. Fixed decile bins are shown even when some occupied bins have small n; instability is exposed, not hidden.</p>`;
}

function renderCompetitive(){
  const {cycle,cp}=selected();
  const bands=cp?.score?.competitive_bands || [];
  if(!bands.length){$('competitivePanel').innerHTML='<p class="muted">No competitive-seat diagnostic is available for this checkpoint.</p>';return;}
  $('competitivePanel').innerHTML=`<p class="method-note">Fixed before inspection. The 45–55, 40–60, 30–70 and 20–80 windows are <strong>nested</strong>; they are not additive categories. “Safe” is the complement outside 20–80.</p>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Band</th><th>n</th><th>Brier</th><th>Log loss</th><th>Winner-call</th><th>Mean D p</th><th>Actual D wins</th><th>Cal. error</th></tr></thead><tbody>${bands.map(b=>`<tr><th scope="row">${esc(b.band)}</th>${metricCells(b)}</tr>`).join('')}</tbody></table></div>
    <p class="muted">${cycle.cycle} · ${cp.days_to_election} days before Election Day.</p>`;
}

function renderPolling(){
  const {cycle,cp}=selected();
  const polling=cp?.score?.polling;
  const chambers=cp?.score?.chambers;
  if(!polling){$('pollingPanel').innerHTML='<p class="muted">No polling partition is available.</p>';return;}
  const chamberRows=['house','senate'].map(k=>`<tr><th scope="row">${k[0].toUpperCase()+k.slice(1)}</th>${metricCells(chambers?.[k])}</tr>`).join('');
  $('pollingPanel').innerHTML=`<div class="warning-note"><strong>Not a causal A/B test.</strong> Polled races are selected partly because they are competitive. This panel asks how each observed subset performed; it does not claim polling caused the difference.</div>
    <h3>Eligible race-level polling</h3>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Subset</th><th>n</th><th>Brier</th><th>Log loss</th><th>Winner-call</th><th>Mean D p</th><th>Actual D wins</th><th>Cal. error</th></tr></thead><tbody><tr><th scope="row">Polled</th>${metricCells(polling.polled)}</tr><tr><th scope="row">Unpolled</th>${metricCells(polling.unpolled)}</tr></tbody></table></div>
    <h3>Chamber</h3>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Chamber</th><th>n</th><th>Brier</th><th>Log loss</th><th>Winner-call</th><th>Mean D p</th><th>Actual D wins</th><th>Cal. error</th></tr></thead><tbody>${chamberRows}</tbody></table></div>
    <p class="muted">${cycle.cycle} · ${cp.days_to_election}d. Missing chamber evaluation is explicitly unavailable, never zero.</p>`;
}

function renderMovement(){
  const {cycle}=selected();
  const m=cycle?.movement;
  if(m?.state!=='scored'){$('movementPanel').innerHTML='<p class="muted">A complete five-checkpoint cycle is required for movement diagnostics.</p>';return;}
  const transitions=(m.transitions||[]).map(t=>`<tr><td>${t.from_days}→${t.to_days}d</td><td>${t.n}</td><td>${pct(t.mean_absolute_probability_change)}</td><td>${t.toward_eventual_winner}</td><td>${t.away_from_eventual_winner}</td><td>${t.strong_toward_eventual_winner}</td><td>${t.strong_away_from_eventual_winner}</td></tr>`).join('');
  const late=(m.large_late_swings||[]).slice(0,12).map(r=>`<tr><td>${esc(r.race_code)}</td><td>${esc(r.race_type)}</td><td>${esc(r.winner)}</td><td>${pp(r.winner_directed_change_7_to_1)}</td><td>${pp(r.late_absolute_change)}</td></tr>`).join('');
  const pollingMovement=(m.transitions||[]).map(t=>{
    const g=t.polling_status_movement || {};
    const p=g.polled_at_later_checkpoint || {};
    const u=g.unpolled_at_later_checkpoint || {};
    return `<tr><td>${t.from_days}→${t.to_days}d</td><td>${p.n ?? 0}</td><td>${pp(p.mean_absolute_probability_change)}</td><td>${pp(p.mean_winner_directed_probability_change)}</td><td>${u.n ?? 0}</td><td>${pp(u.mean_absolute_probability_change)}</td><td>${pp(u.mean_winner_directed_probability_change)}</td></tr>`;
  }).join('');
  $('movementPanel').innerHTML=`<div class="metric-grid"><div class="metric"><span>Cycle</span><strong>${cycle.cycle}</strong></div><div class="metric"><span>Common races</span><strong>${m.common_race_count}</strong></div><div class="metric"><span>Strong move</span><strong>≥${Math.round(m.movement_threshold*100)} pp</strong></div><div class="metric"><span>Confident miss</span><strong>≥${Math.round(m.confident_miss_threshold*100)}%</strong></div></div>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Transition</th><th>n</th><th>Mean |move|</th><th>Toward winner</th><th>Away</th><th>Strong toward</th><th>Strong away</th></tr></thead><tbody>${transitions}</tbody></table></div>
    <h3>Movement by later-checkpoint polling status</h3>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Transition</th><th>Polled n</th><th>Polled |move|</th><th>Polled winner-directed</th><th>Unpolled n</th><th>Unpolled |move|</th><th>Unpolled winner-directed</th></tr></thead><tbody>${pollingMovement}</tbody></table></div>
    <p class="muted">Each transition partitions the common race sample by whether an eligible race-level poll exists at the later checkpoint. This describes movement; it is not a causal estimate of polling value.</p>
    <h3>Largest late swings, 7→1 days</h3>
    ${late?`<div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Race</th><th>Chamber</th><th>Winner</th><th>Winner-directed</th><th>Absolute move</th></tr></thead><tbody>${late}</tbody></table></div>`:'<p class="muted">No ≥10-point late swings.</p>'}
    <p class="muted">“Toward winner” uses the certified result only after the checkpoint probabilities are frozen. It is a forensic label, not a predictive input.</p>`;
}

function renderComparison(data){
  const x=data.cross_cycle || {};
  const rows=(x.cycles||[]).map(r=>`<tr><th scope="row">${r.cycle}</th><td>${r.best_brier_checkpoint_days}d</td><td>${num(r.best_brier,4)}</td><td>${num(r.brier_60d,4)}</td><td>${num(r.brier_14d,4)}</td><td>${num(r.brier_7d,4)}</td><td>${num(r.brier_1d,4)}</td><td>${r.brier_change_7d_to_1d==null?'—':`${r.brier_change_7d_to_1d>=0?'+':''}${num(r.brier_change_7d_to_1d,4)}`}</td><td>${r.brier_change_14d_to_1d==null?'—':`${r.brier_change_14d_to_1d>=0?'+':''}${num(r.brier_change_14d_to_1d,4)}`}</td><td>${esc(r.final_week_direction)}</td><td>${r.confident_misses_1d ?? '—'}</td></tr>`).join('');
  const hypotheses=(x.hypotheses||[]).map(h=>`<div class="hypothesis"><strong>${esc(h.id.replaceAll('_',' '))}</strong><span>${esc(h.state.replaceAll('_',' '))}</span><small>${esc(h.evidence)}</small></div>`).join('');
  $('comparisonPanel').innerHTML=`<div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Cycle</th><th>Best point</th><th>Best Brier</th><th>60d</th><th>14d</th><th>7d</th><th>1d</th><th>7→1 Δ</th><th>14→1 Δ</th><th>Final week (7→1)</th><th>Confident misses 1d</th></tr></thead><tbody>${rows}</tbody></table></div><p class="method-note">${esc(x.interpretation || '')}</p><div class="hypothesis-grid">${hypotheses}</div>`;
}

function renderFailures(data){
  const misses=[];
  for(const cycle of data.cycles || []) for(const cp of cycle.checkpoints || []) for(const miss of cp?.score?.misses || []) misses.push({...miss,cycle:cycle.cycle,days:cp.days_to_election});
  misses.sort((a,b)=>Number(b.surprise)-Number(a.surprise));
  if(!misses.length){
    $('failurePanel').innerHTML=`<div class="empty-state"><strong>No wrong-side calls in the admitted output.</strong></div>`;
    return;
  }
  $('failurePanel').innerHTML=`<div class="table-wrap"><table class="failure-table"><thead><tr><th>Cycle</th><th>Cutoff</th><th>Race</th><th>Chamber</th><th>Winner</th><th>Winner p</th><th>Confident miss?</th></tr></thead><tbody>${misses.slice(0,25).map(m=>`<tr><td>${m.cycle}</td><td>${m.days}d</td><td>${esc(m.race_code)}</td><td>${esc(m.race_type)}</td><td>${esc(m.winner)}</td><td>${pct(m.winner_probability)}</td><td>${m.confident_miss?'yes':'no'}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderControls(data){
  const cycles=(data.cycles||[]).filter(c=>c.state==='scored');
  $('diagCycle').innerHTML=cycles.map(c=>`<option value="${c.cycle}">${c.cycle}</option>`).join('');
  if(cycles.length)$('diagCycle').value=String(cycles.at(-1).cycle);
  $('diagCheckpoint').innerHTML=(data.checkpoints_days_to_election||[]).map(d=>`<option value="${d}">${d} days</option>`).join('');
  $('diagCheckpoint').value='1';
  for(const id of ['diagCycle','diagCheckpoint']) $(id).addEventListener('change',renderSelectedDiagnostics);
}

function renderSelectedDiagnostics(){
  renderCalibration();
  renderCompetitive();
  renderPolling();
  renderMovement();
}

function render(data){
  labData=data;
  const summary=data.summary || {};
  $('labState').dataset.state=summary.state || 'unscored';
  $('labState').textContent=`${stateLabel(summary.state)} · ${summary.scored_cycles || 0}/${summary.requested_cycles || 0} historical cycles scored`;
  $('cycleGrid').innerHTML=(data.cycles || []).map(c=>cycleCard(c,data.checkpoints_days_to_election || [])).join('') || '<div class="lab-card">No cycle manifests found.</div>';
  renderControls(data);
  renderSelectedDiagnostics();
  renderComparison(data);
  renderFailures(data);
  $('guardGrid').innerHTML=(data.leakage_guards || []).map(g=>`<div class="guard">${esc(g)}</div>`).join('');
  const c=data.model_contract || {}, d=data.diagnostic_contract || {};
  $('contractDetails').innerHTML=`<dt>Contract</dt><dd>${esc(c.id)}</dd><dt>Production check</dt><dd>${esc(c.state)}</dd><dt>SHA-256</dt><dd><code>${esc(c.contract_fingerprint_sha256)}</code></dd><dt>Retuning</dt><dd>${data.retuning_allowed?'Allowed':'Forbidden in replay'}</dd><dt>Structural weights</dt><dd>${esc((c.structural_weights || []).join(' / '))}</dd><dt>Polling windows</dt><dd>Generic ${esc(c.generic_ballot?.window_days)} days · race ${esc(c.race_polls?.window_days)} days</dd><dt>Diagnostic bands</dt><dd>${esc((d.competitive_bands||[]).map(b=>b.label).join(' · '))}</dd><dt>Movement threshold</dt><dd>${pct(d.movement_threshold)}</dd>`;
}

fetch('/data/model-lab.json',{cache:'no-store'})
  .then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()})
  .then(render)
  .catch(err=>{
    $('labState').dataset.state='unscored';$('labState').textContent='MODEL LAB DATA UNAVAILABLE';
    $('cycleGrid').innerHTML=`<div class="lab-card"><strong>Audit artefact could not be read.</strong><p>${esc(err.message)}</p></div>`;
    for(const id of ['calibrationPanel','competitivePanel','pollingPanel','movementPanel','comparisonPanel','failurePanel']) if($(id)) $(id).innerHTML='<p>No diagnostic claim can be made.</p>';
  });
