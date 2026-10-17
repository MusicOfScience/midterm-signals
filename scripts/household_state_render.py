"""Human-readable monthly report and public HTML rendering."""
from household_state_core import *
from household_state_classifiers import *
from household_state_composites import *
from household_state_outputs import *

def render_report(
    as_of: str, states: dict[str, dict], dashboard: list[dict], contradictions: list[dict], alerts: list[dict],
    chain: list[dict], composite: dict, distributional: list[dict], watchlist: list[dict], change_log: dict,
    electoral_links: dict, political_composite: dict,
) -> str:
    lines=[f"# US Household & Voter Economic State — {as_of}", "", "> **Governance:** contextual analytical sensor only. Forecast effect: **NONE**. Provisional baseline labels remain explicitly provisional until triangulation rules are met.", ""]
    lines += ["## A. Executive judgment", ""]
    executive = [
        "affordability_pressure", "real_income_pressure", "labour_market_security", "employment_retention_security",
        "job_mobility_security", "household_cash_flow", "financial_buffer", "credit_stress", "current_conditions",
        "expectations", "partisan_deflection", "electoral_economic_pressure",
    ]
    for key in executive[:12]:
        r=states.get(key)
        if r:
            lines.append(f"- **{key.replace('_',' ').title()}: {r.get('state')}** — {r.get('confidence')} confidence; {r.get('state_status')}.")

    lines += ["", "## B. State dashboard", "", "| Indicator | Latest | Previous | Jan 2026 | 12-month comparison | Direction | State | Confidence | Freshness | Reference period | Publication |", "|---|---:|---:|---:|---:|---|---|---|---|---|---|"]
    for r in dashboard:
        yoy=r.get('twelve_month_comparison')
        yoy_txt=f"{yoy:.1f}%" if isinstance(yoy,(int,float)) else "—"
        lines.append(f"| {r.get('indicator')} | {r.get('latest')} | {r.get('previous') if r.get('previous') is not None else '—'} | {r.get('january_2026') if r.get('january_2026') is not None else '—'} | {yoy_txt} | {r.get('direction')} | {r.get('state')} | {r.get('confidence')} | {r.get('freshness')} | {r.get('data_reference_period') or '—'} | {r.get('publication_date') or '—'} |")

    lines += ["", "## C. Transmission chain", "", " → ".join(f"{x['label']} {x['state']}" for x in chain), "", "### Electoral transmission links", ""]
    for link in electoral_links.get("links", []):
        lines.append(f"- **{link['link'].replace('_',' ').title()}: {link['state']}** — {link['status']}.")

    lines += ["", "## D. Distributional state", ""]
    if distributional:
        for group in distributional:
            lines.append(f"- **{group['group']}** — {group['confidence']} confidence; {len(group['observations'])} admitted observation(s).")
    else:
        lines.append("- No subgroup breakdown is published on this run because no observation has yet passed the module's group/sample admission rule. Absence is not treated as equality across groups.")

    lines += ["", "## E. Political state", ""]
    political_keys = [
        ("economic_salience", "Economic salience"), ("incumbent_attribution", "Incumbent attribution"),
        ("partisan_deflection", "Republican deflection"), ("independent_state", "Independent movement"),
        ("cross_partisan_affordability_consensus", "Cross-partisan affordability consensus"),
        ("electoral_economic_pressure", "Economic electoral pressure"),
    ]
    for key,label in political_keys:
        r=states.get(key, {})
        lines.append(f"- **{label}: {r.get('state','UNCERTAIN')}** — {r.get('confidence','UNCERTAIN')} confidence; {r.get('state_status','EVIDENCE_INSUFFICIENT')}.")
    lines += ["", f"Political-economic pressure composite: **{political_composite.get('state')}**. Published score: {political_composite.get('score') if political_composite.get('score') is not None else 'withheld for insufficient evidence coverage'}; evidence coverage {political_composite.get('evidence_coverage_pct')}%. Descriptive only."]

    lines += ["", "## F. Contradictions", ""]
    if contradictions:
        for c in contradictions[:8]:
            lines.append(f"- **{c['contradiction']}** — Observation: {c['observation']} Mechanism: {c['mechanism']} Confidence: {c['confidence']}. Political relevance: {c['political_relevance']}")
    else:
        lines.append("- No governed contradiction rule fired on the admitted evidence.")

    lines += ["", "## G. Midterm implications", "", "### Observed facts", ""]
    derived = [(k,v) for k,v in states.items() if isinstance(v,dict) and v.get("state_status") == "EVIDENCE_DERIVED"]
    if derived:
        for key,r in derived[:8]:
            lines.append(f"- {key.replace('_',' ').title()}: **{r.get('state')}** ({r.get('confidence')} confidence).")
    else:
        lines.append("- No state has yet met the evidence-derived classification rule.")
    lines += ["", "### Analytical inference", "", "- Economic experience is not treated as vote pressure unless it transmits through salience, attribution, partisan penetration and vote intention. Missing links remain missing.", "- Provisional baseline labels are hypotheses, not observations, and cannot satisfy high-confidence triangulation by themselves.", "", "### Forecast implications", "", "**NONE.** This module is not wired to House or Senate numerical probabilities. Any future numerical interface requires preregistration, historical backtesting, leakage controls, coefficient/calibration documentation, uncertainty propagation and an explicit model-version/governance change.", ""]

    lines += ["## H. Watchlist", ""]
    for item in watchlist[:15]:
        lines.append(f"- **{item['indicator']}** — current state {item['current_state']}; trigger: {item['trigger']}; why it matters: {item['why_it_matters']}; next expected release: {item.get('next_expected_release') or 'not registered'}.")

    lines += ["", "## Analytical alerts", ""]
    if alerts:
        for a in alerts:
            lines.append(f"- **{a['alert']}** — {a['basis']}")
    else:
        lines.append("- No configured analytical alert fired on admitted evidence.")

    lines += ["", "## Descriptive household-stress composite", ""]
    if composite.get("score") is None:
        lines.append(f"Published score withheld: evidence coverage is {composite.get('evidence_coverage_pct')}%. Provisional component score is {composite.get('provisional_score')} ({composite.get('provisional_state')}).")
    else:
        lines.append(f"Descriptive score: **{composite.get('score')} / 100 ({composite.get('state')})**. Evidence coverage: {composite.get('evidence_coverage_pct')}%.")
    lines.append("This index is decomposable and descriptive only; it is not a forecasting coefficient.")

    lines += ["", "## Monthly state change log", ""]
    for label,key in [("New signals","new_signals"),("Strengthened signals","strengthened_signals"),("Weakened signals","weakened_signals"),("Reversed signals","reversed_signals"),("Unchanged signals","unchanged_signals")]:
        entries=change_log.get(key,[])
        if entries:
            lines.append(f"- **{label}:** " + "; ".join(f"{x['sensor']} {x.get('previous') or 'NEW'} → {x.get('current')}" for x in entries))
    lines.append("")
    return "\n".join(lines)


