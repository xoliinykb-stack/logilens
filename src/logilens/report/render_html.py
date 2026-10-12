"""Single self-contained HTML report (inline CSS, light/dark via ``prefers-color-scheme``, no scripts needed)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from logilens.i18n import issue_fix, issue_message, t
from logilens.report import render_seq
from logilens.report.model import FormResult, GroupReport, Report, Verdict
from logilens.report.svg import kmap_svg
from logilens.report.text import (
    best_form,
    cover_formulas,
    derivation_legend,
    derivations,
    form_label,
    msg,
    robustness_text,
    tech_label,
    verdict_label,
    verdict_sentence,
)

VERDICT_CLASS = {
    Verdict.OPTIMAL: "ok", Verdict.IMPROVABLE: "warn", Verdict.BEYOND_TWO_LEVEL: "beyond",
    Verdict.UNPROVEN: "unproven", Verdict.NOT_APPLICABLE: "na",
}

CSS = """
:root{--paper:#fff;--ink:#1a1a1a;--soft:#555;--faint:#8a8a8a;--rule:#d9d9d9;--hair:#ececec;--tint:#f6f6f4;
--link:#1f4e8c;--ok:#1b7a3a;--warn:#a35b00;--bad:#b3261e;--beyond:#7a3e8e;--unproven:#1f4e8c;--na:#777;
--serif:"Charter","Iowan Old Style","Palatino Linotype",Georgia,"Times New Roman",serif;
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
--fg:var(--ink);--muted:var(--soft);--line:var(--rule);--card:var(--paper);--bg:var(--paper);--accent:var(--ink)}
@media (prefers-color-scheme:dark){:root{--paper:#17181b;--ink:#e4e2dd;--soft:#a9a6a0;--faint:#7b7974;
--rule:#34353a;--hair:#2a2b2f;--tint:#1f2024;--link:#8fb4e8;--ok:#5fbf7d;--warn:#e0a24a;--bad:#ef7b72;
--beyond:#c79ad8;--unproven:#8fb4e8}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 var(--sans)}
a{color:var(--link)}
.page{display:grid;grid-template-columns:200px minmax(0,880px);gap:56px;max-width:1180px;margin:0 auto;
padding:40px 32px 80px}
aside.toc{position:sticky;top:32px;align-self:start;font-size:13.5px}
aside.toc .brand{font-family:var(--serif);font-size:17px;color:var(--ink);margin-bottom:14px}
aside.toc ol{list-style:none;margin:0;padding:0;counter-reset:toc}
aside.toc li{counter-increment:toc;margin:0 0 6px}
aside.toc li::before{content:counter(toc) ".";color:var(--faint);display:inline-block;width:22px;
font-variant-numeric:tabular-nums}
aside.toc a{color:var(--soft);text-decoration:none}aside.toc a:hover{color:var(--ink);text-decoration:underline}
main{counter-reset:sec;min-width:0}
header.doc{border-bottom:2px solid var(--ink);padding-bottom:18px;margin-bottom:8px}
header.doc .kicker{font-size:12.5px;color:var(--soft);letter-spacing:.02em}
h1{font-family:var(--serif);font-weight:600;font-size:32px;line-height:1.15;margin:6px 0 4px;word-break:break-word}
header.doc .sub{color:var(--soft);font-size:14px}
h2{font-family:var(--serif);font-weight:600;font-size:22px;margin:44px 0 12px;padding-top:12px;
border-top:1px solid var(--rule)}
h2::before{counter-increment:sec;content:counter(sec);color:var(--faint);font-weight:400;margin-right:12px;
font-variant-numeric:tabular-nums}
h3{font-family:var(--serif);font-weight:600;font-size:18px;margin:30px 0 8px}
h4{font-size:13px;font-weight:600;margin:22px 0 8px;color:var(--soft)}
p{margin:8px 0}.muted{color:var(--soft)}
.card{margin:0}
.facts{margin:18px 0 0;width:100%}.facts th{width:190px;color:var(--soft);font-weight:400;text-transform:none;
letter-spacing:0;font-size:14px}
.verdict-line{font-size:17px;margin:16px 0 0}
.status{font-weight:600;white-space:nowrap}.status::before{content:"";display:inline-block;width:.62em;height:.62em;
margin-right:.4em;background:currentColor;vertical-align:.06em}
.s-ok{color:var(--ok)}.s-warn{color:var(--warn)}.s-bad{color:var(--bad)}.s-beyond{color:var(--beyond)}
.s-unproven{color:var(--unproven)}.s-na{color:var(--na)}
.v-ok{color:var(--ok)}.v-warn{color:var(--warn)}.v-beyond{color:var(--beyond)}.v-unproven{color:var(--unproven)}
.v-na{color:var(--na)}
table{border-collapse:collapse;width:100%;font-size:14px;margin:6px 0}
th,td{padding:7px 12px 7px 0;border-bottom:1px solid var(--hair);text-align:left;vertical-align:top}
thead th{border-bottom:1px solid var(--ink);color:var(--ink);font-weight:600;font-size:13px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.scroll{overflow-x:auto}
.sev-error{color:var(--bad);font-weight:600}.sev-warning{color:var(--warn);font-weight:600}
.sev-info{color:var(--unproven);font-weight:600}
.counts{color:var(--soft);margin:0 0 8px}
.verdict{border-left:3px solid var(--na);padding:2px 0 2px 14px;margin:10px 0 14px}
.verdict.ok{border-color:var(--ok)}.verdict.warn{border-color:var(--warn)}.verdict.beyond{border-color:var(--beyond)}
.verdict.unproven{border-color:var(--unproven)}.verdict ul{margin:6px 0 0;color:var(--soft)}
pre,code{font-family:var(--mono);font-size:13px}
pre{background:var(--tint);padding:12px 14px;overflow-x:auto;line-height:1.55;border-left:2px solid var(--rule)}
code{font-size:.92em}
tr.match td{color:var(--ok)}tr.ilp td:first-child{font-weight:600}
.kmaps{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:26px 30px;margin:10px 0}
figure.kmap{margin:0}figure.kmap svg{display:block;max-width:100%;height:auto}
ul.legend{list-style:none;padding:0;margin:6px 0 0;font:12px/1.65 var(--mono);color:var(--soft)}
ul.legend span{display:inline-block;width:14px;height:0;border-top:2.5px solid;margin-right:8px;vertical-align:.25em}
ul{margin:6px 0;padding-left:20px}
details{margin:8px 0}details>summary{cursor:pointer;color:var(--link);font-size:14px}
details[open]>summary{margin-bottom:6px}
.figure{margin:12px 0}.figure .caption{font-size:13px;color:var(--soft);margin-top:6px}
.circuit-box{max-height:520px;overflow:auto;border:1px solid var(--rule);background:#fff}
.circuit-box img{display:block;max-width:100%;height:auto;margin:0 auto}
svg.timing,.graph svg{display:block;max-width:100%;height:auto}.graph{overflow-x:auto}
footer{margin-top:56px;padding-top:12px;border-top:1px solid var(--rule);font-size:12.5px;color:var(--faint)}
@media (max-width:980px){.page{grid-template-columns:minmax(0,1fr);padding:24px 16px 64px;gap:0}
aside.toc{display:none}h1{font-size:26px}.kmaps{grid-template-columns:minmax(0,1fr)}}
@media print{aside.toc{display:none}.page{display:block;padding:0}details{display:block}
.circuit-box{max-height:none}h2{break-after:avoid}figure,table{break-inside:avoid}}
"""


def _e(value: object) -> str:
    return escape(str(value))


def render(report: Report, lang: str | None = None) -> str:
    lang = lang or report.lang
    sections = [
        ("circuit", t("ui.circuit_image", lang), _image(report, lang)),
        ("lint", t("ui.lint", lang), _lint(report, lang)),
        ("spec", t("ui.spec_check", lang), _spec(report, lang)),
        ("summary", t("ui.summary", lang), _summary(report, lang)
         + "".join(_group(g, lang) for g in report.groups)),
        ("truth", t("ui.truth_table", lang), _truth(report, lang)),
        ("seq", t("ui.sequential", lang), _seq(report, lang)),
        ("notes", t("ui.recommendations", lang), _closing(report, lang)),
    ]
    present = [(sid, label, body) for sid, label, body in sections if body]
    toc = "".join(f'<li><a href="#{sid}">{_e(label)}</a></li>' for sid, label, _ in present)
    body = "".join(f'<section id="{sid}">{content}</section>' for sid, _, content in present)
    title = f"logilens · {Path(report.file).name}"
    return (f'<!doctype html><html lang="{_e(lang)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)}</title>'
            f'<style>{CSS}</style></head><body><div class="page"><aside class="toc"><div class="brand">logilens</div>'
            f"<ol>{toc}</ol></aside><main>{_header(report, lang)}{body}"
            f"<footer>logilens {_e(report.tool_version)} · {_e(report.generated_at)}</footer>"
            "</main></div></body></html>\n")


def _badge(v: Verdict, lang: str) -> str:
    return f'<span class="status s-{VERDICT_CLASS[v]}">{_e(verdict_label(v, lang).capitalize())}</span>'


def _table(header: list[str], rows: list[list[str]], classes: list[str] | None = None,
           num: frozenset[int] | set[int] = frozenset()) -> str:
    head = "".join(f'<th class="num">{h}</th>' if i in num else f"<th>{h}</th>" for i, h in enumerate(header))
    body = []
    for k, row in enumerate(rows):
        cls = f' class="{classes[k]}"' if classes and classes[k] else ""
        cells = "".join(f'<td class="num">{c}</td>' if i in num else f"<td>{c}</td>" for i, c in enumerate(row))
        body.append(f"<tr{cls}>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _header(report: Report, lang: str) -> str:
    spec = _e(Path(report.spec.path).name) if report.spec else f'<span class="muted">{_e(t("ui.no_spec", lang))}</span>'
    facts = [
        (t("ui.verdict", lang), _badge(report.overall, lang)),
        *_key_results(report, lang),
        (t("ui.spec", lang), spec),
        (t("ui.io", lang), _e(t("ui.io_value", lang, n_in=len(report.inputs), ins=" ".join(report.inputs),
                                n_out=len(report.outputs), outs=" ".join(report.outputs)))),
        (t("ui.components", lang), _e(", ".join(f"{k} ×{n}" for k, n in report.stats.items()))),
        (t("ui.type", lang), _e(t("ui.sequential_kind" if report.is_sequential else "ui.combinational_kind", lang))),
        (t("ui.engine", lang), _e(f"Logisim {report.source_version} · {t('ui.backend', lang)} {report.backend}")),
    ]
    rows = "".join(f"<tr><th>{_e(k)}</th><td>{v}</td></tr>" for k, v in facts)
    notes = "".join(f"<li>{_e(msg(n, lang))}</li>" for n in report.notes)
    return (f'<header class="doc"><div class="kicker">logilens · {_e(t("ui.report_title", lang))}</div>'
            f'<h1>{_e(Path(report.file).name)}</h1><div class="sub">{_e(t("ui.circuit", lang))} '
            f'<code>{_e(report.circuit)}</code></div><table class="facts"><tbody>{rows}</tbody></table>'
            f'{f"<ul class=muted>{notes}</ul>" if notes else ""}</header>')


def _key_results(report: Report, lang: str) -> list[tuple[str, str]]:
    """One line each for the wiring check, the specification and every output group."""
    out = []
    issues = report.lint.issues
    if not issues:
        out.append((t("ui.lint", lang), f'<span class="s-ok">{_e(t("ui.lint_clean", lang))}</span>'))
    else:
        parts = [f'<span class="sev-{sev}">{_e(t(f"severity.{sev}", lang).capitalize())}: {n}</span>'
                 for sev in ("error", "warning", "info") if (n := sum(1 for i in issues if i.severity.value == sev))]
        out.append((t("ui.lint", lang), ", ".join(parts)))
    if report.spec is not None:
        spec = report.spec
        counts = spec.rows_ok_by_output_group or spec.rows_ok_by_group
        cls = "s-ok" if all(n == spec.rows_checked for n in counts.values()) else "s-bad"
        worst = min(counts.values(), default=spec.rows_checked)
        out.append((t("ui.spec_check", lang),
                    f'<span class="{cls}">{worst}/{spec.rows_checked}</span> {_e(t("ui.rows_correct", lang))}'))
    for g in report.groups:
        fr = g.form_result(g.verdict_form)
        best = fr.reference.short() if fr and fr.reference else "—"
        drawn = g.structural.nandnor_short() if g.structural else "—"
        cls = f"v-{VERDICT_CLASS[g.verdict]}"
        text = (f"{_e(drawn)} · {_e(t('ui.optimum', lang))} {_e(best)}" if drawn != best
                else f"{_e(drawn)} = {_e(t('ui.optimum', lang))}")
        out.append((g.title, f'<span class="{cls}">{text}</span>'))
    return out


def _image(report: Report, lang: str) -> str:
    if not report.image_png:
        return ""
    return (f'<h2>{_e(t("ui.circuit_image", lang))}</h2>'
            f'<div class="circuit-box"><img alt="circuit" src="data:image/png;base64,{report.image_png}"></div>')


def _lint(report: Report, lang: str) -> str:
    head = f"<h2>{_e(t('ui.lint', lang))}</h2>"
    if not report.lint.issues:
        return head + f'<p class="s-ok">{_e(t("ui.lint_clean", lang))}</p>'
    rows = []
    for i in report.lint.issues:
        sev = i.severity.value
        rows.append([f'<span class="sev-{sev}">{_e(t(f"severity.{sev}", lang).capitalize())}</span>', f"<code>{_e(i.rule)}</code>",
                     f"<code>{_e(i.component or (str(i.loc) if i.loc else i.circuit))}</code>",
                     f"{_e(issue_message(i, lang))}<br><span class='muted'>→ {_e(issue_fix(i, lang))}</span>"])
    header = [_e(t(k, lang)) for k in ("ui.severity", "ui.rule", "ui.where", "ui.problem_fix")]
    return head + f'<div class="scroll">{_table(header, rows)}</div>'


def _spec(report: Report, lang: str) -> str:
    spec = report.spec
    if spec is None:
        return ""
    counts = spec.rows_ok_by_output_group or spec.rows_ok_by_group
    items = "".join(
        f"<li><b>{_e(name)}</b>: <span style='color:var(--{'ok' if ok == spec.rows_checked else 'bad'})'>"
        f"{'✓' if ok == spec.rows_checked else '✗'} {ok}/{spec.rows_checked}</span> {_e(t('ui.rows_correct', lang))}</li>"
        for name, ok in counts.items())
    mapping = "; ".join(f"{_e(s)} → {_e(', '.join(ls))} <span class='muted'>({_e(t('how.' + spec.how.get(s, ''), lang))})"
                        f"</span>" for s, ls in spec.mapping.items())
    body = f"<ul>{items}</ul><p><span class='muted'>{_e(t('ui.mapping', lang))}:</span> {mapping}</p>"
    if spec.mismatches:
        header = [_e(t(k, lang)) for k in ("ui.inputs_col", "ui.output", "ui.label", "ui.expected", "ui.actual")]
        rows = [[_e(m["inputs"]), _e(m["output"]), _e(m["label"]), _e(m["expected"]), f"<b>{_e(m['actual'])}</b>"]
                for m in spec.mismatches]
        body += f"<h4>{_e(t('ui.mismatches', lang))}</h4>" + _table(header, rows)
    if spec.dc_differences:
        body += f"<p class='muted'>ⓘ {_e(t('ui.dc_differences', lang, count=len(spec.dc_differences)))}</p>"
    return f"<h2>{_e(t('ui.spec_check', lang))}</h2><div class='card'>{body}</div>"


def _summary(report: Report, lang: str) -> str:
    if not report.groups:
        return ""
    rows = []
    for g in report.groups:
        fr = g.form_result(g.verdict_form)
        rows.append([str(g.index), _e(g.title), _e(tech_label(g.technology, lang)),
                     _e(g.structural.short() if g.structural else "—"),
                     _e(g.structural.nandnor_short() if g.structural else "—"),
                     _e(fr.reference.short() if fr and fr.reference else "—"), _badge(g.verdict, lang)])
    header = ["#"] + [_e(t(k, lang)) for k in ("ui.outputs", "ui.technology", "ui.as_drawn", "ui.nandnor_count",
                                               "ui.optimum", "ui.verdict")]
    return (f"<h2>{_e(t('ui.summary', lang))}</h2><div class='card'>{_table(header, rows, num={0, 3, 4, 5})}"
            f"<p class='muted'>{_e(t('ui.summary_caption', lang))}</p></div>")


def _formulas(pairs: list[tuple[str, str]]) -> str:
    return "<pre>" + "\n".join(_e(f"{o} = {f}") for o, f in pairs) + "</pre>"


def _methods(fr: FormResult, lang: str) -> str:
    rows, classes = [], []
    for r in fr.rows:
        rows.append([("✓ " if r.matches_reference else "") + _e(r.method),
                     _e(f"{r.gates}/{r.inputs}" if r.gates is not None else "—"), _e(r.proof or "—"),
                     "✓" if r.verified else "✗", _e(f"{r.runtime_s * 1000:.0f} ms"), _e(r.note)])
        classes.append(" ".join(c for c in ("match" if r.matches_reference else "", "ilp" if r.method == "ilp" else "")
                                if c))
    header = [_e(t(k, lang)) for k in ("ui.method", "ui.cost", "ui.proof", "ui.verified", "ui.time", "ui.note")]
    rob = f"<p class='muted'>{_e(t('ui.robustness', lang))}: {_e(robustness_text(fr, lang))}</p>" if fr.robustness \
        else ""
    return (f"<details><summary>{_e(t('ui.methods_title', lang, form=form_label(fr.form, lang)))} · {len(fr.rows)}"
            f"</summary><div class='scroll'>{_table(header, rows, classes, num={1, 4})}</div>{rob}</details>")


def _group(g: GroupReport, lang: str) -> str:
    cls = VERDICT_CLASS[g.verdict]
    notes = "".join(f"<li>{_e(msg(n, lang))}</li>" for n in g.notes)
    out = [f"<div class='card'><h3>{_e(t('ui.group_title', lang, index=g.index, outputs=g.title))}</h3>",
           (f"<div class='verdict {cls}'><span class='status s-{cls}'></span>{_e(verdict_sentence(g, lang))}"
           f"{f'<ul class=muted>{notes}</ul>' if notes else ''}</div>"),
           f"<p class='muted'>{_e(t('ui.variables', lang))}: {_e(' '.join(g.variables))}</p>"]
    if g.structural is not None:
        out.append(f"<p>{_e(t('ui.implemented', lang))}: <b>{_e(tech_label(g.technology, lang))}</b>, "
                   f"{_e(t('ui.as_drawn', lang))} <b>{_e(g.structural.short())}</b>, {_e(t('ui.nandnor_count', lang))} "
                   f"<b>{_e(g.structural.nandnor_short())}</b></p>")
    if g.implemented_cover is not None:
        out.append(_formulas(cover_formulas(g.implemented_cover)))
    out += [f"<p style='color:var(--beyond)'>◆ {_e(r)}</p>" for r in g.recover_reasons]
    out += [_methods(fr, lang) for fr in g.forms]
    fr = best_form(g)
    if fr is not None and fr.best_cover is not None:
        key = "ui.optimal_cover" if fr.proven else "ui.best_cover"
        out.append(f"<h4>{_e(t(key, lang, form=form_label(fr.form, lang), cost=fr.best_cost.short() if fr.best_cost else '?', method=fr.best_method or '?'))}</h4>")
        out.append("<pre>" + _e("\n".join(line for block in derivations(fr.best_cover) for line in block)) + "</pre>")
        out.append(f"<p class='muted'>{_e(derivation_legend(fr.form, lang))}</p>")
        if fr.kmaps:
            out.append(f"<h4>{_e(t('ui.kmaps', lang, form=form_label(fr.form, lang)))}</h4>")
            out.append("<div class='kmaps'>" + "".join(kmap_svg(v) for v in fr.kmaps) + "</div>")
    if g.implemented_kmaps and g.verdict is Verdict.IMPROVABLE:
        out.append(f"<details><summary>{_e(t('ui.implemented_kmaps', lang))}</summary><div class='kmaps'>"
                   + "".join(kmap_svg(v) for v in g.implemented_kmaps) + "</div></details>")
    out.append("</div>")
    return "".join(out)


def _truth(report: Report, lang: str) -> str:
    truth = report.truth
    if truth is None:
        return ""
    rows = [[str(k), f"<code>{_e(' '.join(bits))}</code>", f"<code>{_e(' '.join(outs))}</code>"]
            for k, (bits, outs) in enumerate(truth.rows)]
    table = _table(["#", _e(" ".join(truth.inputs)), _e(" ".join(truth.outputs))], rows, num={0})
    return (f"<h2>{_e(t('ui.truth_table', lang))}</h2><div class='card'><details><summary>"
            f"{_e(t('ui.show_rows', lang, count=len(truth.rows)))}</summary>{table}</details></div>")


def _seq(report: Report, lang: str) -> str:
    seq = report.seq
    if seq is None:
        return ""
    if seq.status == "ok" and seq.data:
        body = render_seq.html(seq.data, lang)
    else:
        key = "ui.seq_error" if seq.status == "error" else "ui.seq_skipped"
        body = f"<p class='muted'>{_e(t(key, lang, message=seq.message))}</p>"
    return f"<h2>{_e(t('ui.sequential', lang))}</h2><div class='card'>{body}</div>"


def _closing(report: Report, lang: str) -> str:
    recs = "".join(f"<li>{_e(msg(m, lang))}</li>" for m in report.recommendations)
    lims = "".join(f"<li>{_e(msg(m, lang))}</li>" for m in report.limitations)
    return (f"<h2>{_e(t('ui.recommendations', lang))}</h2><div class='card'><ul>{recs}</ul></div>"
            f"<h2>{_e(t('ui.limitations', lang))}</h2><div class='card muted'><ul>{lims}</ul></div>")
