import { readFile, access } from 'node:fs/promises';
import { constants } from 'node:fs';

const required = [
  'public/index.html',
  'public/styles.css',
  'public/app.js',
  'public/data/status.json',
  'wrangler.toml'
];
for (const file of required) await access(file, constants.R_OK);

const status = JSON.parse(await readFile('public/data/status.json', 'utf8'));
if (status.election_date !== '2026-11-03') throw new Error('Unexpected election date');
if (!['withheld', 'published'].includes(status.production_forecast)) throw new Error('Invalid publication state');

const html = await readFile('public/index.html', 'utf8');
for (const marker of ['MIDTERM SIGNALS', 'Observations ≠ forecasts ≠ scenarios ≠ results']) {
  if (!html.includes(marker)) throw new Error(`Missing marker: ${marker}`);
}
console.log('MIDTERM SIGNALS static checks passed.');
