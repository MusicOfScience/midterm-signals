const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (value,digits=4) => value == null ? '—' : Number(value).toFixed(digits);
const pct = (value,digits=1) => value == null ? '—' : `${(Number(value)*100).toFixed(digits)}%`;
const pp = (value,digits=1) => value == null ? '—' : `${(Number(value)*100).toFixed(digits)} pp`;
let data = null;

function selection(){
  const scored=(data?.cycles||[]).filter(c=>c.state==='scored');
  const selectedYear=Number($('diagCycle')?.value || scored.at(-1)?.cycle);
  const selectedDays=Number($('diagCheckpoint')?.value || 1);
  const cycle=scored.find(c=>Number(c.cycle)===selectedYear) || scored.at(-1);
  const checkpoint=(cycle?.checkpoints||[]).find(c=>Number(c.days_to_election)===selectedDays) || (cycle?.checkpoints||[]).at(-1);
  return {cycle,checkpoint};
}

function deltaClass(value){
  return Number(value)<0?'good-delta':Number(value)>0?'bad-delta':'';
}

function pairedRow(label,s){
  if(!s || s.state!=='scored') return `<tr><th scope="row">${esc(label)}</th><td colspan="9">Unavailable</td></tr>`;
  const brierClass=deltaClass(s.brier_delta_with_polls_minus_prior);
  const logClass=deltaClass(s.log_loss_delta_with_polls_minus_prior);
  return `<tr><th scope="row">${esc(label)}</th><td>${s.n}</td><td>${num(s.prior_brier)}</td><td>${num(s.with_race_polls_brier)}</td><td class="${brierClass}">${num(s.brier_delta_with_polls_minus_prior)}</td><td>${num(s.prior_log_loss)}</td><td>${num(s.with_race_polls_log_loss)}</td><td class="${logClass}">${num(s.log_loss_delta_with_polls_minus_prior)}</td><td>${pp(s.mean_winner_directed_probability_change)}</td><td>${s.moved_toward_eventual_winner}/${s.moved_away_from_eventual_winner}</td></tr>`;
}

function renderPaired(){
  const {cycle,checkpoint}=selection();
  const polling=checkpoint?.score?.polling;
  const all=polling?.paired_component_test;
  const competitive=polling?.paired_component_test_prior_20_80;
  if(!all){
    $('pairedPollingPanel').innerHTML='<p class="muted">Paired polling-component diagnostic unavailable.</p>';
    return;
  }
  $('pairedPollingPanel').innerHTML=`<h3>Same-race component test</h3>
    <p class="method-note">This is the stronger polling diagnostic. For each race that had eligible race-level polls, it compares the published forecast with that <strong>same race’s frozen structural + generic-ballot prior</strong> before the race-poll blend. Negative score deltas mean the poll component improved the paired forecasts.</p>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Paired sample</th><th>n</th><th>Prior Brier</th><th>With polls</th><th>Δ Brier</th><th>Prior log loss</th><th>With polls</th><th>Δ log loss</th><th>Mean move toward winner</th><th>Toward / away</th></tr></thead><tbody>${pairedRow('All polled races',all)}${pairedRow('Prior 20–80%',competitive)}</tbody></table></div>
    <p class="muted">${cycle?.cycle} · ${checkpoint?.days_to_election}d. This isolates the model component on the same races, but it remains an evaluation of the admitted polling stream rather than a causal claim about polling in general.</p>`;
}

function structuralRow(label,s){
  if(!s || s.state!=='scored') return `<tr><th scope="row">${esc(label)}</th><td colspan="7">Unavailable</td></tr>`;
  return `<tr><th scope="row">${esc(label)}</th><td>${s.n}</td><td>${num(s.structural_plus_incumbency?.brier)}</td><td>${num(s.structural_plus_generic_ballot?.brier)}</td><td class="${deltaClass(s.brier_delta_generic_minus_structural)}">${num(s.brier_delta_generic_minus_structural)}</td><td>${num(s.published_full_forecast?.brier)}</td><td class="${deltaClass(s.brier_delta_full_minus_prior)}">${num(s.brier_delta_full_minus_prior)}</td><td class="${deltaClass(s.brier_delta_full_minus_structural)}">${num(s.brier_delta_full_minus_structural)}</td></tr>`;
}

