import { readFile, access } from 'node:fs/promises';
import { constants } from 'node:fs';

const required=['public/index.html','public/styles.css','public/app.js','public/core.mjs','public/model-lab/index.html','public/model-lab/model-lab.js','public/model-lab/model-lab.css','public/data/model-lab.json','public/household/index.html','public/data/household/household_state.json','public/data/household/voter_state.json','public/data/household/source_health.json','scripts/build_forecast.py','scripts/validate_forecast.py','scripts/model_lab.py','scripts/household_state.py','wrangler.toml','docs/METHODOLOGY.md','docs/MODEL_LAB.md','docs/DATA_PROVENANCE.md','docs/MODEL_CHANGELOG.md','docs/SOURCE_STATUS.md','docs/HOUSEHOLD_VOTER_STATE.md'];
for(const file of required)await access(file,constants.R_OK);
const html=await readFile('public/index.html','utf8');
for(const marker of ['MIDTERM SIGNALS','Forecast','House','Senate','Races','Map','Polls','National environment','Candidates','Money','Campaign signals','Household & voter','Scenarios','History','Model Lab','Data','Methodology','About','GLOBAL SEARCH','Facts ≠ polls ≠ forecasts ≠ scenarios ≠ results'])if(!html.includes(marker))throw new Error(`Missing product marker: ${marker}`);
const app=(await Promise.all(['public/app-parts/1.jsfrag','public/app-parts/2.jsfrag','public/app-parts/3.jsfrag','public/app-parts/4.jsfrag','public/app-parts/5.jsfrag'].map(f=>readFile(f,'utf8')))).join('');
for(const marker of ['renderRace','renderRaces','renderPolls','renderScenarios','renderBuilder','renderHistory','renderData','renderMethodology','runScenario','source_health'])if(!app.includes(marker))throw new Error(`Missing application capability: ${marker}`);
const css=(await Promise.all(['public/styles-parts/1.css','public/styles-parts/2.css'].map(f=>readFile(f,'utf8')))).join('');
for(const marker of ['focus-visible','prefers-reduced-motion','.race-grid','.search-dialog','@media(max-width:760px)'])if(!css.includes(marker))throw new Error(`Missing accessibility/responsive marker: ${marker}`);
const labHtml=await readFile('public/model-lab/index.html','utf8');
for(const marker of ['MODEL LAB','Replay','Calibration','Failures','Anti-leakage architecture'])if(!labHtml.includes(marker))throw new Error(`Missing Model Lab marker: ${marker}`);
const lab=JSON.parse(await readFile('public/data/model-lab.json','utf8'));
if(lab.evaluation_only!==true||lab.retuning_allowed!==false)throw new Error('Model Lab evaluation boundary broken');
if(!Array.isArray(lab.checkpoints_days_to_election)||lab.checkpoints_days_to_election.join(',')!=='60,30,14,7,1')throw new Error('Model Lab checkpoints changed');
if(!lab.model_contract?.id||lab.model_contract?.state!=='verified')throw new Error('Model Lab production contract is not verified');
for(const cycle of lab.cycles||[]){
  if(cycle.state==='unavailable'&&cycle.checkpoints?.some(c=>c?.score?.state==='scored'))throw new Error(`Unavailable ${cycle.cycle} cycle contains fabricated score`);
}
const householdHtml=await readFile('public/household/index.html','utf8');
for(const marker of ['US Household','Voter State','FORECAST EFFECT: NONE','Midterm implications'])if(!householdHtml.includes(marker))throw new Error(`Missing household module marker: ${marker}`);
const household=JSON.parse(await readFile('public/data/household/household_state.json','utf8'));
if(household.forecast_effect!=='NONE'||household.governance?.forecast_effect!=='NONE'||household.governance?.numerical_forecast_input!==false)throw new Error('Household module model-safety boundary broken');
for(const [sensor,state] of Object.entries(household.states||{})){
  if(state&&typeof state==='object'&&state.forecast_effect!=='NONE')throw new Error(`Household state ${sensor} has non-NONE forecast effect`);
}
const voter=JSON.parse(await readFile('public/data/household/voter_state.json','utf8'));
if(voter.forecast_effect!=='NONE')throw new Error('Voter-state forecast effect must remain NONE');
try{
  const forecast=JSON.parse(await readFile('public/data/forecast.json','utf8'));
  if(forecast.election_date!=='2026-11-03')throw new Error('Unexpected election date');
  const house=(forecast.races||[]).filter(r=>r.race_type==='house');
  const senate=(forecast.races||[]).filter(r=>r.race_type==='senate');
  if(house.length!==435)throw new Error(`House universe incomplete: ${house.length}`);
  if(senate.length<33)throw new Error(`Senate universe incomplete: ${senate.length}`);
  if(forecast.schema_version==='1.0.0'){
    if(!forecast.summary?.joint_control)throw new Error('v1 joint control missing');
    if(!forecast.summary?.house?.distribution?.length)throw new Error('v1 House distribution missing');
    if(!forecast.source_health?.length)throw new Error('v1 source health missing');
    if(forecast.model_health?.historical_backtests?.['2018']?.state!=='unavailable')throw new Error('2018 validation state must not be fabricated');
  }
  console.log(`MIDTERM SIGNALS static checks passed (${forecast.schema_version} data; ${house.length} House + ${senate.length} Senate; Model Lab ${lab.summary?.state}; household sensor forecast effect NONE).`);
}catch(err){if(err?.code==='ENOENT')console.log(`Static product checks passed; production forecast refresh pending; Model Lab ${lab.summary?.state}; household sensor forecast effect NONE.`);else throw err}