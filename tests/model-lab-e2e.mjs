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
  if(data.schema_version!=='1.1.0')throw new Error(`Unexpected Model Lab schema ${data.schema_version}`);
  if(data.diagnostic_contract?.movement_threshold!==0.10||data.diagnostic_contract?.confident_miss_threshold!==0.80){
    throw new Error('Fixed diagnostic thresholds drifted');
  }
  if(data.diagnostic_contract?.paired_polling_component_test?.model_effect!=='NONE'){
    throw new Error('Paired polling diagnostic must be evaluation-only');
  }

  const requested=Number(data.summary?.requested_cycles ?? 0);
  const scored=Number(data.summary?.scored_cycles ?? 0);
  const expectedState=scored===requested&&requested>0?'scored':scored>0?'partial':'unscored';
  if(data.summary?.state!==expectedState){
    throw new Error(`Model Lab summary state/count mismatch: ${JSON.stringify(data.summary)}`);
  }
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
    if(cycle.movement?.state!=='scored')throw new Error(`${year} movement diagnostics missing`);
    if((cycle.movement?.polling_partitions||[]).length!==4)throw new Error(`${year} polling movement partitions missing`);
    for(const cp of cycle.checkpoints){
      if((cp.score?.competitive_bands||[]).length!==5)throw new Error(`${year} ${cp.days_to_election}d competitive diagnostics missing`);
      const pollN=Number(cp.score?.polling?.polled?.n||0)+Number(cp.score?.polling?.unpolled?.n||0);
      if(pollN!==cp.score?.n)throw new Error(`${year} ${cp.days_to_election}d polling partition drift`);
      if(cp.score?.polling?.paired_component_test?.state!=='scored')throw new Error(`${year} ${cp.days_to_election}d paired polling diagnostic missing`);
      const calN=(cp.score?.calibration||[]).reduce((sum,b)=>sum+Number(b.count||0),0);
      if(calN!==cp.score?.n)throw new Error(`${year} ${cp.days_to_election}d calibration denominator drift`);
    }
  }

  const c2022=data.cycles?.find(c=>c.cycle===2022);
  const n2022=[...new Set((c2022?.checkpoints||[]).map(c=>c.score?.n))];
  if(n2022.length!==1||n2022[0]!==416)throw new Error(`2022 fixed replay sample drifted: ${JSON.stringify(n2022)}`);
  if(c2022?.chamber_scope?.senate?.state!=='unavailable')throw new Error('2022 Senate must be explicitly unavailable');

  if(await page.locator('#competitivePanel').getByText('45-55',{exact:false}).count()===0)throw new Error('Competitive diagnostics not rendered');
  if(await page.locator('#pollingPanel').getByText('Not a causal A/B test.',{exact:false}).count()===0)throw new Error('Polling caveat not rendered');
  await page.locator('#pairedPollingPanel').getByText('Same-race component test',{exact:false}).waitFor();
  await page.locator('#movementPollingPanel').getByText('Movement by polling status',{exact:false}).waitFor();
  if(await page.locator('#comparisonPanel').getByText('2018',{exact:false}).count()===0)throw new Error('Cross-cycle diagnostics not rendered');

  await page.selectOption('#diagCycle','2018');
  await page.selectOption('#diagCheckpoint','14');
  const selectedText=await page.locator('#competitivePanel').innerText();
  if(!selectedText.includes('2018')||!selectedText.includes('14 days'))throw new Error('Diagnostic controls did not update panels');
  const pairedText=await page.locator('#pairedPollingPanel').innerText();
  if(!pairedText.includes('2018')||!pairedText.includes('14d'))throw new Error('Paired polling panel did not follow controls');

  const body=await page.locator('body').innerText();
  if(!body.match(/Brier\s+0\.\d+/))throw new Error('Scored historical Brier metric is not rendered');

  await page.setViewportSize({width:390,height:844});
  await page.reload({waitUntil:'networkidle'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+2);
  if(overflow)throw new Error('Model Lab has horizontal page overflow at phone viewport');
  if(consoleErrors.length)throw new Error(`Model Lab browser errors: ${consoleErrors.join(' | ')}`);
  console.log(`MODEL LAB browser checks passed: desktop + mobile + ${scored}/${requested} historical cycles scored; diagnostics rendered; 2022 n=416.`);
} finally {
  await browser.close();
}
