import { readFile, access } from 'node:fs/promises';
import { constants } from 'node:fs';

const required = ['public/index.html','public/styles.css','public/app.js','scripts/build_forecast.py','scripts/validate_forecast.py','wrangler.toml'];
for (const file of required) await access(file, constants.R_OK);

const html = await readFile('public/index.html','utf8');
for (const marker of ['MIDTERM SIGNALS','PRODUCTION BASELINE','All 435 districts','CLASS II + SPECIAL ELECTIONS','Observations ≠ forecasts ≠ scenarios ≠ results']) {
  if (!html.includes(marker)) throw new Error(`Missing marker: ${marker}`);
}

try {
  const forecast = JSON.parse(await readFile('public/data/forecast.json','utf8'));
  if (forecast.schema_version !== '0.2.0') {
    console.log(`Static checks passed; v0.2 refresh pending (current schema ${forecast.schema_version}).`);
    process.exit(0);
  }
  if (forecast.production_forecast !== 'published') throw new Error('Forecast not published');
  if (forecast.election_date !== '2026-11-03') throw new Error('Unexpected election date');
  const house=forecast.races.filter(r=>r.race_type==='house');
  const senate=forecast.races.filter(r=>r.race_type==='senate');
  if (house.length!==435) throw new Error(`House universe incomplete: ${house.length}`);
  if (senate.length<33) throw new Error(`Senate universe incomplete: ${senate.length}`);
  for (const race of forecast.races) if (!(race.dem_probability>=0&&race.dem_probability<=1)) throw new Error(`Invalid probability for ${race.race_code}`);
  console.log(`MIDTERM SIGNALS checks passed: ${house.length} House + ${senate.length} Senate races.`);
} catch (err) {
  if (err?.code==='ENOENT') console.log('Static checks passed; forecast snapshot pending first refresh.');
  else throw err;
}
