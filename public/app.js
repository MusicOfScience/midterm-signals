(async()=>{
  const parts=['/app-parts/1.jsfrag','/app-parts/2.jsfrag','/app-parts/3.jsfrag','/app-parts/4.jsfrag','/app-parts/5.jsfrag'];
  globalThis.__MIDTERM_CORE__=await import('/core.mjs');
  const source=(await Promise.all(parts.map(async u=>{const r=await fetch(u);if(!r.ok)throw new Error(`Failed to load ${u}: ${r.status}`);return r.text()}))).join('');
  let patched=source.replace(/^import\s+\{([^}]+)\}\s+from\s+'\/core\.mjs';/, 'const {$1}=globalThis.__MIDTERM_CORE__;');
  // Keep race tiles as native buttons. Overriding them to listitem removes button semantics
  // and makes aria-label prohibited under the ARIA role model.
  patched=patched.replace('class="race-grid" role="list"','class="race-grid"').replaceAll(' role="listitem" aria-label=',' aria-label=');
  const blob=URL.createObjectURL(new Blob([patched],{type:'text/javascript'}));
  try{await import(blob)}finally{URL.revokeObjectURL(blob);delete globalThis.__MIDTERM_CORE__}
})().catch(err=>{console.error(err);const main=document.querySelector('#content');if(main)main.innerHTML='<div class="error-state"><h2>Application failed to load</h2><p>The static shell is available, but an interactive module could not be loaded. Production data remain available from the Data links.</p></div>'});
