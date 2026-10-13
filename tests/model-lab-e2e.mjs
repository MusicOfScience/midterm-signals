import { chromium } from 'playwright';

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:4173';
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1280,height:900}});
const consoleErrors=[];
page.on('console',msg=>{if(msg.type()==='error')consoleErrors.push(msg.text())});
page.on('pageerror',err=>consoleErrors.push(String(err)));

try{
  const response=await page.goto(`${BASE_URL}/model-lab/`,{waitUntil:'networkidle'});
  if(!response?.ok())throw new Error(`Model Lab HTTP ${response?.status()}`);
  await page.getByRole('heading',{name:'Can the probabilities survive contact with history?'}).waitFor();
  const state=(await page.locator('#labState').innerText()).trim();
  if(!state.includes('UNSCORED'))throw new Error(`Expected honest UNSCORED state, got: ${state}`);
  for(const year of ['2018','2022'])if(!(await page.locator('#cycleGrid').innerText()).includes(year))throw new Error(`Missing ${year} cycle card`);
  const body=await page.locator('body').innerText();
  if(!body.includes('No fake certainty.'))throw new Error('Missing unscored calibration explanation');
  if(body.match(/Brier\s+0\.\d+/))throw new Error('Fabricated Brier metric rendered while historical cycles are unavailable');
  const data=await page.evaluate(async()=>await (await fetch('/data/model-lab.json',{cache:'no-store'})).json());
  if(data.retuning_allowed!==false||data.evaluation_only!==true)throw new Error('Model Lab evaluation contract broken in browser');
  if(data.model_contract?.state!=='verified')throw new Error(`Production contract not verified: ${data.model_contract?.state}`);

  await page.setViewportSize({width:390,height:844});
  await page.reload({waitUntil:'networkidle'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+2);
  if(overflow)throw new Error('Model Lab has horizontal page overflow at phone viewport');
  if(consoleErrors.length)throw new Error(`Model Lab browser errors: ${consoleErrors.join(' | ')}`);
  console.log('MODEL LAB browser checks passed: desktop + mobile + honest unscored state.');
} finally {
  await browser.close();
}
