"""Single self-contained HTML report (inline CSS, light/dark via ``prefers-color-scheme``, no scripts needed)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from logilens.i18n import issue_fix, issue_message, t
from logilens.report import render_seq
from logilens.report.model import FormResult, GroupReport, Report, Verdict
from logilens.report.svg import kmap_svg
from logilens.report.text import (
    VERDICT_ICON,
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
:root{--bg:#f6f6f8;--card:#fff;--fg:#1c1c22;--muted:#6a6a78;--line:#e4e4ec;--accent:#6d4aff;--accent-soft:#efeaff;
--ok:#1f9d55;--warn:#c27c0e;--bad:#d64545;--beyond:#b03fb0;--unproven:#2b7bb9;--na:#8a8a96;--code:#f2f1f7;
--shadow:0 1px 2px rgba(20,20,40,.05),0 4px 16px rgba(20,20,40,.04)}
@media (prefers-color-scheme:dark){:root{--bg:#111116;--card:#191921;--fg:#e9e9f1;--muted:#9898a8;--line:#2a2a36;
--accent:#a48bff;--accent-soft:#2a2440;--code:#20202a;--shadow:none}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:64px}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",
Inter,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
nav.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 82%,transparent);
backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
nav.top div{max-width:1180px;margin:0 auto;padding:10px 20px;display:flex;gap:6px;align-items:center;overflow-x:auto}
nav.top b{color:var(--accent);margin-right:10px;white-space:nowrap}
nav.top a{color:var(--muted);text-decoration:none;font-size:13.5px;padding:4px 10px;border-radius:999px;white-space:nowrap}
nav.top a:hover{background:var(--accent-soft);color:var(--fg)}
main{max-width:1180px;margin:0 auto;padding:24px 20px 72px}
h1{font-size:26px;line-height:1.2;margin:0}h2{font-size:19px;margin:40px 0 12px}
h3{font-size:17px;margin:0 0 12px}h4{font-size:13px;margin:22px 0 10px;color:var(--muted);text-transform:uppercase;
letter-spacing:.04em}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin:12px 0;
box-shadow:var(--shadow)}
.hero{display:grid;gap:18px}.hero .title{display:flex;flex-wrap:wrap;gap:12px 16px;align-items:center}
.hero .file{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:14px;color:var(--muted)}
.muted{color:var(--muted)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:5px 20px;margin:0}.kv dt{color:var(--muted)}.kv dd{margin:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.tile{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--bg)}
.tile .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.tile .v{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px}
.tile .s{font-size:12.5px;color:var(--muted)}
.tile.ok .v{color:var(--ok)}.tile.warn .v{color:var(--warn)}.tile.bad .v{color:var(--bad)}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px 10px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600;font-size:12.5px;text-transform:uppercase;
letter-spacing:.03em}tbody tr:last-child td{border-bottom:none}td.num,th.num{text-align:right;
font-variant-numeric:tabular-nums}.scroll{overflow-x:auto}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:11.5px;font-weight:700;color:#fff;
letter-spacing:.02em}.sev-error{background:var(--bad)}.sev-warning{background:var(--warn)}.sev-info{background:var(--unproven)}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:999px;font-weight:700;
font-size:13px;color:#fff;letter-spacing:.02em}
.v-ok{background:var(--ok)}.v-warn{background:var(--warn)}.v-beyond{background:var(--beyond)}
.v-unproven{background:var(--unproven)}.v-na{background:var(--na)}
.verdict{border-left:4px solid var(--na);padding:12px 16px;border-radius:10px;background:var(--code);margin:12px 0}
.verdict.ok{border-color:var(--ok)}.verdict.warn{border-color:var(--warn)}.verdict.beyond{border-color:var(--beyond)}
.verdict.unproven{border-color:var(--unproven)}.verdict ul{margin:8px 0 0}
pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}
pre{background:var(--code);padding:12px 14px;border-radius:10px;overflow-x:auto;line-height:1.5}
code{background:var(--code);padding:1px 5px;border-radius:5px}pre code{background:none;padding:0}
tr.match td{color:var(--ok);font-weight:600}tr.ilp td:first-child{font-weight:700}
.kmaps{display:flex;flex-wrap:wrap;gap:16px}
figure.kmap{margin:0;border:1px solid var(--line);border-radius:12px;padding:12px 14px 10px;background:var(--bg)}
figure.kmap svg{display:block;max-width:100%;height:auto}
ul.legend{list-style:none;padding:0;margin:8px 0 0;font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}
ul.legend span{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
ul{margin:6px 0;padding-left:22px}
details{margin:10px 0}details>summary{cursor:pointer;color:var(--muted);font-weight:600;list-style:none;
padding:6px 0}details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"▸";display:inline-block;width:16px;transition:transform .15s}
details[open]>summary::before{transform:rotate(90deg)}
.circuit-box{max-height:560px;overflow:auto;background:#fff;border-radius:10px;border:1px solid var(--line)}
.circuit-box img{display:block;max-width:100%;height:auto;margin:0 auto}
svg.timing,.graph svg{display:block;max-width:100%;height:auto}.graph{overflow-x:auto}
footer{margin-top:48px;font-size:12.5px;color:var(--muted);text-align:center}
@media print{nav.top{display:none}body{background:#fff}.card{box-shadow:none;break-inside:avoid}
details{display:block}.circuit-box{max-height:none}}
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
    nav = "".join(f'<a href="#{sid}">{_e(label)}</a>' for sid, label, _ in present)
    body = "".join(f'<section id="{sid}">{content}</section>' for sid, _, content in present)
    title = f"logilens · {Path(report.file).name}"
    return (f'<!doctype html><html lang="{_e(lang)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)}</title>'
            f'<style>{CSS}</style></head><body><nav class="top"><div><b>logilens</b>{nav}</div></nav>'
            f"<main>{_header(report, lang)}{body}"
            f"<footer>logilens {_e(report.tool_version)} · {_e(report.generated_at)}</footer>"
            "</main></body></html>\n")


def _badge(v: Verdict, lang: str) -> str:
    return f'<span class="badge v-{VERDICT_CLASS[v]}">{VERDICT_ICON[v]} {_e(verdict_label(v, lang))}</span>'


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
    kv = [
        (t("ui.engine", lang), _e(f"Logisim {report.source_version} · {t('ui.backend', lang)} {report.backend}")),
        (t("ui.io", lang), _e(t("ui.io_value", lang, n_in=len(report.inputs), ins=" ".join(report.inputs),
                                n_out=len(report.outputs), outs=" ".join(report.outputs)))),
        (t("ui.components", lang), _e(", ".join(f"{k} ×{n}" for k, n in report.stats.items()))),
        (t("ui.type", lang), _e(t("ui.sequential_kind" if report.is_sequential else "ui.combinational_kind", lang))),
        (t("ui.spec", lang), spec),
    ]
    rows = "".join(f"<dt>{_e(k)}</dt><dd>{v}</dd>" for k, v in kv)
    notes = "".join(f"<li>{_e(msg(n, lang))}</li>" for n in report.notes)
    return (f'<div class="card hero"><div class="title"><h1>{_e(Path(report.file).name)}</h1>'
            f'{_badge(report.overall, lang)}<span class="file">{_e(t("ui.circuit", lang))} {_e(report.circuit)}'
            f'</span></div>{_tiles(report, lang)}<dl class="kv">{rows}</dl>'
            f'{f"<ul class=muted>{notes}</ul>" if notes else ""}</div>')


def _tiles(report: Report, lang: str) -> str:
    tiles = []
    errors = sum(1 for i in report.lint.issues if i.severity.value == "error")
    warnings = sum(1 for i in report.lint.issues if i.severity.value == "warning")
    state = "bad" if errors else "warn" if warnings else "ok"
    value = "✓ 0" if not report.lint.issues else f"{errors} · {warnings}"
    sub = f"{t('severity.error', lang)} · {t('severity.warning', lang)}" if report.lint.issues else ""
    tiles.append((state, t("ui.lint", lang), value, sub))
    if report.spec is not None:
        spec = report.spec
        counts = spec.rows_ok_by_output_group or spec.rows_ok_by_group
        ok = all(n == spec.rows_checked for n in counts.values())
        worst = min(counts.values(), default=spec.rows_checked)
        tiles.append(("ok" if ok else "bad", t("ui.spec_check", lang), f"{worst}/{spec.rows_checked}",
                      t("ui.rows_correct", lang)))
    for g in report.groups:
        fr = g.form_result(g.verdict_form)
        best = fr.reference.short() if fr and fr.reference else "—"
        drawn = g.structural.nandnor_short() if g.structural else "—"
        state = {Verdict.OPTIMAL: "ok", Verdict.IMPROVABLE: "warn"}.get(g.verdict, "")
        tiles.append((state, g.title, drawn if drawn == best else f"{drawn} → {best}",
                      f"{t('ui.nandnor_count', lang)} → {t('ui.optimum', lang)}"))
    return '<div class="tiles">' + "".join(
        f'<div class="tile {st}"><div class="k">{_e(k)}</div><div class="v">{_e(v)}</div>'
        f'<div class="s">{_e(sub)}</div></div>' for st, k, v, sub in tiles) + "</div>"


def _image(report: Report, lang: str) -> str:
    if not report.image_png:
        return ""
    return (f'<h2>{_e(t("ui.circuit_image", lang))}</h2><div class="card">'
            f'<div class="circuit-box"><img alt="circuit" src="data:image/png;base64,{report.image_png}"></div></div>')


def _lint(report: Report, lang: str) -> str:
    head = f"<h2>{_e(t('ui.lint', lang))}</h2>"
    if not report.lint.issues:
        return head + f'<div class="card"><b style="color:var(--ok)">✓ {_e(t("ui.lint_clean", lang))}</b></div>'
    rows = []
    for i in report.lint.issues:
        sev = i.severity.value
        rows.append([f'<span class="pill sev-{sev}">{_e(t(f"severity.{sev}", lang))}</span>', f"<b>{_e(i.rule)}</b>",
                     f"<code>{_e(i.component or (str(i.loc) if i.loc else i.circuit))}</code>",
                     f"{_e(issue_message(i, lang))}<br><span class='muted'>→ {_e(issue_fix(i, lang))}</span>"])
    header = [_e(t(k, lang)) for k in ("ui.severity", "ui.rule", "ui.where", "ui.problem_fix")]
    counts = "".join(f'<span class="pill sev-{sev}">{n} × {_e(t(f"severity.{sev}", lang))}</span>'
                     for sev in ("error", "warning", "info")
                     if (n := sum(1 for i in report.lint.issues if i.severity.value == sev)))
    return head + f'<div class="card"><div class="chips">{counts}</div><div class="scroll">{_table(header, rows)}</div></div>'


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
           (f"<div class='verdict {cls}'>{_badge(g.verdict, lang)} {_e(verdict_sentence(g, lang))}"
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