function structuralMissRows(s){
  return (s?.confident_structural_misses||[]).slice(0,12).map(r=>`<tr><td>${esc(r.race_code)}</td><td>${esc(r.winner)}</td><td>${pct(r.winner_probability_structural)}</td><td>${pct(r.dem_probability_structural)}</td><td>${pct(r.dem_probability_after_generic)}</td><td>${pct(r.dem_probability_full)}</td><td>${pp(r.generic_winner_directed_change)}</td><td>${pp(r.poll_winner_directed_change)}</td></tr>`).join('');
}

function renderStructural(){
  const panel=$('structuralAuditPanel');
  if(!panel) return;
  const {cycle,checkpoint}=selection();
  const all=checkpoint?.score?.structural_decomposition;
  const competitive=checkpoint?.score?.structural_decomposition_20_80;
  if(!all){
    panel.innerHTML='<p class="muted">Structural-stage diagnostic unavailable.</p>';
    return;
  }
  const misses=structuralMissRows(all);
  panel.innerHTML=`<div class="warning-note"><strong>Diagnostic, not a redistricting verdict.</strong> This scores the frozen structural presidential-relative-lean + incumbency stage before later information is added. A weak structural stage is evidence about the baseline; it does not by itself identify changed district boundaries as the cause.</div>
    <h3>Where does forecast skill enter?</h3>
    <p class="method-note">The same two-major-party races are carried through three stages: <strong>structural + incumbency</strong> → <strong>+ generic ballot</strong> → <strong>published full forecast</strong>. Negative Δ Brier means the newly added stage improved the same sample.</p>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Fixed sample</th><th>n</th><th>Structural Brier</th><th>+ generic</th><th>Δ generic</th><th>Full</th><th>Δ race polls</th><th>Total Δ</th></tr></thead><tbody>${structuralRow('All two-party contests',all)}${structuralRow('Structural 20–80%',competitive)}</tbody></table></div>
    <div class="metric-grid"><div class="metric"><span>Generic mean move toward winner</span><strong>${pp(all.generic_ballot_effect?.mean_winner_directed_probability_change)}</strong></div><div class="metric"><span>Race-poll mean move toward winner</span><strong>${pp(all.race_poll_effect?.mean_winner_directed_probability_change)}</strong></div><div class="metric"><span>Total mean move toward winner</span><strong>${pp(all.total_information_effect?.mean_winner_directed_probability_change)}</strong></div><div class="metric"><span>Confident structural misses</span><strong>${all.confident_structural_misses?.length ?? '—'}</strong></div></div>
    <h3>Confident structural misses</h3>
    ${misses?`<div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Race</th><th>Winner</th><th>Winner p at structure</th><th>D p structure</th><th>D p + generic</th><th>D p full</th><th>Generic move toward winner</th><th>Poll move toward winner</th></tr></thead><tbody>${misses}</tbody></table></div>`:'<p class="muted">No structural-stage miss crossed the fixed 80% confidence threshold in this selected sample.</p>'}
    <p class="muted">${cycle?.cycle} · ${checkpoint?.days_to_election}d. No coefficient changes. No post-election district field is fed into any probability.</p>`;
}

function stabilityBandLabel(key){
  return ({stable_0_5:'0–5 pp',moderate_5_10:'>5–10 pp',high_10_15:'>10–15 pp',very_high_gt_15:'>15 pp'})[key] || key;
}

