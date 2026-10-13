#!/usr/bin/env python3
"""Build production browser assets without runtime source assembly.

Canonical application and enhancement sources stay split into reviewable fragments,
but the public browser receives ordinary ES modules and one combined stylesheet.
This removes the runtime fetch/concatenate/Blob/import path that dominated v1
startup time while preserving the existing application architecture.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def numbered_parts(directory: Path, suffix: str) -> list[Path]:
    def order(path: Path) -> tuple[int, str]:
        try:
            return (int(path.stem.split(".")[0]), path.name)
        except ValueError:
            return (10_000, path.name)
    return sorted(directory.glob(f"*{suffix}"), key=order)


def joined(directory: str, suffix: str) -> str:
    files = numbered_parts(PUBLIC / directory, suffix)
    if not files:
        raise RuntimeError(f"No browser source parts found in {directory}")
    return "".join(p.read_text(encoding="utf-8") for p in files)


def replace_required(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        raise RuntimeError(f"Browser build patch target missing: {label}")
    return source.replace(old, new, 1)


def build_app() -> str:
    source = joined("app-parts", ".jsfrag")

    # Accessibility fixes formerly applied by the runtime loader.
    source = source.replace('class="race-grid" role="list"', 'class="race-grid"')
    source = source.replace(' role="listitem" aria-label=', ' aria-label=')
    source = source.replace('class="seat-track" aria-label=', 'class="seat-track" role="img" aria-label=')

    # Ordinary routes use a compact forecast projection. Observation-heavy detail
    # views hydrate the authoritative full snapshot only when requested.
    source = replace_required(
        source,
        'let MODEL=null,STATUS=null,SOURCES=null,HISTORY_INDEX=null,SEARCH=[];',
        'let MODEL=null,STATUS=null,SOURCES=null,HISTORY_INDEX=null,SEARCH=[],FULL_MODEL_PROMISE=null;',
        "model state",
    )
    source = replace_required(
        source,
        'function renderRoute(route){if(!MODEL)return;activeNav(route.view);',
        "function renderRoute(route){if(!MODEL)return;if(MODEL.__bootstrap&&['race','polls','pollster','candidate'].includes(route.view)){activeNav(route.view);$('#content').innerHTML='<div class=\"loading-screen\"><div class=\"eyebrow\">DEEP DATA</div><h1>Loading underlying observations</h1><p>Fetching the full immutable forecast snapshot for this detail view.</p></div>';if(!FULL_MODEL_PROMISE)FULL_MODEL_PROMISE=loadJSON('/data/forecast.json').then(full=>{if(full){MODEL=full;SEARCH=searchRecords(MODEL)}return full});FULL_MODEL_PROMISE.then(full=>{if(full)renderRoute(routeFromLocation());else $('#content').innerHTML='<div class=\"error-state\"><h2>Detailed data unavailable</h2><p>The compact forecast remains available, but the full observation bundle could not be loaded.</p></div>'});return}activeNav(route.view);",
        "deep data hydration",
    )
    source = replace_required(
        source,
        "[MODEL,STATUS,SOURCES]=await Promise.all([loadJSON('/data/forecast.json'),loadJSON('/data/status.json',{}),loadJSON('/data/source-status.json',null)]);",
        "const initialRoute=routeFromLocation(),needsFull=['race','polls','pollster','candidate'].includes(initialRoute.view);[MODEL,STATUS,SOURCES]=await Promise.all([(needsFull?loadJSON('/data/forecast.json'):loadJSON('/data/bootstrap.json').then(x=>x||loadJSON('/data/forecast.json'))),loadJSON('/data/status.json',{}),loadJSON('/data/source-status.json',null)]);",
        "bootstrap loading",
    )
    source = replace_required(
        source,
        'SEARCH=searchRecords(MODEL);setupChrome();setupSearch();renderRoute(routeFromLocation());',
        "SEARCH=searchRecords(MODEL);for(const name of MODEL.pollster_names||[])if(!SEARCH.some(r=>r.type==='pollster'&&r.key===name))SEARCH.push({type:'pollster',label:name,subtitle:'Pollster',key:name,terms:name});setupChrome();setupSearch();renderRoute(routeFromLocation());",
        "search hydration",
    )

    # Enhancement code is not part of the homepage critical path. All other
    # analytical routes may opt into the richer v1 controls after first render.
    # Keep the small mobile-navigation Escape behaviour in the base bundle so
    # accessibility does not depend on loading the enhancement module.
    lazy = r'''let __ENHANCEMENTS_PROMISE=null;
function __maybeLoadEnhancements(){
  const view=routeFromLocation().view;
  if(view==='home')return;
  if(!__ENHANCEMENTS_PROMISE)__ENHANCEMENTS_PROMISE=import('/enhancements.bundle.mjs').catch(err=>{console.warn('MIDTERM SIGNALS v1 enhancements unavailable',err);return null});
}
window.addEventListener('popstate',()=>setTimeout(__maybeLoadEnhancements,0));
document.addEventListener('click',()=>setTimeout(__maybeLoadEnhancements,0),{capture:true,passive:true});
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;const nav=document.querySelector('#primaryNav'),toggle=document.querySelector('#navToggle');if(nav?.classList.contains('open')){nav.classList.remove('open');toggle?.setAttribute('aria-expanded','false');toggle?.focus()}});
boot().then(()=>{document.querySelector('.site-footer')?.removeAttribute('hidden');setTimeout(__maybeLoadEnhancements,0)}).catch(err=>{console.error(err);const main=document.querySelector('#content');if(main)main.innerHTML='<div class="error-state"><h2>Application failed to load</h2><p>The static shell is available, but the interactive application could not be initialised.</p></div>'});
'''
    source = replace_required(source, "boot();\n", lazy, "boot invocation")
    return source


def main() -> None:
    app = build_app()
    enhancements = joined("enhancement-parts", ".jsfrag")
    css = "\n".join(p.read_text(encoding="utf-8") for p in numbered_parts(PUBLIC / "styles-parts", ".css")) + "\n"

    (PUBLIC / "app.bundle.mjs").write_text(app, encoding="utf-8")
    (PUBLIC / "enhancements.bundle.mjs").write_text(enhancements, encoding="utf-8")
    (PUBLIC / "app.js").write_text("import '/app.bundle.mjs';\n", encoding="utf-8")
    (PUBLIC / "styles.css").write_text(css, encoding="utf-8")

    print(
        "browser assets:",
        f"app {len(app.encode('utf-8')):,} B;",
        f"enhancements {len(enhancements.encode('utf-8')):,} B;",
        f"css {len(css.encode('utf-8')):,} B",
    )


if __name__ == "__main__":
    main()
