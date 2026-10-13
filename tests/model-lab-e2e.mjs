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
  if(data.schema_version!=='1.1.1')throw new Error(`Unexpected Model Lab schema ${data.schema_version}`);
  if(data.diagnostic_contract?.movement_threshold!==0.10||data.diagnostic_contract?.confident_miss_threshold!==0.80){
    throw new Error('Fixed diagnostic thresholds drifted');
  }
  if(!String(data.diagnostic_contract?.scoreability_gate||'').includes('stable Democratic/Republican candidate presence')){
    throw new Error('Pre-outcome scoreability gate missing from public diagnostic contract');
  }
  if(data.diagnostic_contract?.paired_polling_component_test?.model_effect!=='NONE'){
    throw new Error('Paired polling diagnostic must be evaluation-only');
  }
  if(data.diagnostic_contract?.structural_decomposition?.model_effect!=='NONE'){
    throw new Error('Structural decomposition must be evaluation-only');
  }
  if(data.diagnostic_contract?.structural_decomposition?.redistricting_identified!==false){
    throw new Error('Structural diagnostic must not claim redistricting is identified');
  }
  const stabilityContract=data.diagnostic_contract?.baseline_stability;
  if(stabilityContract?.model_effect!=='NONE'||stabilityContract?.band_assignment_uses_outcomes!==false){
    throw new Error('Baseline stability diagnostic must remain pre-outcome and evaluation-only');
  }
  if((stabilityContract?.fixed_range_bands_pp||[]).length!==4||stabilityContract?.high_instability_threshold_pp!==10){
    throw new Error('Baseline stability fixed thresholds drifted');
  }
  const pollErrorContract=data.diagnostic_contract?.polling_error_decomposition;
  if(pollErrorContract?.model_effect!=='NONE'||pollErrorContract?.outcomes_visible_only_after_forecasts!==true){
    throw new Error('Polling-error decomposition must remain post-forecast and evaluation-only');
  }
  if(!String(pollErrorContract?.result_margin_source||'').includes('result-margin-provenance.json')){
    throw new Error('Polling-error certified margin provenance missing');
  }
  const sourceContract=data.diagnostic_contract?.source_mix;
  if(sourceContract?.model_effect!=='NONE'||sourceContract?.feature_assignment_uses_outcomes!==false){
    throw new Error('Source-mix bands must remain pre-outcome and evaluation-only');
  }
  if((sourceContract?.poll_depth_bands||[]).join(',')!=='1,2,3-4,5+'||(sourceContract?.unique_pollster_bands||[]).join(',')!=='1,2,3+'){
    throw new Error('Source-mix fixed bands drifted');
  }
  if(Math.abs(Number(sourceContract?.top_source_concentration_threshold)-2/3)>1e-12||sourceContract?.pollster_minimum_distinct_race_sources!==5){
    throw new Error('Source-mix concentration or pollster sample threshold drifted');
  }
  if(sourceContract?.polling_mode!=='unavailable_not_in_historical_corpus'){
    throw new Error('Polling mode must remain explicitly unavailable rather than inferred');
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
  if(data.polling_error_cross_cycle?.state!=='scored'||(data.polling_error_cross_cycle?.cycles||[]).length!==2){
    throw new Error('House-only cross-cycle polling-error comparison missing');
  }
  if(data.source_mix_cross_cycle?.state!=='scored'||(data.source_mix_cross_cycle?.cycles||[]).length!==2){
    throw new Error('House-only cross-cycle source-mix comparison missing');
  }

  const state=(await page.locator('#labState').innerText()).trim().toUpperCase();
  const expectedLabel=`${scored}/${requested}`;
  if(!state.includes(expectedState.toUpperCase())||!state.includes(expectedLabel)){
    throw new Error(`Rendered Model Lab state diverges from data summary ${expectedState} ${expectedLabel}: ${state}`);
  }

  const cycleText=await page.locator('#cycleGrid').innerText();
  for(const year of ['2018','2022'])if(!cycleText.includes(year))throw new Error(`Missing ${year} cycle card`);

  const expectedSamples=new Map([[2018,468],[2022,416]]);
  for(const year of [2018,2022]){
    const cycle=data.cycles?.find(c=>c.cycle===year);
    const expectedN=expectedSamples.get(year);
    if(cycle?.state!=='scored')throw new Error(`${year} should be scored, got: ${cycle?.state}`);
    if(cycle?.scoreability?.state!=='frozen_pre_outcome'||cycle?.scoreability?.uses_outcomes!==false){
      throw new Error(`${year} scoreability decision was not frozen pre-outcome`);
    }
    if(cycle?.scoreability?.admitted_races!==expectedN){
      throw new Error(`${year} official scored sample drifted: ${cycle?.scoreability?.admitted_races} != ${expectedN}`);
    }
    if(cycle?.checkpoints?.length!==5||cycle.checkpoints.some(c=>c.state!=='scored'||c.score?.state!=='scored')){
      throw new Error(`${year} does not expose five fully scored checkpoints`);
    }
    if(cycle.movement?.state!=='scored')throw new Error(`${year} movement diagnostics missing`);
    if((cycle.movement?.polling_partitions||[]).length!==4)throw new Error(`${year} polling movement partitions missing`);
    for(const cp of cycle.checkpoints){
      if(cp.score?.n!==expectedN)throw new Error(`${year} ${cp.days_to_election}d denominator drift: ${cp.score?.n}`);
      if((cp.score?.competitive_bands||[]).length!==5)throw new Error(`${year} ${cp.days_to_election}d competitive diagnostics missing`);
      const pollN=Number(cp.score?.polling?.polled?.n||0)+Number(cp.score?.polling?.unpolled?.n||0);
      if(pollN!==cp.score?.n)throw new Error(`${year} ${cp.days_to_election}d polling partition drift`);
      if(cp.score?.polling?.paired_component_test?.state!=='scored')throw new Error(`${year} ${cp.days_to_election}d paired polling diagnostic missing`);
      const pollError=cp.score?.polling_error;
      if(pollError?.state!=='scored'||pollError?.outcome_margin_used_only_for_scoring!==true){
        throw new Error(`${year} ${cp.days_to_election}d polling-error diagnostic missing or leaked`);
      }
      if(Number(pollError?.all_polled?.n||0)<=0||pollError?.all_polled?.raw_race_poll_aggregate?.state!=='scored'){
        throw new Error(`${year} ${cp.days_to_election}d raw polling-error sample empty`);
      }
      const sourceMix=cp.score?.source_mix;
      if(sourceMix?.state!=='scored'||sourceMix?.feature_assignment_uses_outcomes!==false){
        throw new Error(`${year} ${cp.days_to_election}d source-mix diagnostic missing or leaked`);
      }
      const house=sourceMix.house_only;
      if(!house||house.state!=='scored'||house.n<=0)throw new Error(`${year} ${cp.days_to_election}d House source-mix sample empty`);
      for(const key of ['by_poll_depth','by_unique_pollsters','by_source_concentration','by_partisan_label_share']){
        const total=(house[key]||[]).reduce((sum,row)=>sum+Number(row.n||0),0);
        if(total!==house.n)throw new Error(`${year} ${cp.days_to_election}d source-mix partition ${key} drift: ${total} != ${house.n}`);
      }
      if(house.pollsters?.minimum_distinct_race_sources!==5||!String(house.pollsters?.ordering||'').includes('never ranked by error')){
        throw new Error(`${year} ${cp.days_to_election}d pollster reporting contract drifted`);
      }
      if(cp.score?.structural_decomposition?.state!=='scored')throw new Error(`${year} ${cp.days_to_election}d structural decomposition missing`);
      if(cp.score?.structural_decomposition_20_80?.state!=='scored')throw new Error(`${year} ${cp.days_to_election}d structural competitive decomposition missing`);
      if(Number(cp.score?.structural_decomposition?.n||0)<=0)throw new Error(`${year} ${cp.days_to_election}d structural denominator empty`);
      const stability=cp.score?.baseline_stability;
      if(stability?.state!=='scored'||stability?.band_assignment_uses_outcomes!==false){
        throw new Error(`${year} ${cp.days_to_election}d baseline stability diagnostic missing or leaked`);
      }
      if((stability?.bands||[]).length!==4)throw new Error(`${year} ${cp.days_to_election}d baseline stability bands drifted`);
      const stabilityN=(stability.bands||[]).reduce((sum,b)=>sum+Number(b.n||0),0);
      if(stabilityN!==stability.n||stability.n<=0)throw new Error(`${year} ${cp.days_to_election}d baseline stability denominator drift`);
      const calN=(cp.score?.calibration||[]).reduce((sum,b)=>sum+Number(b.count||0),0);
      if(calN!==cp.score?.n)throw new Error(`${year} ${cp.days_to_election}d calibration denominator drift`);
    }
  }

  const c2018=data.cycles?.find(c=>c.cycle===2018);
  const exclusions2018=new Set((c2018?.scoreability?.exclusions||[]).map(r=>r.race_code));
  if(!exclusions2018.has('LA-06')||!exclusions2018.has('OR-03')||exclusions2018.size!==2){
    throw new Error(`2018 scoreability exclusions drifted: ${JSON.stringify([...exclusions2018])}`);
  }
  const c2022=data.cycles?.find(c=>c.cycle===2022);
  if(c2022?.scoreability?.excluded_races!==0)throw new Error('2022 scoreability gate should exclude zero races');
  if(c2022?.chamber_scope?.senate?.state!=='unavailable')throw new Error('2022 Senate must be explicitly unavailable');

  if(await page.locator('#competitivePanel').getByText('45-55',{exact:false}).count()===0)throw new Error('Competitive diagnostics not rendered');
  if(await page.locator('#pollingPanel').getByText('Not a causal A/B test.',{exact:false}).count()===0)throw new Error('Polling caveat not rendered');
  await page.locator('#pairedPollingPanel').getByText('Same-race component test',{exact:false}).waitFor();
  await page.locator('#pollErrorPanel').getByText('Poll → result → model',{exact:false}).waitFor();
  await page.locator('#sourceMixPanel').getByText('Where is polling error concentrated?',{exact:false}).waitFor();
  await page.locator('#structuralAuditPanel').getByText('Where does forecast skill enter?',{exact:false}).waitFor();
  await page.locator('#baselineStabilityPanel').getByText('Did unstable structural history fail more often?',{exact:false}).waitFor();
  await page.locator('#movementPollingPanel').getByText('Movement by polling status',{exact:false}).waitFor();
  if(await page.locator('#comparisonPanel').getByText('2018',{exact:false}).count()===0)throw new Error('Cross-cycle diagnostics not rendered');

  await page.selectOption('#diagCycle','2018');
  await page.selectOption('#diagCheckpoint','14');
  const selectedText=await page.locator('#competitivePanel').innerText();
  if(!selectedText.includes('2018')||!selectedText.includes('14 days'))throw new Error('Diagnostic controls did not update panels');
  const pairedText=await page.locator('#pairedPollingPanel').innerText();
  if(!pairedText.includes('2018')||!pairedText.includes('14d'))throw new Error('Paired polling panel did not follow controls');
  const pollErrorText=await page.locator('#pollErrorPanel').innerText();
  if(!pollErrorText.includes('2018')||!pollErrorText.includes('14d'))throw new Error('Polling-error panel did not follow controls');
  const sourceMixText=await page.locator('#sourceMixPanel').innerText();
  if(!sourceMixText.includes('2018')||!sourceMixText.includes('14d'))throw new Error('Source-mix panel did not follow controls');
  const structuralText=await page.locator('#structuralAuditPanel').innerText();
  if(!structuralText.includes('2018')||!structuralText.includes('14d'))throw new Error('Structural panel did not follow controls');
  const stabilityText=await page.locator('#baselineStabilityPanel').innerText();
  if(!stabilityText.includes('2018')||!stabilityText.includes('14d'))throw new Error('Baseline stability panel did not follow controls');

  const body=await page.locator('body').innerText();
  if(!body.match(/Brier\s+0\.\d+/))throw new Error('Scored historical Brier metric is not rendered');

  await page.setViewportSize({width:390,height:844});
  await page.reload({waitUntil:'networkidle'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+2);
  if(overflow)throw new Error('Model Lab has horizontal page overflow at phone viewport');
  if(consoleErrors.length)throw new Error(`Model Lab browser errors: ${consoleErrors.join(' | ')}`);
  console.log(`MODEL LAB browser checks passed: desktop + mobile + ${scored}/${requested} cycles scored; scoreability + structural + baseline-stability + polling-error + source-mix audits verified.`);
} finally {
  await browser.close();
}