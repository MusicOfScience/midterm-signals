import { chromium } from 'playwright';
import axe from 'axe-core';
import assert from 'node:assert/strict';

const base=process.env.BASE_URL||'http://127.0.0.1:4173';
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto(base,{waitUntil:'networkidle'});
  await page.getByText('MIDTERM SIGNALS',{exact:true}).first().waitFor();
  assert.match(await page.title(),/MIDTERM SIGNALS/);
  const text=await page.locator('main').innerText();
  assert.match(text,/HOUSE/i);
  assert.match(text,/SENATE/i);

  await page.getByRole('button',{name:/Search/i}).click();
  await page.locator('#globalSearch').fill('MI-07');
  const result=page.locator('.search-result').filter({hasText:'MI-07'}).first();
  await result.waitFor();
  await result.click();
  await page.getByRole('heading',{name:'MI-07',exact:true}).waitFor();
  assert.match(await page.locator('main').innerText(),/POLLING/i);

  await page.goto(`${base}/?view=races`,{waitUntil:'networkidle'});
  await page.locator('#raceQ').fill('MI-07');
  await page.waitForTimeout(100);
  assert.match(await page.locator('#filterSummary').innerText(),/1 of|races shown/i);
  assert.match(page.url(),/q=MI-07/);

  await page.goto(`${base}/?view=scenarios`,{waitUntil:'networkidle'});
  await page.locator('#scG').fill('2');
  await page.waitForTimeout(150);
  assert.match(await page.locator('main').innerText(),/SCENARIO, NOT OFFICIAL FORECAST/i);
  assert.match(page.url(),/gcb=2/);

  await page.goto(`${base}/?view=history`,{waitUntil:'networkidle'});
  assert.match(await page.locator('main').innerText(),/Snapshots, not rewritten memory/i);

  await page.goto(base,{waitUntil:'networkidle'});
  await page.addScriptTag({content:axe.source});
  const a11y=await page.evaluate(async()=>await axe.run(document,{rules:{'color-contrast':{enabled:false}}}));
  const severe=a11y.violations.filter(v=>['serious','critical'].includes(v.impact));
  assert.equal(severe.length,0,`serious/critical axe violations: ${severe.map(v=>v.id).join(', ')}`);

  const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  await mobile.goto(base,{waitUntil:'networkidle'});
  await mobile.locator('#navToggle').click();
  assert.equal(await mobile.locator('#navToggle').getAttribute('aria-expanded'),'true');
  const overflow=await mobile.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
  assert(overflow<=2,`mobile horizontal overflow ${overflow}px`);
  await mobile.close();

  const degraded=await browser.newPage({viewport:{width:1024,height:768}});
  await degraded.route('**/data/source-status.json',route=>route.fulfill({status:503,body:'unavailable'}));
  await degraded.goto(base,{waitUntil:'networkidle'});
  assert.match(await degraded.locator('main').innerText(),/MIDTERM|HOUSE|SENATE/i);
  await degraded.close();

  console.log('browser/mobile/accessibility tests passed');
} finally {
  await browser.close();
}