def render_html(as_of: str, states: dict[str, dict], dashboard: list[dict], contradictions: list[dict], alerts: list[dict], chain: list[dict], composite: dict) -> str:
    def esc(v: Any) -> str:
        return str(v if v is not None else "—").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')
    cards="".join(f'<article class="card"><small>{esc(k.replace("_"," ").upper())}</small><strong>{esc(v.get("state"))}</strong><span>{esc(v.get("confidence"))} · {esc(v.get("state_status"))}</span></article>' for k,v in states.items() if k in {"affordability_pressure","real_income_pressure","labour_market_security","household_cash_flow","financial_buffer","credit_stress","current_conditions","expectations","partisan_deflection","electoral_economic_pressure"})
    rows="".join(f'<tr><td>{esc(r.get("indicator"))}</td><td>{esc(r.get("latest"))}</td><td>{esc(round(r.get("twelve_month_comparison"),1) if isinstance(r.get("twelve_month_comparison"),(int,float)) else "—")}</td><td>{esc(r.get("state"))}</td><td>{esc(r.get("freshness"))}</td></tr>' for r in dashboard)
    contradictions_html="".join(f'<li><b>{esc(c["contradiction"])}</b> — {esc(c["observation"])}</li>' for c in contradictions) or "<li>No governed contradiction rule fired.</li>"
    alerts_html="".join(f'<li><b>{esc(a["alert"])}</b> — {esc(a["basis"])}</li>' for a in alerts) or "<li>No configured analytical alert fired.</li>"
    chain_html="<span> → </span>".join(f'<b>{esc(x["label"])} {esc(x["state"])}</b>' for x in chain)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f2eee4"><title>US Household & Voter State · MIDTERM SIGNALS</title><style>
