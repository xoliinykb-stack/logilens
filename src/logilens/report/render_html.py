"""Single self-contained HTML report (inline CSS, light/dark via ``prefers-color-scheme``, no scripts needed)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from logilens.core.logic_types import KMapView
from logilens.i18n import issue_fix, issue_message, t
from logilens.kmap.groups import cells_of_group
from logilens.kmap.render_text import legend_lines
from logilens.report import render_seq
from logilens.report.model import FormResult, GroupReport, Report, Verdict
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

COLORS = {
    "red": "#e5484d", "green": "#30a46c", "blue": "#3e63dd", "magenta": "#d6409f", "cyan": "#0894b3",
    "yellow": "#c99a00", "bright_red": "#ff6b6b", "bright_green": "#2fbf71", "bright_blue": "#4c8dff",
    "bright_magenta": "#b65bd6", "bright_cyan": "#14b8c4", "dark_orange": "#e8730c", "purple": "#7c3aed",
    "spring_green3": "#12a37f", "deep_pink3": "#c2185b", "gold3": "#b8860b",
}
VERDICT_CLASS = {
    Verdict.OPTIMAL: "ok", Verdict.IMPROVABLE: "warn", Verdict.BEYOND_TWO_LEVEL: "beyond",
    Verdict.UNPROVEN: "unproven", Verdict.NOT_APPLICABLE: "na",
}

CSS = """
:root{--bg:#f7f7f9;--card:#fff;--fg:#1d1d24;--muted:#6b6b78;--line:#e3e3ea;--accent:#7c3aed;
--ok:#1f9d55;--warn:#c27c0e;--bad:#d64545;--beyond:#b03fb0;--unproven:#2b7bb9;--na:#888;--code:#f1f0f6}
@media (prefers-color-scheme:dark){:root{--bg:#121218;--card:#1b1b24;--fg:#e8e8f0;--muted:#9a9aab;--line:#2c2c3a;
--accent:#a78bfa;--code:#23232f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:19px;margin:32px 0 12px;border-bottom:1px solid var(--line);
padding-bottom:6px}h3{font-size:17px;margin:0 0 10px}h4{font-size:15px;margin:18px 0 8px;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0;
box-shadow:0 1px 2px rgba(0,0,0,.04)}
.brand{color:var(--accent);font-weight:700}.muted{color:var(--muted)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 18px}.kv dt{color:var(--muted)}.kv dd{margin:0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:6px 9px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}td.num,th.num{text-align:right;
font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:700;color:#fff}
.sev-error{background:var(--bad)}.sev-warning{background:var(--warn)}.sev-info{background:var(--unproven)}
.badge{display:inline-block;padding:3px 12px;border-radius:8px;font-weight:700;color:#fff}
.v-ok{background:var(--ok)}.v-warn{background:var(--warn)}.v-beyond{background:var(--beyond)}
.v-unproven{background:var(--unproven)}.v-na{background:var(--na)}
.verdict{border-left:6px solid var(--na);padding:10px 14px;border-radius:8px;background:var(--code);margin:12px 0}
.verdict.ok{border-color:var(--ok)}.verdict.warn{border-color:var(--warn)}.verdict.beyond{border-color:var(--beyond)}
.verdict.unproven{border-color:var(--unproven)}
pre,code{font-family:"SF Mono",Menlo,Consolas,monospace;font-size:13px}pre{background:var(--code);
padding:10px 12px;border-radius:8px;overflow-x:auto}
tr.match td{color:var(--ok);font-weight:600}tr.ilp td:first-child{font-weight:700}
.kmaps{display:flex;flex-wrap:wrap;gap:18px}.kmap{border:1px solid var(--line);border-radius:10px;padding:10px}
.kmap table{width:auto;font-family:"SF Mono",Menlo,monospace}.kmap td,.kmap th{border:1px solid var(--line);
text-align:center;min-width:42px;padding:6px 6px}.kmap th{font-weight:500}.kmap .bar{border:none;color:var(--accent);
font-size:12px;padding:0 4px}.kmap .val{font-weight:700}.kmap .X{color:var(--muted)}
.kmap sup{font-size:10px;font-weight:700;margin-left:2px}.legend{font-size:12px;margin-top:6px}
.legend span{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
ul{margin:6px 0;padding-left:22px}details summary{cursor:pointer;color:var(--muted)}
img.circuit{max-width:100%;background:#fff;border-radius:8px;border:1px solid var(--line)}
"""


def _e(value: object) -> str:
    return escape(str(value))


def render(report: Report, lang: str | None = None) -> str:
    lang = lang or report.lang
    parts = [_header(report, lang), _image(report, lang), _lint(report, lang), _spec(report, lang),
             _summary(report, lang)]
    parts += [_group(g, lang) for g in report.groups]
    parts += [_truth(report, lang), _seq(report, lang), _closing(report, lang)]
    title = f"logilens · {Path(report.file).name}"
    return (f'<!doctype html><html lang="{_e(lang)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)}</title>'
            f"<style>{CSS}</style></head><body><main>{''.join(p for p in parts if p)}"
            f'<p class="muted">logilens {_e(report.tool_version)} · {_e(report.generated_at)}</p>'
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
        (t("ui.file", lang), (f"<code>{_e(Path(report.file).name)}</code> · {_e(t('ui.circuit', lang))} "
                             f"<code>{_e(report.circuit)}</code>")),
        (t("ui.engine", lang), _e(f"Logisim {report.source_version} · {t('ui.backend', lang)} {report.backend}")),
        (t("ui.io", lang), _e(t("ui.io_value", lang, n_in=len(report.inputs), ins=" ".join(report.inputs),
                                n_out=len(report.outputs), outs=" ".join(report.outputs)))),
        (t("ui.components", lang), _e(", ".join(f"{k} ×{n}" for k, n in report.stats.items()))),
        (t("ui.type", lang), _e(t("ui.sequential_kind" if report.is_sequential else "ui.combinational_kind", lang))),
        (t("ui.spec", lang), spec),
        (t("ui.verdict", lang), _badge(report.overall, lang)),
    ]
    rows = "".join(f"<dt>{_e(k)}</dt><dd>{v}</dd>" for k, v in kv)
    notes = "".join(f"<li>{_e(msg(n, lang))}</li>" for n in report.notes)
    return (f'<div class="card"><h1><span class="brand">logilens</span> · {_e(t("ui.report_title", lang))}'
            f'</h1><dl class="kv">{rows}</dl>{f"<ul class=muted>{notes}</ul>" if notes else ""}</div>')


def _image(report: Report, lang: str) -> str:
    if not report.image_png:
        return ""
    return (f'<h2>{_e(t("ui.circuit_image", lang))}</h2><div class="card">'
            f'<img class="circuit" alt="circuit" src="data:image/png;base64,{report.image_png}"></div>')


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
    return head + f'<div class="card">{_table(header, rows)}</div>'


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
    return (f"<h4>{_e(t('ui.methods_title', lang, form=form_label(fr.form, lang)))}</h4>"
            + _table(header, rows, classes, num={1, 4}) + rob)


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
            out.append("<div class='kmaps'>" + "".join(kmap_html(v) for v in fr.kmaps) + "</div>")
    if g.implemented_kmaps and g.verdict is Verdict.IMPROVABLE:
        out.append(f"<details><summary>{_e(t('ui.implemented_kmaps', lang))}</summary><div class='kmaps'>"
                   + "".join(kmap_html(v) for v in g.implemented_kmaps) + "</div></details>")
    out.append("</div>")
    return "".join(out)


def _cell_style(groups: list[tuple[str, tuple[bool, bool, bool, bool]]]) -> str:
    """Tint + inset outline per covering group: edges = (top, right, bottom, left)."""
    if not groups:
        return ""
    shadows = []
    for k, (color, (top, right, bottom, left)) in enumerate(groups):
        w = 3 * (k + 1)
        if top:
            shadows.append(f"inset 0 {w}px 0 0 {color}")
        if bottom:
            shadows.append(f"inset 0 -{w}px 0 0 {color}")
        if left:
            shadows.append(f"inset {w}px 0 0 0 {color}")
        if right:
            shadows.append(f"inset -{w}px 0 0 0 {color}")
    tint = groups[0][0] + "26"
    return f' style="background:{tint};box-shadow:{",".join(shadows)}"' if shadows else f' style="background:{tint}"'


def kmap_html(view: KMapView) -> str:
    """K-map as an HTML table: bars + Gray codes on the axes, tinted cells, group outlines, legend."""
    ncols = len(view.col_codes)
    cover: dict[tuple[int, int], list[tuple[str, tuple[bool, bool, bool, bool]]]] = {}
    labels: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for g in view.groups:
        color = COLORS.get(g.color, "#7c3aed")
        for r0, c0, r1, c1 in g.rects:
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    cover.setdefault((r, c), []).append((color, (r == r0, c == c1, r == r1, c == c0)))
        for cell in cells_of_group(view, g):
            labels.setdefault(cell, []).append((g.label, color))
    nbars = len(view.row_bars)
    head = []
    for var, idx in view.col_bars.items():
        bar_cells = "".join(f"<th class='bar'>{'━━' if c in idx else ''}</th>" for c in range(ncols))
        head.append(f"<tr><th class='bar' colspan='{nbars}'></th><th class='bar'>{_e(var)}</th>{bar_cells}</tr>")
    corner = _e("".join(view.row_vars) + "\\" + "".join(view.col_vars))
    codes = "".join(f"<th>{_e(code)}</th>" for code in view.col_codes)
    head.append(f"<tr><th class='bar' colspan='{nbars}'></th><th>{corner}</th>{codes}</tr>")
    body = []
    for r, code in enumerate(view.row_codes):
        bars = "".join(f"<th class='bar' title='{_e(v)}'>{'┃' if r in idx else ''}</th>" for v, idx in view.row_bars.items())
        cells = []
        for c in range(ncols):
            value = view.values[r][c]
            sup = "".join(f"<sup style='color:{col}'>{_e(lab)}</sup>" for lab, col in labels.get((r, c), []))
            cells.append(f"<td{_cell_style(cover.get((r, c), []))}><span class='val {value}'>{_e(value)}</span>{sup}</td>")
        body.append(f"<tr>{bars}<th>{_e(code)}</th>{''.join(cells)}</tr>")
    row_names = " ".join(view.row_bars)
    legend = "".join(f"<div><span style='background:{COLORS.get(g.color, '#7c3aed')}'></span>{_e(line)}</div>"
                     for g, line in zip(view.groups, legend_lines(view, "ascii")))
    return (f"<div class='kmap'><b>{_e(view.output)}</b> <span class='muted'>({_e(view.form.value)}; ┃ = "
            f"{_e(row_names)})</span><table>{''.join(head)}{''.join(body)}</table><div class='legend'>{legend}</div></div>")


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
