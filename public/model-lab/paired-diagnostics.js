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

function pairedRow(label,s){
  if(!s || s.state!=='scored') return `<tr><th scope="row">${esc(label)}</th><td colspan="9">Unavailable</td></tr>`;
  const brierClass=Number(s.brier_delta_with_polls_minus_prior)<0?'good-delta':'bad-delta';
  const logClass=Number(s.log_loss_delta_with_polls_minus_prior)<0?'good-delta':'bad-delta';
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

function partitionCells(s){
  if(!s || s.state!=='scored') return '<td>0</td><td colspan="5">Unavailable</td>';
  return `<td>${s.n}</td><td>${pct(s.mean_absolute_probability_change)}</td><td>${pp(s.mean_winner_directed_probability_change)}</td><td>${s.toward_eventual_winner}</td><td>${s.away_from_eventual_winner}</td><td>${s.strong_toward_eventual_winner}/${s.strong_away_from_eventual_winner}</td>`;
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
  $('movementPollingPanel').innerHTML=`<h3>Movement by polling status</h3>
    <p class="method-note">This separates probability movement by whether a race had eligible race polling at the later checkpoint. “Newly polled” means zero eligible race polls at the earlier checkpoint and at least one at the later checkpoint.</p>
    <div class="table-wrap"><table class="diagnostic-table"><thead><tr><th>Transition</th><th>Status</th><th>n</th><th>Mean |move|</th><th>Mean toward winner</th><th>Toward</th><th>Away</th><th>Strong toward / away</th></tr></thead><tbody>${html.join('')}</tbody></table></div>
    <p class="muted">Outcome direction is applied only after both checkpoint forecasts are frozen.</p>`;
}

function render(){
  if(!data) return;
  renderPaired();
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
    if($('movementPollingPanel')) $('movementPollingPanel').innerHTML='<p>Movement partition unavailable.</p>';
  });
