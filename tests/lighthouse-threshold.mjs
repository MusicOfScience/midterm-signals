import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const path=process.argv[2]||'test-artifacts/lighthouse.json';
const report=JSON.parse(await fs.readFile(path,'utf8'));
const categories=report.categories||{};
const scores={
  performance:categories.performance?.score??0,
  accessibility:categories.accessibility?.score??0,
  'best-practices':categories['best-practices']?.score??0,
  seo:categories.seo?.score??0,
};
console.log('Lighthouse scores',Object.fromEntries(Object.entries(scores).map(([k,v])=>[k,Math.round(v*100)])));
assert(scores.performance>=0.85,`Performance ${Math.round(scores.performance*100)} < 85 floor`);
assert(scores.accessibility>=0.95,`Accessibility ${Math.round(scores.accessibility*100)} < 95 target`);
assert(scores['best-practices']>=0.95,`Best Practices ${Math.round(scores['best-practices']*100)} < 95 target`);
assert(scores.seo>=0.95,`SEO ${Math.round(scores.seo*100)} < 95 target`);
