import { readFile, access } from 'node:fs/promises';
import { constants } from 'node:fs';

const required = [
  'public/index.html','public/styles.css','public/app.js','public/data/status.json','public/data/forecast.json','public/data/history/2026-10-12.json','wrangler.toml'
];
for (const file of required) await access(file, constants.R_OK);
const status = JSON.parse(await readFile('public/data/status.json', 'utf8'));
const forecast = JSON.parse(await readFile('public/data/forecast.json', 'utf8'));
if (status.election_date !== '2026-11-03') throw new Error('Unexpected election date');
if (status.production_forecast !== 'published') throw new Error('Production forecast is not published');
if (forecast.house.total_seats !== 435) throw new Error('House universe incomplete');
if (forecast.senate.contested_seats !== 35) throw new Error('Senate universe incomplete');
const html = await readFile('public/index.html', 'utf8');
for (const marker of ['MIDTERM SIGNALS','Observations ≠ forecasts ≠ scenarios ≠ results','PROVISIONAL PRODUCTION BASELINE']) {
  if (!html.includes(marker)) throw new Error(`Missing marker: ${marker}`);
}
console.log('MIDTERM SIGNALS static checks passed.');