function stabilityBandRow(s){
  if(!s || s.state!=='scored') return `<tr><th scope="row">${esc(stabilityBandLabel(s?.band||''))}</th><td>${s?.n||0}</td><td colspan="6">Unavailable</td></tr>`;
  return `<tr><th scope="row">${esc(stabilityBandLabel(s.band))}</th><td>${s.n}</td><td>${num(s.mean_range_pp,1)} pp</td><td>${num(s.structural_plus_incumbency?.brier)}</td><td>${num(s.published_full_forecast?.brier)}</td><td class="${deltaClass(s.brier_delta_full_minus_structural)}">${num(s.brier_delta_full_minus_structural)}</td><td>${s.structural_confident_misses}</td><td>${s.full_confident_misses}</td></tr>`;
}

function unstableRaceRows(s){
  return (s?.top_unstable||[]).slice(0,12).map(r=>`<tr><td>${esc(r.race_code)}</td><td>${num(r.range_pp,1)} pp</td><td>${pp(r.trend_earliest_to_latest_pp)}</td><td>${esc((r.relative_leans_d_minus_r||[]).map(v=>`${Number(v).toFixed(1)}`).join(' → '))}</td><td>${esc(r.winner)}</td><td>${pct(r.winner_probability_structural)}</td><td>${pct(r.winner_probability_full)}</td><td>${r.poll_count}</td></tr>`).join('');
}

function renderBaselineStability(){
  const panel=$('baselineStabilityPanel');
  if(!panel) return;
  const {cycle,checkpoint}=selection();
  const s=checkpoint?.score?.baseline_stability;
  if(!s || s.state!=='scored'){
    panel.innerHTML='<p class="muted">Baseline-stability diagnostic unavailable.</p>';
    return;
  }
  const rows=(s.bands||[]).map(stabilityBandRow).join('');
  const unstable=unstableRaceRows(s);
  panel.innerHTML=`<div class="warning-note"><strong>Volatility is not redistricting.</strong> This test asks whether the three pre-election presidential relative leans were internally stable on the cycle’s own district geography. A volatile history can reflect realignment, demographic change or baseline non-stationarity. It does not prove a boundary effect.</div>
    <h3>Did unstable structural history fail more often?</h3>
    <p class="method-note">Bands are fixed before outcomes: 0–5, &gt;5–10, &gt;10–15 and &gt;15 percentage-point range across the three admitted presidential relative leans. Only House races with both major-party candidates are included.</p>
    <div class="metric-grid"><div class="metric"><span>House two-party sample</span><strong>${s.n}</strong></div><div class="metric"><span>&gt;10 pp instability</span><strong>${s.high_instability_n}</strong></div><div class="metric"><span>Share &gt;10 pp</span><strong>${pct(s.high_instability_share)}</strong></div><div class="metric"><span>Band assignment</span><strong>PRE-OUTCOME</strong></div></div>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Relative-lean range</th><th>n</th><th>Mean range</th><th>Structural Brier</th><th>Full Brier</th><th>Total Δ</th><th>Structural 80% misses</th><th>Full 80% misses</th></tr></thead><tbody>${rows}</tbody></table></div>
    <h3>Most unstable structural histories</h3>
    ${unstable?`<div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Race</th><th>Range</th><th>Earliest→latest</th><th>Relative leans D−R</th><th>Winner</th><th>Winner p structure</th><th>Winner p full</th><th>Polls</th></tr></thead><tbody>${unstable}</tbody></table></div>`:'<p class="muted">No eligible unstable races.</p>'}
    <p class="muted">${cycle?.cycle} · ${checkpoint?.days_to_election}d. For 2022, the admitted presidential inputs were reconstructed on the 118th-Congress district geography before this diagnostic; old district numbers are not carried forward as structural inputs.</p>`;
}

function partitionCells(s){
  if(!s || s.state!=='scored') return '<td>0</td><td colspan="5">Unavailable</td>';
  return `<td>${s.n}</td><td>${pct(s.mean_absolute_probability_change)}</td><td>${pp(s.mean_winner_directed_probability_change)}</td><td>${s.toward_eventual_winner}</td><td>${s.away_from_eventual_winner}</td><td>${s.strong_toward_eventual_winner}/${s.strong_away_from_eventual_winner}</td>`;
}

