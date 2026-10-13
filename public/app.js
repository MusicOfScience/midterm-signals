const route=()=>{const p=new URLSearchParams(location.search);return location.pathname!=='/'||[...p.keys()].some(k=>['view','race','candidate','pollster'].includes(k))};
let full=null;const load=()=>full??=import('/app.bundle.mjs');
if(route()||!document.querySelector('[data-ssr-home]')){load()}else{
  document.querySelector('.site-footer')?.removeAttribute('hidden');
  const nav=document.querySelector('#primaryNav'),toggle=document.querySelector('#navToggle');
  toggle?.addEventListener('click',()=>{const open=nav.classList.toggle('open');toggle.setAttribute('aria-expanded',String(open))});
  document.addEventListener('keydown',async e=>{if(e.key==='Escape'&&nav?.classList.contains('open')){nav.classList.remove('open');toggle?.setAttribute('aria-expanded','false');toggle?.focus();return}if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)){e.preventDefault();await load();setTimeout(()=>document.querySelector('#openSearch')?.click(),0)}});
  document.querySelector('#healthChip')?.addEventListener('click',()=>{location.href='/?view=data'});
  const search=document.querySelector('#openSearch');search?.addEventListener('click',async e=>{e.preventDefault();await load();setTimeout(()=>document.querySelector('#openSearch')?.click(),0)},{once:true});
  const bar=document.querySelector('#contextBar');if(bar)bar.innerHTML='<span><strong>PROD v1</strong> · current forecast rendered at build time · open any analytical section for full interactive exploration</span>';
  fetch('/data/source-status.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(x=>{if(!x)return;const src=x.sources||[],bad=src.filter(s=>(s.state||s.health)!=='current').length,chip=document.querySelector('#healthChip');if(chip){chip.classList.add(bad?'degraded':'current');const label=chip.querySelector('span:last-child');if(label)label.textContent=bad?`${bad} source issue${bad===1?'':'s'}`:'Data current'}}).catch(()=>{});
}
