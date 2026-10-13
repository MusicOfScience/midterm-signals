import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const base = process.env.BASE_URL || 'http://127.0.0.1:4173';
const browser = await chromium.launch({ headless: true });

async function json(path) {
  const response = await fetch(new URL(path, base));
  assert.equal(response.ok, true, `${path} should return HTTP 2xx`);
  return response.json();
}

function assertProbability(value, label) {
  assert.equal(Number.isFinite(value), true, `${label} must be finite`);
  assert(value >= 0 && value <= 1, `${label} must be in [0,1]`);
}

try {
  // Numerical/publication contract: a production forecast can only be exposed
  // when the complete federal race roster is accounted for and the run itself
  // reports that validation passed.
  const [status, forecast, report, sourceStatus, signals, results, external, fec] = await Promise.all([
    json('/data/status.json'),
    json('/data/forecast.json'),
    json('/data/run-report.json'),
    json('/data/source-status.json'),
    json('/data/signals.json'),
    json('/data/results.json'),
    json('/data/external-forecasters.json'),
    json('/data/fec.json'),
  ]);

  assert.equal(status.production_forecast, 'published');
  assert.equal(status.house_all_435_accounted_for, true);
  assert.equal(status.qualitative_news_changes_probabilities, false);
  assert(status.simulations >= 10_000, 'production simulation count unexpectedly small');
  assert.equal(report.checks, 'passed');
  assert.deepEqual(report.warnings, []);
  assert.equal(report.house_races, 435);
  assert.equal(report.senate_contests, status.senate_contests_accounted_for);
  assert.equal(report.enrichment?.numerical_forecast_unchanged, true, 'context enrichment must not change numerical probabilities');

  assert(Array.isArray(forecast.races), 'forecast.races must be an array');
  const house = forecast.races.filter(r => r.race_type === 'house');
  const senate = forecast.races.filter(r => r.race_type === 'senate');
  assert.equal(house.length, 435, 'House forecast must account for all 435 seats');
  assert.equal(senate.length, status.senate_contests_accounted_for, 'Senate roster mismatch');
  const codes = new Set();
  for (const race of forecast.races) {
    assert(race.race_code, 'every modeled race needs a race_code');
    assert.equal(codes.has(race.race_code), false, `duplicate race_code ${race.race_code}`);
    codes.add(race.race_code);
    assertProbability(race.dem_probability, `${race.race_code}.dem_probability`);
  }

  const sourceMap = new Map((sourceStatus.sources || []).map(s => [s.id, s]));
  for (const id of ['upstream_input_mirror', 'generic_ballot', 'race_polls']) {
    assert.equal(sourceMap.get(id)?.state, 'current', `${id} is a required current numerical source`);
  }

  // Third-party forecasts must always have an explicit state. Missing access is
  // never silently converted to a neutral rating or synthetic probability.
  const allowedExternalStates = new Set(['current', 'stale', 'unavailable', 'restricted', 'manual']);
  for (const id of ['cook', 'inside_elections', 'crystal_ball', 'silver_bulletin', 'ddhq']) {
    const state = sourceMap.get(id)?.state;
    assert(allowedExternalStates.has(state), `${id} must be explicit, never silently neutral; got ${state}`);
  }
  assert.equal(sourceMap.get('cook')?.state, 'restricted', 'Cook must remain an explicit licensed/access boundary unless a permitted feed is configured');
  assert.equal(sourceMap.get('silver_bulletin')?.state, 'restricted', 'Silver Bulletin must remain an explicit subscriber/licensing boundary');
  assert(['current','stale'].includes(sourceMap.get('inside_elections')?.state), 'Inside Elections public ratings adapter should be current or last-known-good stale');
  assert(['manual','current','stale'].includes(sourceMap.get('crystal_ball')?.state), 'Crystal Ball must be explicitly manual or a real configured feed');
  assert(['manual','current','stale'].includes(sourceMap.get('ddhq')?.state), 'DDHQ must be explicitly manual or a real configured feed');
  assert((external.inside_elections?.ratings_count || 0) > 0, 'Inside Elections configured source must contain native race ratings');
  assert.equal(external.model_effect, 'NONE', 'external forecasters may not silently alter MIDTERM SIGNALS probabilities');

  // Campaign Signals is now a real structured event layer. Every item must
  // state its model effect; contextual items must default to NONE while poll
  // observations may say POLL INPUT only because those polls are already
  // consumed by the separately documented quantitative poll adapter.
  assert.equal(Array.isArray(signals.signals), true);
  assert(signals.signals.length > 0, 'campaign signals should contain current structured records');
  const allowedEffects = new Set(['NONE', 'POLL INPUT']);
  for (const signal of signals.signals) {
    assert(signal.id, 'every signal requires a stable id');
    assert(signal.date, `signal ${signal.id} requires a date`);
    assert(signal.category, `signal ${signal.id} requires a category`);
    assert(signal.description, `signal ${signal.id} requires a factual description`);
    assert(allowedEffects.has(signal.model_effect || 'NONE'), `unexpected model effect on ${signal.id}`);
    if (signal.category !== 'POLL') assert.equal(signal.model_effect || 'NONE', 'NONE', `${signal.category} must not affect probabilities`);
    if (signal.category === 'RATING CHANGE') assert(signal.source, `${signal.id} rating change requires source provenance`);
    if (signal.category === 'FUNDRAISING') assert.match(String(signal.source || ''), /^https:\/\/www\.fec\.gov\//, `${signal.id} fundraising signal must cite FEC`);
  }
  assert(signals.signals.some(s => s.category === 'POLL'), 'campaign signals should include structured poll observations');
  assert((fec.matched_candidates || 0) > 0, 'official FEC adapter should match current production candidates');
  assert(['current','stale'].includes(fec.state), `FEC adapter must be current/stale when records are published, got ${fec.state}`);

  assert.equal(results.phase, 'pre-election');
  assert.equal(results.state, 'unavailable');
  assert.deepEqual(results.races, []);

  // Performance architecture invariant: the build-time-rendered home page must
  // remain useful before the heavy analytical bundle is requested.
  const requested = [];
  const home = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  home.on('request', request => requested.push(new URL(request.url()).pathname));
  await home.goto(base, { waitUntil: 'networkidle' });
  const homeText = await home.locator('main').innerText();
  assert.match(homeText, /30-SECOND READ/i);
  assert.match(homeText, /HOUSE/i);
  assert.match(homeText, /SENATE/i);
  assert.doesNotMatch(homeText, /External feeds not configured/i, 'production home page must not advertise the removed external-feed placeholder');
  assert.doesNotMatch(homeText, /0 structured signals/i, 'production home page must not advertise the removed campaign-signal placeholder');
  assert.equal(requested.includes('/app.bundle.mjs'), false, 'home must not eagerly load the full analytical app');
  assert.equal(requested.includes('/data/bootstrap.json'), false, 'home must not eagerly load bootstrap data');
  assert.equal(requested.includes('/data/forecast.json'), false, 'home must not eagerly load the full forecast JSON');

  // Keyboard-only search must hydrate on demand, focus correctly and close.
  // The full search module deliberately focuses after showModal() on a short
  // timer, so assert the eventual focus contract rather than racing that timer.
  await home.keyboard.press('/');
  await home.locator('#searchDialog[open]').waitFor({ state: 'visible', timeout: 15_000 });
  await home.waitForFunction(() => document.activeElement?.id === 'globalSearch', null, { timeout: 1_500 });
  await home.keyboard.press('Escape');
  await home.locator('#searchDialog').waitFor({ state: 'hidden' });
  await home.close();

  // The publication must still communicate its core result with JavaScript
  // entirely disabled. This is both resilience and progressive enhancement.
  const noJsContext = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1024, height: 768 } });
  const noJs = await noJsContext.newPage();
  await noJs.goto(base, { waitUntil: 'domcontentloaded' });
  const noJsText = await noJs.locator('main').innerText();
  assert.match(noJsText, /30-SECOND READ/i);
  assert.match(noJsText, /HOUSE/i);
  assert.match(noJsText, /SENATE/i);
  await noJsContext.close();

  // Hostile/malformed query strings must not execute markup or take down the
  // analytical shell. Capture browser-level errors while probing the route.
  const hostile = await browser.newPage({ viewport: { width: 1024, height: 768 } });
  const browserErrors = [];
  hostile.on('pageerror', error => browserErrors.push(String(error)));
  hostile.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
  await hostile.goto(`${base}/?view=races&q=${encodeURIComponent('\"><img data-adversarial src=x onerror=globalThis.__MIDTERM_XSS__=1>')}`, { waitUntil: 'networkidle' });
  await hostile.locator('#raceQ').waitFor({ state: 'visible', timeout: 15_000 });
  await hostile.locator('#raceQ').fill('\"><img data-adversarial src=x onerror=globalThis.__MIDTERM_XSS__=1>');
  await hostile.waitForTimeout(150);
  assert.equal(await hostile.evaluate(() => Boolean(globalThis.__MIDTERM_XSS__)), false, 'query string executed script');
  assert.equal(await hostile.locator('img[data-adversarial]').count(), 0, 'query string became executable markup');
  assert.equal(browserErrors.length, 0, `browser errors under hostile query: ${browserErrors.join(' | ')}`);
  await hostile.close();

  // Narrow-phone product check. 320 CSS pixels catches regressions hidden by
  // the more forgiving 390px mobile smoke test.
  const narrow = await browser.newPage({ viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true });
  await narrow.goto(base, { waitUntil: 'networkidle' });
  let overflow = await narrow.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 2, `320px home horizontal overflow ${overflow}px`);
  await narrow.goto(`${base}/?view=races`, { waitUntil: 'networkidle' });
  await narrow.locator('#raceSort').waitFor({ state: 'visible', timeout: 15_000 });
  overflow = await narrow.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 2, `320px Race Explorer horizontal overflow ${overflow}px`);
  await narrow.close();

  console.log('adversarial production-readiness checks passed');
} finally {
  await browser.close();
}