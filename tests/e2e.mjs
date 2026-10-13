import { chromium } from 'playwright';
import axe from 'axe-core';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const base=process.env.BASE_URL||'http://127.0.0.1:4173';
const artifacts=process.env.TEST_ARTIFACT_DIR||'test-artifacts';
await fs.mkdir(artifacts,{recursive:true});
const browser=await chromium.launch({headless:true});

async function waitEnhanced(page,selector){await page.locator(selector).waitFor({state:'visible',timeout:15000})}
async function seriousAxe(page,label){
  await page.addScriptTag({content:axe.source});
  const report=await page.evaluate(async()=>await axe.run(document));
  const severe=report.violations.filter(v=>['serious','critical'].includes(v.impact));
  const detail=severe.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.slice(0,6).map(n=>({target:n.target,html:n.html,failureSummary:n.failureSummary}))}));
  assert.equal(severe.length,0,`${label} serious/critical axe violations: ${JSON.stringify(detail)}`);
}

try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto(base,{waitUntil:'networkidle'});
  await page.getByText('MIDTERM SIGNALS',{exact:true}).first().waitFor();
  assert.match(await page.title(),/MIDTERM SIGNALS/);
  let text=await page.locator('main').innerText();
  assert.match(text,/HOUSE/i);assert.match(text,/SENATE/i);assert.match(text,/30-SECOND READ/i);
  assert.doesNotMatch(text,/External feeds not configured/i,'homepage must not regress to the v1.0 external-feed placeholder');
  assert.doesNotMatch(text,/0 structured signals/i,'homepage must not regress to the empty campaign-signals placeholder');
  await page.screenshot({path:`${artifacts}/home-desktop.png`,fullPage:true});
  await seriousAxe(page,'desktop home');

  await page.getByRole('button',{name:/Search/i}).click();
  await page.locator('#globalSearch').fill('MI-07');
  const result=page.locator('.search-result').filter({hasText:'MI-07'}).first();
  await result.waitFor();await result.click();
  await page.getByRole('heading',{name:'MI-07',exact:true}).waitFor();
  text=await page.locator('main').innerText();
  assert.match(text,/POLLING/i);assert.match(text,/SOURCES & PROVENANCE/i);assert.match(text,/EXTERNAL FORECASTERS/i);
  assert.match(text,/Inside Elections/i,'race pages should expose the native external-rating layer');

  await page.goto(`${base}/?view=races`,{waitUntil:'networkidle'});
  await waitEnhanced(page,'#raceSort');
  await page.locator('#raceQ').fill('MI-07');
  await page.waitForTimeout(120);
  assert.match(await page.locator('#filterSummary').innerText(),/1 of|races shown/i);
  assert.match(page.url(),/q=MI-07/);
  assert.match(await page.locator('#raceResults').innerText(),/POLL AVG/i);
  await page.locator('#raceQ').fill('');
  await page.locator('#raceSort').selectOption('movement');
  assert.match(page.url(),/sort=movement/);
  const expertButton=page.getByRole('button',{name:/MODEL \/ EXPERT DISAGREEMENT/i});
  if(await expertButton.count()) assert.equal(await expertButton.isDisabled(),false,'expert-disagreement preset should be usable when native external ratings are present');

  await page.goto(`${base}/?view=map&chamber=house`,{waitUntil:'networkidle'});
  await waitEnhanced(page,'#mapPeriod');
  await page.locator('#mapLayer').selectOption('margin');
  await page.waitForTimeout(100);
  assert.match(await page.locator('#mapGrid').innerText(),/[DR] \+\d|D \+|R \+/);
  await page.locator('#mapLayer').selectOption('movement');
  await page.locator('#mapPeriod').selectOption('7');
  assert.match(page.url(),/period=7/);

  await page.goto(`${base}/?view=polls`,{waitUntil:'networkidle'});
  await waitEnhanced(page,'#pollDatabase');
  const pollSummary=await page.locator('#pollDbSummary').innerText();
  assert.match(pollSummary,/observations shown/i);
  assert((await page.locator('.poll-card').count())>0,'poll database should contain observations');

  const senateCode=await page.evaluate(async()=>{const d=await fetch('/data/forecast.json').then(r=>r.json());const r=d.races.find(x=>x.race_type==='senate'&&x.dem_probability>.08&&x.dem_probability<.92)||d.races.find(x=>x.race_type==='senate');return r?.race_code});
  assert(senateCode,'expected a Senate race');
  await page.goto(`${base}/?race=${encodeURIComponent(senateCode)}`,{waitUntil:'networkidle'});
  text=await page.locator('main').innerText();
  assert.match(text,/POLLING/i);assert.match(text,/Inside Elections/i);

  // Campaign Signals is now a real structured event layer, not an empty shell.
  await page.goto(`${base}/?view=signals`,{waitUntil:'networkidle'});
  await waitEnhanced(page,'#signalCategory');
  text=await page.locator('main').innerText();
  assert.match(text,/structured signals/i);assert.match(text,/POLL/i);assert.match(text,/MODEL EFFECT/i);
  const signalCount=await page.evaluate(async()=>{const d=await fetch('/data/signals.json').then(r=>r.json());return d.signals?.length||0});
  assert(signalCount>0,'campaign signal feed should contain structured records');
  const categories=await page.locator('#signalCategory option').allTextContents();
  assert(categories.includes('POLL'),'signals should include structured poll observations');
  if(categories.includes('RATING CHANGE')){
    await page.locator('#signalCategory').selectOption({label:'RATING CHANGE'});
    assert.match(await page.locator('#signalResults').innerText(),/Inside Elections/i);
  }
  await seriousAxe(page,'campaign signals');

  // Money uses official FEC current-campaign summaries and keeps reporting dates visible.
  await page.goto(`${base}/?view=money`,{waitUntil:'networkidle'});
  text=await page.locator('main').innerText();
  assert.match(text,/Federal Election Commission|FEC ADAPTER/i);
  assert.match(text,/reporting|coverage|through/i);
  const fecState=await page.evaluate(async()=>{const d=await fetch('/data/fec.json').then(r=>r.json());return {state:d.state,count:d.matched_candidates||0}});
  assert(['current','stale'].includes(fecState.state),`FEC adapter should be current/stale, got ${fecState.state}`);
  assert(fecState.count>0,'FEC adapter should match at least one production candidate');

  await page.goto(`${base}/?view=scenarios`,{waitUntil:'networkidle'});
  await waitEnhanced(page,'#scenarioAdvanced');
  await page.locator('#scG').fill('2');
  await page.locator('#scTurnout').fill('1');
  const override=page.locator('#scOverrideRace');
  const values=await override.locator('option').evaluateAll(opts=>opts.map(o=>o.value).filter(Boolean));
  if(values.length){await override.selectOption(values[0]);await page.locator('#scOverrideChoice').selectOption('D')}
  await page.waitForTimeout(180);
  text=await page.locator('main').innerText();
  assert.match(text,/SCENARIO, NOT OFFICIAL FORECAST/i);
  assert.match(page.url(),/gcb=2/);assert.match(page.url(),/turnout=1/);
  if(values.length)assert.match(page.url(),/overrideRace=/);

  await page.goto(`${base}/?view=builder`,{waitUntil:'networkidle'});
  await page.locator('#modelFav').waitFor();await page.locator('#modelFav').click();
  assert.match(await page.locator('#scoreStrip').innerText(),/House/i);assert.match(await page.locator('main').innerText(),/NOT OFFICIAL FORECAST/i);

  await page.goto(`${base}/?view=history`,{waitUntil:'networkidle'});
  assert.match(await page.locator('main').innerText(),/Snapshots, not rewritten memory/i);
  const workbench=page.locator('#historyWorkbench');
  if(await workbench.count()){
    assert(await page.locator('#historySlider').count()===1);
    if(Number(await page.locator('#historySlider').getAttribute('max'))>0){await page.locator('#historySlider').fill('1');await page.locator('#historyCompare').selectOption('first')}
  } else {
    assert((await page.locator('.history-list').count())===1,'history must remain usable before compact index refresh');
  }

  await page.goto(`${base}/?view=forecast`,{waitUntil:'networkidle'});
  await waitEnhanced(page,'#forecasterWorkbench');
  text=await page.locator('#forecasterWorkbench').innerText();
  assert.match(text,/Inside Elections/i);assert.match(text,/comparable races|native rating/i);

  await page.goto(base,{waitUntil:'networkidle'});await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(()=>document.activeElement?.classList.contains('skip')),true,'skip link should be first focus target');

  const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  await mobile.goto(base,{waitUntil:'networkidle'});
  await mobile.locator('#navToggle').click();
  assert.equal(await mobile.locator('#navToggle').getAttribute('aria-expanded'),'true');
  await mobile.keyboard.press('Escape');
  assert.equal(await mobile.locator('#navToggle').getAttribute('aria-expanded'),'false');
  let overflow=await mobile.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
  assert(overflow<=2,`mobile home horizontal overflow ${overflow}px`);
  await mobile.goto(`${base}/?view=races`,{waitUntil:'networkidle'});await waitEnhanced(mobile,'#raceSort');
  overflow=await mobile.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
  assert(overflow<=2,`mobile Race Explorer horizontal overflow ${overflow}px`);
  await mobile.screenshot({path:`${artifacts}/race-explorer-mobile.png`,fullPage:true});
  await seriousAxe(mobile,'mobile Race Explorer');
  await mobile.goto(`${base}/?view=signals`,{waitUntil:'networkidle'});await waitEnhanced(mobile,'#signalCategory');
  overflow=await mobile.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
  assert(overflow<=2,`mobile Campaign Signals horizontal overflow ${overflow}px`);
  await mobile.close();

  const degraded=await browser.newPage({viewport:{width:1024,height:768}});
  await degraded.route('**/data/source-status.json',route=>route.fulfill({status:503,body:'unavailable'}));
  await degraded.goto(base,{waitUntil:'networkidle'});
  assert.match(await degraded.locator('main').innerText(),/MIDTERM|HOUSE|SENATE/i);
  await degraded.close();

  console.log('browser/mobile/accessibility/exploration tests passed');
} finally {await browser.close()}
