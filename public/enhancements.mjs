(async()=>{
  const parts=['/enhancement-parts/1.jsfrag','/enhancement-parts/2.jsfrag','/enhancement-parts/3.jsfrag','/enhancement-parts/4.jsfrag','/enhancement-parts/5.jsfrag','/enhancement-parts/6.jsfrag'];
  globalThis.__MIDTERM_V1_CORE__=await import('/core.mjs');
  const source=(await Promise.all(parts.map(async u=>{const r=await fetch(u);if(!r.ok)throw new Error(`Failed to load ${u}: ${r.status}`);return r.text()}))).join('');
  const patched=source.replace(/^import\s+\{([^}]+)\}\s+from\s+'\/core\.mjs';/,'const {$1}=globalThis.__MIDTERM_V1_CORE__;');
  const blob=URL.createObjectURL(new Blob([patched],{type:'text/javascript'}));
  try{await import(blob)}finally{URL.revokeObjectURL(blob);delete globalThis.__MIDTERM_V1_CORE__}
})().catch(err=>console.warn('MIDTERM SIGNALS v1 enhancements unavailable',err));
