import { chromium } from 'playwright';
import axe from 'axe-core';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base=process.env.BASE_URL;if(!base)throw new Error('BASE_URL required');
const artifacts=process.env.TEST_ARTIFACT_DIR||'live-artifacts';await fs.mkdir(artifacts,{recursive:true});
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:1365,height:900}});
  await page.goto(base,{waitUntil:'networkidle',timeout:45000});
  await page.getByText('MIDTERM SIGNALS',{exact:true}).first().waitFor();
  assert.match(await page.locator('main').innerText(),/30-SECOND READ|State of the race/i);
  await page.getByRole('button',{name:/Search/i}).click();await page.locator('#globalSearch').fill('MI-07');await page.locator('.search-result').filter({hasText:'MI-07'}).first().click();await page.getByRole('heading',{name:'MI-07',exact:true}).waitFor();
  await page.goto(`${base}/?view=races`,{waitUntil:'networkidle'});await page.locator('#raceSort').waitFor();
  await page.addScriptTag({content:axe.source});const a11y=await page.evaluate(async()=>await axe.run(document));const severe=a11y.violations.filter(v=>['serious','critical'].includes(v.impact));assert.equal(severe.length,0,`live axe: ${severe.map(x=>x.id).join(', ')}`);
  await page.screenshot({path:`${artifacts}/live-races-desktop.png`,fullPage:true});
  const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});await mobile.goto(`${base}/?view=home`,{waitUntil:'networkidle'});assert((await mobile.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth))<=2);await mobile.screenshot({path:`${artifacts}/live-home-mobile.png`,fullPage:true});await mobile.close();
  console.log(`live smoke passed: ${base}`);
}finally{await browser.close()}
