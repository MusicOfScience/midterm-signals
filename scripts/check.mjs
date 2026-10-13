import { readFile, access } from 'node:fs/promises';
import { constants } from 'node:fs';

const required=['public/index.html','public/styles.css','public/app.js','public/core.mjs','scripts/build_forecast.py','scripts/validate_forecast.py','wrangler.toml','docs/METHODOLOGY.md','docs/DATA_PROVENANCE.md','docs/MODEL_CHANGELOG.md','docs/SOURCE_STATUS.md'];
for(const file of required)await access(file,constants.R_OK);
const html=await readFile('public/index.html','utf8');
for(const marker of ['MIDTERM SIGNALS','Forecast','House','Senate','Races','Map','Polls','National environment','Candidates','Money','Campaign signals','Scenarios','History','Data','Methodology','About','GLOBAL SEARCH','Facts ≠ polls ≠ forecasts ≠ scenarios ≠ results'])if(!html.includes(marker))throw new Error(`Missing product marker: ${marker}`);
const app=(await Promise.all(['public/app-parts/1.jsfrag','public/app-parts/2.jsfrag','public/app-parts/3.jsfrag','public/app-parts/4.jsfrag','public/app-parts/5.jsfrag'].map(f=>readFile(f,'utf8')))).join('');
for(const marker of ['renderRace','renderRaces','renderPolls','renderScenarios','renderBuilder','renderHistory','renderData','renderMethodology','runScenario','source_health'])if(!app.includes(marker))throw new Error(`Missing application capability: ${marker}`);
const css=(await Promise.all(['public/styles-parts/1.css','public/styles-parts/2.css'].map(f=>readFile(f,'utf8')))).join('');
for(const marker of ['focus-visible','prefers-reduced-motion','.race-grid','.search-dialog','@media(max-width:760px)'])if(!css.includes(marker))throw new Error(`Missing accessibility/responsive marker: ${marker}`);
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
  console.log(`MIDTERM SIGNALS static checks passed (${forecast.schema_version} data; ${house.length} House + ${senate.length} Senate).`);
}catch(err){if(err?.code==='ENOENT')console.log('Static product checks passed; production data refresh pending.');else throw err}
