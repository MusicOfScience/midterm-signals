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
  if(!state.includes('PARTIAL')||!state.includes('1/2'))throw new Error(`Expected partial 1/2 scored state, got: ${state}`);

  const cycleText=await page.locator('#cycleGrid').innerText();
  for(const year of ['2018','2022'])if(!cycleText.includes(year))throw new Error(`Missing ${year} cycle card`);

  const data=await page.evaluate(async()=>await (await fetch('/data/model-lab.json',{cache:'no-store'})).json());
  if(data.retuning_allowed!==false||data.evaluation_only!==true)throw new Error('Model Lab evaluation contract broken in browser');
  if(data.model_contract?.state!=='verified')throw new Error(`Production contract not verified: ${data.model_contract?.state}`);
  if(data.summary?.state!=='partial'||data.summary?.scored_cycles!==1||data.summary?.requested_cycles!==2){
    throw new Error(`Unexpected Model Lab summary: ${JSON.stringify(data.summary)}`);
  }

  const c2018=data.cycles?.find(c=>c.cycle===2018);
  const c2022=data.cycles?.find(c=>c.cycle===2022);
  if(c2018?.state!=='scored')throw new Error(`2018 should be scored, got: ${c2018?.state}`);
  if(c2018?.checkpoints?.length!==5||c2018.checkpoints.some(c=>c.state!=='scored'||c.score?.state!=='scored')){
    throw new Error('2018 does not expose five fully scored checkpoints');
  }
  if(c2022?.state==='scored')throw new Error('2022 must remain unscored until its corpus is admitted');

  const body=await page.locator('body').innerText();
  if(!body.match(/Brier\s+0\.\d+/))throw new Error('Scored 2018 Brier metric is not rendered');

  await page.setViewportSize({width:390,height:844});
  await page.reload({waitUntil:'networkidle'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+2);
  if(overflow)throw new Error('Model Lab has horizontal page overflow at phone viewport');
  if(consoleErrors.length)throw new Error(`Model Lab browser errors: ${consoleErrors.join(' | ')}`);
  console.log('MODEL LAB browser checks passed: desktop + mobile + partial 2018-scored / 2022-unscored state.');
} finally {
  await browser.close();
}