:root{{--paper:#f2eee4;--ink:#1b1a17;--muted:#68635a;--line:#c9c0b1;--panel:#faf7f0}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}a{{color:inherit}}header,main{{max-width:1180px;margin:auto;padding:24px}}header{{border-bottom:1px solid var(--line)}}.brand{{font-weight:800;letter-spacing:.06em}}h1{{font-size:clamp(2.3rem,7vw,5.5rem);line-height:.92;margin:.5rem 0 1rem}}.deck{{max-width:850px;font-size:1.15rem}}.guard{{padding:12px 14px;border:2px solid var(--ink);font-weight:700;margin:20px 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}}.card{{background:var(--panel);border:1px solid var(--line);padding:16px;display:flex;min-height:130px;flex-direction:column;gap:8px}}.card strong{{font-size:1.15rem}}.card span,.card small,.muted{{color:var(--muted)}}section{{margin:34px 0}}.chain{{background:var(--panel);border:1px solid var(--line);padding:18px;overflow:auto}}table{{width:100%;border-collapse:collapse;background:var(--panel)}}th,td{{text-align:left;padding:10px;border-bottom:1px solid var(--line)}}th{{position:sticky;top:0;background:var(--panel)}}.table-wrap{{overflow:auto}}ul{{padding-left:22px}}footer{{border-top:1px solid var(--line);padding:24px;max-width:1180px;margin:auto;color:var(--muted)}}
</style></head><body><header><a class="brand" href="/">M∕S · MIDTERM SIGNALS</a><div class="muted">Governed economic-political sensor · {esc(as_of)}</div><h1>US Household<br>& Voter State</h1><p class="deck">What is happening to households, to whom, through which transmission channel, at what speed, and whether that pressure is becoming politically consequential.</p><div class="guard">FORECAST EFFECT: NONE · This page cannot alter House or Senate numerical probabilities.</div></header><main><section><div class="grid">{cards}</div></section><section><h2>Transmission chain</h2><div class="chain">{chain_html}</div></section><section><h2>Household stress composite</h2><p><strong>{esc(composite.get('score') if composite.get('score') is not None else 'WITHHELD')} · {esc(composite.get('state'))}</strong></p><p class="muted">Descriptive only. Evidence coverage {esc(composite.get('evidence_coverage_pct'))}%; classification coverage {esc(composite.get('classification_coverage_pct'))}%. Provisional component score: {esc(composite.get('provisional_score'))}.</p></section><section><h2>State dashboard</h2><div class="table-wrap"><table><thead><tr><th>Indicator</th><th>Latest</th><th>YoY %</th><th>State</th><th>Freshness</th></tr></thead><tbody>{rows}</tbody></table></div></section><section><h2>Contradictions</h2><ul>{contradictions_html}</ul></section><section><h2>Analytical alerts</h2><ul>{alerts_html}</ul></section><section><h2>Midterm implications</h2><h3>Observed facts</h3><p>Raw and normalised measurements are stored separately from state classifications.</p><h3>Analytical inference</h3><p>Economic experience must transmit through salience, attribution, partisan penetration and vote intention before it is treated as electoral pressure.</p><h3>Forecast implications</h3><p><strong>NONE.</strong> Any future numerical interface requires preregistered variables, historical backtesting, leakage controls, calibration analysis and an explicit model-version change.</p></section></main><footer><a href="/data/household/household_state.json">Household JSON</a> · <a href="/data/household/voter_state.json">Voter JSON</a> · <a href="/data/household/source_health.json">Source health</a> · <a href="https://github.com/MusicOfScience/midterm-signals">Source code</a></footer></body></html>'''
