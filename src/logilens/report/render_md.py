"""Markdown rendering of a :class:`Report` (GitHub-flavoured tables, K-maps as code blocks)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from logilens.i18n import issue_fix, issue_message, t
from logilens.kmap.render_text import render_plain
from logilens.report import render_seq
from logilens.report.model import FormResult, GroupReport, Report
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


def _esc(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    out = ["| " + " | ".join(_esc(h) for h in header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(_esc(c) for c in row) + " |" for row in rows]
    return out + [""]


def render(report: Report, lang: str | None = None, *, show_table: bool = True) -> str:
    lang = lang or report.lang
    lines: list[str] = []
    lines += _header(report, lang)
    lines += _lint(report, lang)
    if report.spec is not None:
        lines += _spec(report, lang)
    if report.groups:
        lines += _summary(report, lang)
    for g in report.groups:
        lines += _group(g, lang)
    if show_table and report.truth is not None:
        lines += _truth(report, lang)
    if report.seq is not None:
        lines += [f"## {t('ui.sequential', lang)}", ""]
        lines += render_seq.markdown(report.seq.data, lang) if report.seq.data else [
            t("ui.seq_error" if report.seq.status == "error" else "ui.seq_skipped", lang,
              message=report.seq.message), ""]
    lines += [f"## {t('ui.recommendations', lang)}", ""] + [f"- {msg(m, lang)}" for m in report.recommendations] + [""]
    lines += [f"## {t('ui.limitations', lang)}", ""] + [f"- {msg(m, lang)}" for m in report.limitations] + [""]
    lines.append(f"<sub>logilens {report.tool_version} · {report.generated_at}</sub>")
    return "\n".join(lines) + "\n"


def _header(report: Report, lang: str) -> list[str]:
    v = report.overall
    rows = [
        [t("ui.file", lang), f"`{Path(report.file).name}` ({t('ui.circuit', lang)} `{report.circuit}`)"],
        [t("ui.engine", lang), f"Logisim {report.source_version} · {t('ui.backend', lang)} {report.backend}"],
        [t("ui.io", lang), t("ui.io_value", lang, n_in=len(report.inputs), ins=" ".join(report.inputs),
                             n_out=len(report.outputs), outs=" ".join(report.outputs))],
        [t("ui.components", lang), ", ".join(f"{k} ×{n}" for k, n in report.stats.items())],
        [t("ui.type", lang), t("ui.sequential_kind" if report.is_sequential else "ui.combinational_kind", lang)],
        [t("ui.spec", lang), Path(report.spec.path).name if report.spec else t("ui.no_spec", lang)],
        [t("ui.verdict", lang), f"**{VERDICT_ICON[v]} {verdict_label(v, lang)}**"],
    ]
    out = [f"# logilens · {t('ui.report_title', lang)}", ""] + _table(["", ""], rows)
    out += [f"> {msg(n, lang)}" for n in report.notes] + ([""] if report.notes else [])
    return out


def _lint(report: Report, lang: str) -> list[str]:
    out = [f"## {t('ui.lint', lang)}", ""]
    if not report.lint.issues:
        return out + [f"✓ {t('ui.lint_clean', lang)}", ""]
    rows = [[t(f"severity.{i.severity.value}", lang), i.rule, i.component or (str(i.loc) if i.loc else i.circuit),
             issue_message(i, lang), issue_fix(i, lang)] for i in report.lint.issues]
    out += _table([t("ui.severity", lang), t("ui.rule", lang), t("ui.where", lang), t("ui.problem", lang),
                   t("ui.fix", lang)], rows)
    return out


def _spec(report: Report, lang: str) -> list[str]:
    spec = report.spec
    assert spec is not None
    out = [f"## {t('ui.spec_check', lang)}", ""]
    counts = spec.rows_ok_by_output_group or spec.rows_ok_by_group
    out += [f"- **{name}**: {'✓' if ok == spec.rows_checked else '✗'} {ok}/{spec.rows_checked} "
            f"{t('ui.rows_correct', lang)}" for name, ok in counts.items()]
    out += ["", f"{t('ui.mapping', lang)}: " + "; ".join(
        f"{s} → {', '.join(ls)} ({t('how.' + spec.how.get(s, ''), lang)})" for s, ls in spec.mapping.items()), ""]
    if spec.mismatches:
        out += [f"### {t('ui.mismatches', lang)}", ""]
        out += _table([t("ui.inputs_col", lang), t("ui.output", lang), t("ui.label", lang), t("ui.expected", lang),
                       t("ui.actual", lang)],
                      [[m["inputs"], m["output"], m["label"], m["expected"], m["actual"]] for m in spec.mismatches])
    if spec.dc_differences:
        out += [t("ui.dc_differences", lang, count=len(spec.dc_differences)), ""]
    return out


def _summary(report: Report, lang: str) -> list[str]:
    rows = []
    for g in report.groups:
        fr = g.form_result(g.verdict_form)
        rows.append([g.index, g.title, tech_label(g.technology, lang), g.structural.short() if g.structural else "—",
                     g.structural.nandnor_short() if g.structural else "—",
                     fr.reference.short() if fr and fr.reference else "—",
                     f"{VERDICT_ICON[g.verdict]} {verdict_label(g.verdict, lang)}"])
    header = ["#", t("ui.outputs", lang), t("ui.technology", lang), t("ui.as_drawn", lang),
              t("ui.nandnor_count", lang), t("ui.optimum", lang), t("ui.verdict", lang)]
    return [f"## {t('ui.summary', lang)}", ""] + _table(header, rows) + [f"_{t('ui.summary_caption', lang)}_", ""]


def _methods(fr: FormResult, lang: str) -> list[str]:
    rows = [[("✓ " if r.matches_reference else "") + r.method, f"{r.gates}/{r.inputs}" if r.gates is not None else "—",
             r.proof or "—", "✓" if r.verified else "✗", f"{r.runtime_s * 1000:.0f} ms", r.note] for r in fr.rows]
    header = [t("ui.method", lang), t("ui.cost", lang), t("ui.proof", lang), t("ui.verified", lang),
              t("ui.time", lang), t("ui.note", lang)]
    title = f"{t('ui.methods_title', lang, form=form_label(fr.form, lang))} · {len(fr.rows)}"
    out = ["<details>", f"<summary>{title}</summary>", ""] + _table(header, rows)
    if fr.robustness:
        out += [f"{t('ui.robustness', lang)}: " + robustness_text(fr, lang), ""]
    return out + ["</details>", ""]


def _group(g: GroupReport, lang: str) -> list[str]:
    out = [f"### {t('ui.group_title', lang, index=g.index, outputs=g.title)}", ""]
    out += [f"**{VERDICT_ICON[g.verdict]} {verdict_label(g.verdict, lang)}** — {verdict_sentence(g, lang)}", ""]
    out += [f"- {msg(n, lang)}" for n in g.notes] + ([""] if g.notes else [])
    if g.structural is not None:
        out += [(f"{t('ui.implemented', lang)}: {tech_label(g.technology, lang)}, {t('ui.as_drawn', lang)} "
                f"**{g.structural.short()}**, {t('ui.nandnor_count', lang)} **{g.structural.nandnor_short()}**"), ""]
    if g.implemented_cover is not None:
        out += ["```"] + [f"{o} = {f}" for o, f in cover_formulas(g.implemented_cover, "ascii")] + ["```", ""]
    out += [f"> {r}" for r in g.recover_reasons] + ([""] if g.recover_reasons else [])
    for fr in g.forms:
        out += _methods(fr, lang)
    best = best_form(g)
    if best is not None and best.best_cover is not None:
        key = "ui.optimal_cover" if best.proven else "ui.best_cover"
        out += [f"#### {t(key, lang, form=form_label(best.form, lang), cost=best.best_cost.short() if best.best_cost else '?', method=best.best_method or '?')}",
                "", "```"]
        out += [line for block in derivations(best.best_cover) for line in block] + ["```", ""]
        out += [f"*{derivation_legend(best.form, lang)}*", ""]
        if best.kmaps:
            out += [f"#### {t('ui.kmaps', lang, form=form_label(best.form, lang))}", ""]
            out += ["```"] + ["\n\n".join(render_plain(v) for v in best.kmaps)] + ["```", ""]
    return out


def _truth(report: Report, lang: str) -> list[str]:
    truth = report.truth
    assert truth is not None
    rows = [[k, " ".join(bits), " ".join(outs)] for k, (bits, outs) in enumerate(truth.rows)]
    table = _table(["#", " ".join(truth.inputs), " ".join(truth.outputs)], rows)
    return ([f"## {t('ui.truth_table', lang)}", "", "<details>",
             f"<summary>{t('ui.show_rows', lang, count=len(truth.rows))}</summary>", ""] + table + ["</details>", ""])
