import {chromium} from "playwright";
import axe from "axe-core";
import assert from "node:assert/strict";

const base=process.env.BASE_URL||"http://127.0.0.1:4173";
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:390,height:844},acceptDownloads:true});
  // Exercising the no-results/no-network fallback is intentional, not a fixture of votes.
  await page.route("https://thepeoplestally.com/**",route=>route.abort());
  await page.route("https://openamerica.io/**",route=>route.abort());
  await page.route("**/data/observed-results.json*",r=>r.fulfill({
  status:200,contentType:"application/json",body:JSON.stringify({
    schema_version:1,source:"civicAPI",fetched_at:null,source_updated_at:null,
    state:"awaiting_results",races:[]})
 }));
 await page.goto(base+"/results/",{waitUntil:"domcontentloaded"});
  await page.waitForFunction(()=>document.querySelector("#mReporting")?.textContent?.includes(" / 470"),null,{timeout:30000});
  assert.match(await page.title(),/Results Desk/);
  assert.match(await page.locator("#feedStatus").innerText(),/Awaiting verified vote counts/i);
  assert.match(await page.locator("#mHouse").innerText(),/0 D/);
  assert.match(await page.locator("#mSenate").innerText(),/0 D/);
  assert.equal(await page.locator("#raceRows tr").count(),470);
  assert.match(await page.locator("#raceRows tr").first().innerText(),/No votes reported/);
  await page.locator("#chamber").selectOption("senate");
  await page.waitForFunction(()=>document.querySelector("#rowCount")?.textContent?.includes("35 of 470"));
  assert.equal(await page.locator("#raceRows tr").count(),35);
  await page.locator("#chamber").selectOption("all");
  await page.locator("#state").selectOption("PA");
  const stateN=await page.locator("#raceRows tr").count();
  assert(stateN>1&&stateN<30,"Pennsylvania filter must select proper district+Senate subset");
  await page.locator("#state").selectOption("all");
  await page.locator("#reported").check();
  assert.match(await page.locator("#raceRows").innerText(),/No races meet these filters/);
  await page.locator("#reported").uncheck();
  const download=page.waitForEvent("download");
  await page.locator("#export").click();
  const file=await download;
  assert.match(file.suggestedFilename(),/observed-2026\.csv/);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  assert(overflow<4,"Results Desk mobile layout must not overflow document viewport");
  await page.addScriptTag({content:axe.source});
  const result=await page.evaluate(async()=>axe.run(document));
  const severe=result.violations.filter(v=>["serious","critical"].includes(v.impact));
  assert.equal(severe.length,0,"Results Desk has serious accessibility issues: "+JSON.stringify(severe.map(v=>({id:v.id,nodes:v.nodes.slice(0,5).map(n=>({target:n.target,html:n.html}))}))));
  console.log("Results Desk mobile browser, fallback, filters, CSV and accessibility tests passed");
} finally {
  await browser.close();
}
