(async()=>{
  const parts=['/app-parts/1.jsfrag','/app-parts/2.jsfrag','/app-parts/3.jsfrag','/app-parts/4.jsfrag','/app-parts/5.jsfrag'];
  globalThis.__MIDTERM_CORE__=await import('/core.mjs');
  const source=(await Promise.all(parts.map(async u=>{const r=await fetch(u);if(!r.ok)throw new Error(`Failed to load ${u}: ${r.status}`);return r.text()}))).join('');
  let patched=source.replace(/^import\s+\{([^}]+)\}\s+from\s+'\/core\.mjs';/, 'const {$1}=globalThis.__MIDTERM_CORE__;');
  // Preserve native button semantics for race tiles and explicitly name visual seat-share bars.
  patched=patched.replace('class="race-grid" role="list"','class="race-grid"').replaceAll(' role="listitem" aria-label=',' aria-label=');
  patched=patched.replaceAll('class="seat-track" aria-label=','class="seat-track" role="img" aria-label=');

  // Performance architecture: ordinary views boot from a compact projection;
  // poll/race detail hydrates the authoritative full snapshot only on demand.
  patched=patched.replace(
    'let MODEL=null,STATUS=null,SOURCES=null,HISTORY_INDEX=null,SEARCH=[];',
    'let MODEL=null,STATUS=null,SOURCES=null,HISTORY_INDEX=null,SEARCH=[],FULL_MODEL_PROMISE=null;'
  );
  patched=patched.replace(
    'function renderRoute(route){if(!MODEL)return;activeNav(route.view);',
    `function renderRoute(route){if(!MODEL)return;if(MODEL.__bootstrap&&['race','polls','pollster'].includes(route.view)){activeNav(route.view);$('#content').innerHTML='<div class="loading-screen"><div class="eyebrow">DEEP DATA</div><h1>Loading underlying observations</h1><p>Fetching the full immutable forecast snapshot for this detail view.</p></div>';if(!FULL_MODEL_PROMISE)FULL_MODEL_PROMISE=loadJSON('/data/forecast.json').then(full=>{if(full){MODEL=full;SEARCH=searchRecords(MODEL)}return full});FULL_MODEL_PROMISE.then(full=>{if(full)renderRoute(routeFromLocation());else $('#content').innerHTML='<div class="error-state"><h2>Detailed data unavailable</h2><p>The compact forecast remains available, but the full observation bundle could not be loaded.</p></div>'});return}activeNav(route.view);`
  );
  patched=patched.replace(
    "[MODEL,STATUS,SOURCES]=await Promise.all([loadJSON('/data/forecast.json'),loadJSON('/data/status.json',{}),loadJSON('/data/source-status.json',null)]);",
    "const initialRoute=routeFromLocation(),needsFull=['race','polls','pollster'].includes(initialRoute.view);[MODEL,STATUS,SOURCES]=await Promise.all([(needsFull?loadJSON('/data/forecast.json'):loadJSON('/data/bootstrap.json').then(x=>x||loadJSON('/data/forecast.json'))),loadJSON('/data/status.json',{}),loadJSON('/data/source-status.json',null)]);"
  );
  patched=patched.replace(
    'SEARCH=searchRecords(MODEL);setupChrome();setupSearch();renderRoute(routeFromLocation());',
    "SEARCH=searchRecords(MODEL);for(const name of MODEL.pollster_names||[])if(!SEARCH.some(r=>r.type==='pollster'&&r.key===name))SEARCH.push({type:'pollster',label:name,subtitle:'Pollster',key:name,terms:name});setupChrome();setupSearch();renderRoute(routeFromLocation());"
  );

  const blob=URL.createObjectURL(new Blob([patched],{type:'text/javascript'}));
  try{await import(blob);document.querySelector('.site-footer')?.removeAttribute('hidden');await import('/enhancements.mjs')}finally{URL.revokeObjectURL(blob);delete globalThis.__MIDTERM_CORE__}
})().catch(err=>{console.error(err);const main=document.querySelector('#content');if(main)main.innerHTML='<div class="error-state"><h2>Application failed to load</h2><p>The static shell is available, but an interactive module could not be loaded. Production data remain available from the Data links.</p></div>'});