function rosterRows(cycle){
  const transitions=cycle?.movement?.roster_transitions || [];
  const rows=[];
  for(const t of transitions){
    for(const change of t.changes || []){
      if(!change.large_movement && change.absolute_probability_change===0) continue;
      rows.push(`<tr><td>${t.from_days}→${t.to_days}d</td><td>${esc(change.race_code)}</td><td>${esc(change.before?.dem_candidate || '—')} / ${esc(change.before?.rep_candidate || '—')}</td><td>${esc(change.after?.dem_candidate || '—')} / ${esc(change.after?.rep_candidate || '—')}</td><td>${pp(change.absolute_probability_change)}</td><td>${pp(change.winner_directed_probability_change)}</td></tr>`);
    }
  }
  return rows;
}

function renderMovementPartitions(){
  const {cycle}=selection();
  const rows=cycle?.movement?.polling_partitions || [];
  if(!rows.length){
    $('movementPollingPanel').innerHTML='<p class="muted">Movement-by-polling-status diagnostic unavailable.</p>';
    return;
  }
  const html=[];
  for(const r of rows){
    html.push(`<tr><th scope="row" rowspan="3">${r.from_days}→${r.to_days}d</th><td>Later polled</td>${partitionCells(r.later_polled)}</tr>`);
    html.push(`<tr><td>Later unpolled</td>${partitionCells(r.later_unpolled)}</tr>`);
    html.push(`<tr><td>Newly polled</td>${partitionCells(r.newly_polled)}</tr>`);
  }
  const roster=rosterRows(cycle);
  $('movementPollingPanel').innerHTML=`<h3>Movement by polling status</h3>
    <p class="method-note">This separates probability movement by whether a race had eligible race polling at the later checkpoint. “Newly polled” means zero eligible race polls at the earlier checkpoint and at least one at the later checkpoint.</p>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Transition</th><th>Status</th><th>n</th><th>Mean |move|</th><th>Mean toward winner</th><th>Toward</th><th>Away</th><th>Strong toward / away</th></tr></thead><tbody>${html.join('')}</tbody></table></div>
    <h3>Candidate-roster transitions</h3>
    <p class="warning-note">A candidate-pair change can create a very large mechanical probability move under the frozen no-opponent rule. These historical forecasts are preserved, but the transition is labelled so it is not mistaken for ordinary late polling or campaign information.</p>
    ${roster.length?`<div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Transition</th><th>Race</th><th>Before roster</th><th>After roster</th><th>|move|</th><th>Winner-directed</th></tr></thead><tbody>${roster.join('')}</tbody></table></div>`:'<p class="muted">No material roster-state movement in this cycle.</p>'}
    <p class="muted">Outcome direction is applied only after both checkpoint forecasts are frozen. Roster transitions are diagnostic labels only; no historical probability is rewritten.</p>`;
}

function render(){
  if(!data) return;
  renderPaired();
  renderStructural();
  renderBaselineStability();
  renderMovementPartitions();
}

fetch('/data/model-lab.json',{cache:'no-store'})
  .then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()})
  .then(payload=>{
    data=payload;
    render();
    for(const id of ['diagCycle','diagCheckpoint']) $(id)?.addEventListener('change',render);
  })
  .catch(err=>{
    if($('pairedPollingPanel')) $('pairedPollingPanel').innerHTML=`<p>Paired diagnostic unavailable: ${esc(err.message)}</p>`;
    if($('structuralAuditPanel')) $('structuralAuditPanel').innerHTML='<p>Structural-stage diagnostic unavailable.</p>';
    if($('baselineStabilityPanel')) $('baselineStabilityPanel').innerHTML='<p>Baseline-stability diagnostic unavailable.</p>';
    if($('movementPollingPanel')) $('movementPollingPanel').innerHTML='<p>Movement partition unavailable.</p>';
  });
