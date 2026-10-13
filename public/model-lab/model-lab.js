const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (value, digits=1) => value == null ? '—' : `${(Number(value)*100).toFixed(digits)}%`;
const num = (value, digits=3) => value == null ? '—' : Number(value).toFixed(digits);

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
  return `<article class="lab-card cycle-card">
    <div class="cycle-top"><div><div class="eyebrow">ELECTION CYCLE</div><div class="cycle-year">${esc(cycle.cycle)}</div></div><span class="status-pill ${esc(cycle.state)}">${stateLabel(cycle.state)}</span></div>
    <div class="checkpoint-rail" aria-label="Replay checkpoints">${rail}</div>
    ${metrics}${blockers}
  </article>`;
}

function calibrationSvg(score){
  const bins = score?.calibration || [];
  if (!bins.length) return '';
  const w=620,h=390,pad=54, innerW=w-pad*2, innerH=h-pad*2;
  const x=v=>pad+Number(v)*innerW, y=v=>h-pad-Number(v)*innerH;
  const grid=[0,.25,.5,.75,1].map(v=>`<line class="grid" x1="${x(v)}" y1="${y(0)}" x2="${x(v)}" y2="${y(1)}"/><line class="grid" x1="${x(0)}" y1="${y(v)}" x2="${x(1)}" y2="${y(v)}"/><text x="${x(v)}" y="${h-20}" text-anchor="middle">${Math.round(v*100)}%</text><text x="22" y="${y(v)+4}">${Math.round(v*100)}%</text>`).join('');
  const points=bins.map(b=>[x(b.mean_probability),y(b.observed_rate)]);
  const path=points.map((p,i)=>`${i?'L':'M'} ${p[0]} ${p[1]}`).join(' ');
  return `<svg class="cal-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Calibration chart: forecast probability versus observed win rate">
    ${grid}<line class="ideal" x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"/><path class="series" d="${path}"/>${points.map(p=>`<circle class="point" cx="${p[0]}" cy="${p[1]}" r="5"/>`).join('')}
    <text x="${w/2}" y="${h-2}" text-anchor="middle">Forecast Democratic win probability</text><text transform="translate(13 ${h/2}) rotate(-90)" text-anchor="middle">Observed Democratic win rate</text>
  </svg>`;
}

function renderCalibration(data){
  const scored=[];
  for(const cycle of data.cycles || []) for(const cp of cycle.checkpoints || []) if(cp?.score?.state==='scored') scored.push({cycle,cp});
  if(!scored.length){
    $('calibrationPanel').innerHTML=`<div class="empty-state"><strong>No fake certainty.</strong><p>The 2018 and 2022 Brier scores and log loss remain deliberately unpublished. The replay engine exists; the admitted leakage-free corpus does not yet. When it does, this panel will render the diagnostics from the same machine-readable artefact.</p></div>`;
    return;
  }
  const {cycle,cp}=scored[scored.length-1];
  $('calibrationPanel').innerHTML=`<div class="metric-grid"><div class="metric"><span>Cycle</span><strong>${cycle.cycle}</strong></div><div class="metric"><span>Checkpoint</span><strong>${cp.days_to_election}d</strong></div><div class="metric"><span>Brier</span><strong>${num(cp.score.brier,4)}</strong></div><div class="metric"><span>Log loss</span><strong>${num(cp.score.log_loss,4)}</strong></div></div>${calibrationSvg(cp.score)}<p class="muted">Calibration intercept ${num(cp.score.calibration_intercept)} · slope ${num(cp.score.calibration_slope)}. Ideal: 0 and 1 respectively.</p>`;
}

function renderFailures(data){
  const misses=[];
  for(const cycle of data.cycles || []) for(const cp of cycle.checkpoints || []) for(const miss of cp?.score?.misses || []) misses.push({...miss,cycle:cycle.cycle,days:cp.days_to_election});
  misses.sort((a,b)=>Number(b.surprise)-Number(a.surprise));
  if(!misses.length){
    $('failurePanel').innerHTML=`<div class="empty-state"><strong>Failure analysis is waiting for valid failures.</strong><p>We will not invent a rogues' gallery from final results and hindsight. Once a cycle is admitted, wrong-side calls are ranked by how improbable the eventual winner looked at the time.</p></div>`;
    return;
  }
  $('failurePanel').innerHTML=`<div class="table-wrap"><table class="failure-table"><thead><tr><th>Cycle</th><th>Cutoff</th><th>Race</th><th>Winner</th><th>Winner probability</th></tr></thead><tbody>${misses.slice(0,20).map(m=>`<tr><td>${m.cycle}</td><td>${m.days}d</td><td>${esc(m.race_code)}</td><td>${esc(m.winner)}</td><td>${pct(m.winner_probability)}</td></tr>`).join('')}</tbody></table></div>`;
}

function render(data){
  const summary=data.summary || {};
  $('labState').dataset.state=summary.state || 'unscored';
  $('labState').textContent=`${stateLabel(summary.state)} · ${summary.scored_cycles || 0}/${summary.requested_cycles || 0} historical cycles scored`;
  $('cycleGrid').innerHTML=(data.cycles || []).map(c=>cycleCard(c,data.checkpoints_days_to_election || [])).join('') || '<div class="lab-card">No cycle manifests found.</div>';
  renderCalibration(data);
  renderFailures(data);
  $('guardGrid').innerHTML=(data.leakage_guards || []).map(g=>`<div class="guard">${esc(g)}</div>`).join('');
  const c=data.model_contract || {};
  $('contractDetails').innerHTML=`<dt>Contract</dt><dd>${esc(c.id)}</dd><dt>Production check</dt><dd>${esc(c.state)}</dd><dt>SHA-256</dt><dd><code>${esc(c.contract_fingerprint_sha256)}</code></dd><dt>Retuning</dt><dd>${data.retuning_allowed?'Allowed':'Forbidden in replay'}</dd><dt>Structural weights</dt><dd>${esc((c.structural_weights || []).join(' / '))}</dd><dt>Polling windows</dt><dd>Generic ${esc(c.generic_ballot?.window_days)} days · race ${esc(c.race_polls?.window_days)} days</dd>`;
}

fetch('/data/model-lab.json',{cache:'no-store'})
  .then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()})
  .then(render)
  .catch(err=>{
    $('labState').dataset.state='unscored';$('labState').textContent='MODEL LAB DATA UNAVAILABLE';
    $('cycleGrid').innerHTML=`<div class="lab-card"><strong>Audit artefact could not be read.</strong><p>${esc(err.message)}</p></div>`;
    $('calibrationPanel').innerHTML='<p>No calibration claim can be made.</p>';
    $('failurePanel').innerHTML='<p>No failure claim can be made.</p>';
  });
