#!/usr/bin/env python3
"""Build MIDTERM SIGNALS production browser assets.

The source remains split into reviewable fragments, while production receives
ordinary ES modules and a single stylesheet. The homepage is statically rendered
from the current immutable forecast snapshot and ships only a tiny interaction
loader; the full analytical application hydrates on demand. This keeps the
30-second election briefing fast without sacrificing deep exploration routes.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
DATA = PUBLIC / "data"


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


def pct(v: object) -> str:
    try:
        return f"{round(float(v) * 100):.0f}%"
    except (TypeError, ValueError):
        return "—"


def num(v: object, digits: int = 1) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def signed(v: object, digits: int = 1) -> str:
    try:
        x = float(v)
        return f"{'D' if x >= 0 else 'R'} +{abs(x):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def interval(ch: dict, p: int = 80) -> str:
    vals = ch.get(f"dem_seats_{p}_interval") or []
    return "–".join(str(x) for x in vals) if vals else "—"


def esc(v: object) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def race_href(r: dict) -> str:
    return f"/?race={esc(r.get('race_code', ''))}"


def race_mini(r: dict) -> str:
    p = float(r.get("dem_probability", .5) or .5)
    side = "D" if p >= .5 else "R"
    win = max(p, 1 - p)
    return (
        '<div class="race-mini">'
        f'<div class="race-code">{esc(r.get("race_code", ""))}</div>'
        f'<div><a class="ssr-race-link" href="{race_href(r)}"><strong>{esc(r.get("dem_candidate") or "No D nominee")} '
        f'<span class="muted">vs</span> {esc(r.get("rep_candidate") or "No R nominee")}</strong>'
        f'<small>{esc(r.get("rating") or "Unrated")} · {signed(r.get("forecast_margin_d_minus_r"))}</small></a></div>'
        f'<div class="prob {"lead-d" if side == "D" else "lead-r"}">{pct(win)}<small>{side} WIN</small></div>'
        '</div>'
    )


def chamber_card(ch: dict, label: str) -> str:
    total = 435 if label == "HOUSE" else 100
    threshold = "218 seats for control" if label == "HOUSE" else "51 Democratic seats for control"
    width = max(0.0, min(100.0, float(ch.get("expected_dem_seats", 0) or 0) / total * 100))
    return f'''<article class="chamber-card">
      <div class="eyebrow">{label}</div><h2>{threshold}</h2>
      <div class="control-display"><div><small>DEMOCRATIC CONTROL</small><strong class="party-d">{pct(ch.get('dem_control_probability'))}</strong></div><div class="slash">/</div><div><small>REPUBLICAN CONTROL</small><strong class="party-r">{pct(ch.get('rep_control_probability'))}</strong></div></div>
      <div class="seat-track" role="img" aria-label="Expected Democratic seat share"><span style="width:{width:.1f}%"></span></div>
      <div class="metric-line"><div class="metric"><b>{num(ch.get('expected_dem_seats'))}</b><small>expected D seats</small></div><div class="metric"><b>{esc(ch.get('median_dem_seats', '—'))}</b><small>median D seats</small></div><div class="metric"><b>{interval(ch, 80)}</b><small>80% interval</small></div><div class="metric"><b>{signed(ch.get('net_change_dem'))}</b><small>projected net change</small></div></div>
    </article>'''


def source_summary(model: dict) -> str:
    sources = model.get("source_health") or []
    current = sum(1 for s in sources if (s.get("state") or s.get("health")) == "current")
    issue = len(sources) - current
    return f'''<article class="panel panel-pad"><div class="section-head"><div><div class="eyebrow">DATA HEALTH</div><h2>{current}/{len(sources) or '—'} sources current</h2></div><a href="/?view=data">Inspect →</a></div><p class="muted">{issue} adapter state{'s' if issue != 1 else ''} are stale, unavailable or deliberately not configured. Missing sources never become zeroes.</p></article>'''


def distribution_summary(ch: dict, label: str) -> str:
    return f'''<article class="panel panel-pad"><div class="eyebrow">{label.upper()} CONTROL DISTRIBUTION</div><h2>Uncertainty, not a point prediction</h2><div class="facts-grid"><div class="fact"><b>{num(ch.get('expected_dem_seats'))}</b><span>expected D seats</span></div><div class="fact"><b>{esc(ch.get('median_dem_seats', '—'))}</b><span>median</span></div><div class="fact"><b>{interval(ch, 50)}</b><span>50% interval</span></div><div class="fact"><b>{interval(ch, 95)}</b><span>95% interval</span></div></div></article>'''


def render_home(model: dict) -> str:
    summary = model.get("summary", {})
    h, s = summary.get("house", {}), summary.get("senate", {})
    joint = summary.get("joint_control", {})
    briefing = (model.get("briefing") or {}).get("thirty_second_read") or (
        f"The current model gives Democrats {pct(h.get('dem_control_probability'))} probability of House control and "
        f"{pct(s.get('dem_control_probability'))} probability of Senate control."
    )
    gcb = (model.get("national_environment") or {}).get("generic_ballot_d_minus_r")
    house_tip = (model.get("tipping_point_house") or [])[:6]
    senate_tip = (model.get("senate_battlegrounds") or [])[:6]
    uncertain = sorted(model.get("races") or [], key=lambda r: abs(float(r.get("dem_probability", .5) or .5) - .5))[:6]
    movers = sorted(model.get("races") or [], key=lambda r: abs(float((r.get("change") or {}).get("dem_probability", 0) or 0)), reverse=True)[:5]
    has_movers = any(abs(float((r.get("change") or {}).get("dem_probability", 0) or 0)) >= .001 for r in movers)
    generated = esc(model.get("generated_at", "Unavailable"))
    model_name = esc(model.get("model", "MIDTERM SIGNALS"))
    days = esc(model.get("days_to_election", "—"))

    return f'''<section data-ssr-home="true" class="ssr-home">
      <section class="hero"><div class="hero-grid"><div><div class="eyebrow">2026 US MIDTERM ELECTIONS</div><h1>MIDTERM<br>SIGNALS</h1><p class="hero-deck">A public, probabilistic election reference: current forecast, every federal legislative race, polling, scenarios, history and the provenance behind the numbers.</p></div><div class="countdown-block"><strong>{days}</strong><span>DAYS TO 3 NOVEMBER 2026</span></div></div><div class="meta-line"><span>Last forecast <b>{generated}</b></span><span>Model <b>{model_name}</b></span><span>Generic ballot <b>{signed(gcb)}</b></span></div></section>
      <section class="chamber-pair">{chamber_card(h, 'HOUSE')}{chamber_card(s, 'SENATE')}</section>
      <section class="section"><div class="section-head"><div><div class="eyebrow">CONGRESS</div><h2>Joint control</h2><p>The four chamber-control combinations from the same correlated simulations.</p></div><a href="/?view=forecast">Forecast centre →</a></div><div class="joint-grid"><div class="joint-cell"><strong>{pct(joint.get('dem_house_dem_senate'))}</strong><span>Democratic House + Democratic Senate</span></div><div class="joint-cell"><strong>{pct(joint.get('dem_house_rep_senate'))}</strong><span>Democratic House + Republican Senate</span></div><div class="joint-cell"><strong>{pct(joint.get('rep_house_dem_senate'))}</strong><span>Republican House + Democratic Senate</span></div><div class="joint-cell"><strong>{pct(joint.get('rep_house_rep_senate'))}</strong><span>Republican House + Republican Senate</span></div></div></section>
      <section class="section panel read-brief"><div><div class="eyebrow">THE 30-SECOND READ</div><h2>State of the race</h2></div><p>{esc(briefing)}</p></section>
      <section class="section split"><article class="panel panel-pad"><div class="section-head"><div><div class="eyebrow">HOUSE</div><h2>Tipping-point races</h2></div><a href="/?view=house">House centre →</a></div><div class="race-list">{''.join(race_mini(r) for r in house_tip)}</div></article><article class="panel panel-pad"><div class="section-head"><div><div class="eyebrow">SENATE</div><h2>Control battlegrounds</h2></div><a href="/?view=senate">Senate centre →</a></div><div class="race-list">{''.join(race_mini(r) for r in senate_tip)}</div></article></section>
      <section class="section split"><article class="panel panel-pad"><div class="section-head"><div><div class="eyebrow">{'BIGGEST MOVERS' if has_movers else 'FORECAST MOVEMENT'}</div><h2>{'Probability movement' if has_movers else 'No material movement recorded'}</h2></div><a href="/?view=history">History →</a></div>{''.join(race_mini(r) for r in movers) if has_movers else '<p class="muted">The latest snapshot does not record a material race-probability movement against the immediately previous comparable forecast.</p>'}</article>{source_summary(model)}</section>
      <section class="section split">{distribution_summary(h, 'House')}{distribution_summary(s, 'Senate')}</section>
      <section class="section split"><article class="panel panel-pad"><div class="eyebrow">MOST UNCERTAIN</div><h2>Closest races</h2><div class="race-list">{''.join(race_mini(r) for r in uncertain)}</div><a href="/?view=races">Open Race Explorer →</a></article><article class="panel panel-pad"><div class="eyebrow">EXPLORE</div><h2>Go deeper</h2><p class="prose">Interrogate every House and Senate race, inspect raw polls, stress-test the baseline in Scenario Lab, replay forecast history and trace each important number to its source.</p><div class="preset-row"><a class="button secondary" href="/?view=races">Race Explorer</a><a class="button secondary" href="/?view=polls">Polling centre</a><a class="button secondary" href="/?view=scenarios">Scenario Lab</a></div></article></section>
    </section>'''


def build_app() -> str:
    source = joined("app-parts", ".jsfrag")
    source = source.replace('class="race-grid" role="list"', 'class="race-grid"')
    source = source.replace(' role="listitem" aria-label=', ' aria-label=')
    source = source.replace('class="seat-track" aria-label=', 'class="seat-track" role="img" aria-label=')

    source = replace_required(source, 'let MODEL=null,STATUS=null,SOURCES=null,HISTORY_INDEX=null,SEARCH=[];', 'let MODEL=null,STATUS=null,SOURCES=null,HISTORY_INDEX=null,SEARCH=[],FULL_MODEL_PROMISE=null;', "model state")
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


def build_home_loader() -> str:
    return r'''const route=()=>{const p=new URLSearchParams(location.search);return location.pathname!=='/'||[...p.keys()].some(k=>['view','race','candidate','pollster'].includes(k))};
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
'''


def render_index(model: dict) -> None:
    path = PUBLIC / "index.html"
    text = path.read_text(encoding="utf-8")
    home = render_home(model)
    replacement = f'<main id="content" tabindex="-1">{home}</main>'
    text, count = re.subn(r'<main id="content" tabindex="-1">.*?</main>', replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("Could not replace homepage main content")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    forecast_path = DATA / "forecast.json"
    if not forecast_path.exists():
        raise RuntimeError("forecast.json is required before browser asset build")
    model = json.loads(forecast_path.read_text(encoding="utf-8"))

    app = build_app()
    enhancements = joined("enhancement-parts", ".jsfrag")
    css = "\n".join(p.read_text(encoding="utf-8") for p in numbered_parts(PUBLIC / "styles-parts", ".css")) + "\n"
    loader = build_home_loader()

    (PUBLIC / "app.bundle.mjs").write_text(app, encoding="utf-8")
    (PUBLIC / "enhancements.bundle.mjs").write_text(enhancements, encoding="utf-8")
    (PUBLIC / "app.js").write_text(loader, encoding="utf-8")
    (PUBLIC / "styles.css").write_text(css, encoding="utf-8")
    render_index(model)

    print(
        "browser assets:",
        f"home loader {len(loader.encode('utf-8')):,} B;",
        f"app {len(app.encode('utf-8')):,} B;",
        f"enhancements {len(enhancements.encode('utf-8')):,} B;",
        f"css {len(css.encode('utf-8')):,} B",
    )


if __name__ == "__main__":
    main()
