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

  const data=await page.evaluate(async()=>await (await fetch('/data/model-lab.json',{cache:'no-store'})).json());
  if(data.retuning_allowed!==false||data.evaluation_only!==true)throw new Error('Model Lab evaluation contract broken in browser');
  if(data.model_contract?.state!=='verified')throw new Error(`Production contract not verified: ${data.model_contract?.state}`);

  const requested=Number(data.summary?.requested_cycles ?? 0);
  const scored=Number(data.summary?.scored_cycles ?? 0);
  const expectedState=scored===requested&&requested>0?'scored':scored>0?'partial':'unscored';
  if(data.summary?.state!==expectedState){
    throw new Error(`Model Lab summary state/count mismatch: ${JSON.stringify(data.summary)}`);
  }
  // This branch admits 2022 alongside the already-admitted 2018 corpus.
  if(requested!==2||scored!==2||expectedState!=='scored'){
    throw new Error(`Expected both historical cycles scored, got: ${JSON.stringify(data.summary)}`);
  }

  const state=(await page.locator('#labState').innerText()).trim().toUpperCase();
  const expectedLabel=`${scored}/${requested}`;
  if(!state.includes(expectedState.toUpperCase())||!state.includes(expectedLabel)){
    throw new Error(`Rendered Model Lab state diverges from data summary ${expectedState} ${expectedLabel}: ${state}`);
  }

  const cycleText=await page.locator('#cycleGrid').innerText();
  for(const year of ['2018','2022'])if(!cycleText.includes(year))throw new Error(`Missing ${year} cycle card`);

  for(const year of [2018,2022]){
    const cycle=data.cycles?.find(c=>c.cycle===year);
    if(cycle?.state!=='scored')throw new Error(`${year} should be scored, got: ${cycle?.state}`);
    if(cycle?.checkpoints?.length!==5||cycle.checkpoints.some(c=>c.state!=='scored'||c.score?.state!=='scored')){
      throw new Error(`${year} does not expose five fully scored checkpoints`);
    }
  }

  const c2022=data.cycles?.find(c=>c.cycle===2022);
  const n2022=[...new Set((c2022?.checkpoints||[]).map(c=>c.score?.n))];
  if(n2022.length!==1||n2022[0]!==416)throw new Error(`2022 fixed replay sample drifted: ${JSON.stringify(n2022)}`);

  const body=await page.locator('body').innerText();
  if(!body.match(/Brier\s+0\.\d+/))throw new Error('Scored historical Brier metric is not rendered');

  await page.setViewportSize({width:390,height:844});
  await page.reload({waitUntil:'networkidle'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+2);
  if(overflow)throw new Error('Model Lab has horizontal page overflow at phone viewport');
  if(consoleErrors.length)throw new Error(`Model Lab browser errors: ${consoleErrors.join(' | ')}`);
  console.log(`MODEL LAB browser checks passed: desktop + mobile + ${scored}/${requested} historical cycles scored; 2022 n=416.`);
} finally {
  await browser.close();
}
