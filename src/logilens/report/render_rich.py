"""Terminal report with ``rich``: header, lint issues, spec check, verdict summary, per-group details, K-maps."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from logilens.i18n import issue_fix, issue_message, t
from logilens.kmap.render_text import render_rich as kmap_table
from logilens.lint.issue import LintIssue
from logilens.report import render_seq
from logilens.report.model import FormResult, GroupReport, Report, SeqSection, SpecSection, Verdict
from logilens.report.text import (
    SEVERITY_STYLE,
    VERDICT_ICON,
    VERDICT_STYLE,
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

MAX_LINT_ROWS = 40
MAX_MISMATCH_ROWS = 20


def render(report: Report, console: Console, *, lang: str | None = None, show_table: bool = False,
           show_kmaps: bool = True) -> None:
    """Print the full report."""
    for part in renderables(report, lang or report.lang, show_table=show_table, show_kmaps=show_kmaps):
        console.print(part)


def renderables(report: Report, lang: str, *, show_table: bool = False,
                show_kmaps: bool = True) -> Iterator[RenderableType]:
    yield header(report, lang)
    if report.notes:
        yield Text("\n".join("• " + msg(n, lang) for n in report.notes), style="dim")
    yield section_title(t("ui.lint", lang))
    yield lint_view(report.lint.issues, lang, only=report.lint.only, compact=True)
    if report.spec is not None:
        yield section_title(t("ui.spec_check", lang))
        yield spec_view(report.spec, lang)
    if report.groups:
        yield section_title(t("ui.summary", lang))
        yield summary_table(report, lang)
    for g in report.groups:
        yield from group_view(g, lang, show_kmaps=show_kmaps)
    if show_table and report.truth is not None:
        yield section_title(t("ui.truth_table", lang))
        yield truth_table_view(report, lang)
    if report.seq is not None:
        yield section_title(t("ui.sequential", lang))
        yield seq_view(report.seq, lang)
    yield closing_panels(report, lang)


def section_title(text: str) -> Rule:
    return Rule(Text(text, style="bold"), style="grey50", align="left")


# ------------------------------------------------------------------ header


def verdict_badge(v: Verdict, lang: str) -> Text:
    return Text(f"{VERDICT_ICON[v]} {verdict_label(v, lang)} ", style=VERDICT_STYLE[v] + " reverse")


def _io_line(names: list[str], limit: int = 10) -> str:
    shown = " ".join(names[:limit])
    return shown + (f" … (+{len(names) - limit})" if len(names) > limit else "")


def header(report: Report, lang: str) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column()
    grid.add_row(t("ui.file", lang), f"{Path(report.file).name}  [dim]({t('ui.circuit', lang)} {report.circuit})[/]")
    grid.add_row(t("ui.engine", lang), f"Logisim {report.source_version} · {t('ui.backend', lang)} "
                                       f"[bold]{report.backend}[/]")
    grid.add_row(t("ui.io", lang), t("ui.io_value", lang, n_in=len(report.inputs), ins=_io_line(report.inputs),
                                     n_out=len(report.outputs), outs=_io_line(report.outputs)))
    stats = ", ".join(f"{name} ×{k}" for name, k in list(report.stats.items())[:8])
    grid.add_row(t("ui.components", lang), stats or "—")
    kind = t("ui.sequential_kind" if report.is_sequential else "ui.combinational_kind", lang)
    grid.add_row(t("ui.type", lang), kind)
    if report.spec is not None:
        spec = t("ui.spec_value", lang, name=Path(report.spec.path).name, kind=t(f"spec.kind.{report.spec.kind}", lang),
                 rows=report.spec.listed_rows)
    else:
        spec = f"[yellow]{t('ui.no_spec', lang)}[/]"
    grid.add_row(t("ui.spec", lang), spec)
    grid.add_row(t("ui.verdict", lang), verdict_badge(report.overall, lang))
    title = Text.assemble(("logilens", "bold magenta"), (f" · {t('ui.report_title', lang)}", "bold"))
    return Panel(grid, title=title, title_align="left", border_style="magenta", box=box.ROUNDED, padding=(1, 2))


# ------------------------------------------------------------------ lint


def _compacted(issues: list[LintIssue], per_kind: int) -> list[LintIssue | tuple[str, str, int]]:
    """Keep at most ``per_kind`` issues per (rule, message kind); the rest become one ``(rule, key, count)`` row."""
    counts = Counter((i.rule, i.msg_key) for i in issues)
    shown: Counter[tuple[str, str]] = Counter()
    out: list[LintIssue | tuple[str, str, int]] = []
    for issue in issues:
        key = (issue.rule, issue.msg_key)
        shown[key] += 1
        if shown[key] <= per_kind:
            out.append(issue)
        elif shown[key] == per_kind + 1:
            out.append((issue.rule, issue.msg_key, counts[key] - per_kind))
    return out


def lint_view(issues: list[LintIssue], lang: str, *, only: str | None = None, compact: bool = False) -> RenderableType:
    """Issues table (errors first); ``compact`` folds long runs of the same kind of issue."""
    problems = [i for i in issues if i.is_problem]
    infos = [i for i in issues if not i.is_problem]
    if not issues:
        return Text("✓ " + t("ui.lint_clean", lang), style="bold green")
    table = Table(box=box.SIMPLE_HEAVY, show_edge=False, expand=True, pad_edge=False)
    table.add_column(t("ui.severity", lang), no_wrap=True)
    table.add_column(t("ui.rule", lang), no_wrap=True, style="bold")
    table.add_column(t("ui.where", lang), no_wrap=True, style="cyan")
    table.add_column(t("ui.problem_fix", lang), ratio=1)
    rows = _compacted(problems + infos, 2) if compact else list(problems + infos)
    for item in rows[:MAX_LINT_ROWS]:
        if isinstance(item, tuple):
            table.add_row("", item[0], "", Text(t("ui.more_same", lang, count=item[2], rule=item[0]), style="dim"))
            continue
        sev = item.severity.value
        where = item.component or (str(item.loc) if item.loc else item.circuit)
        body = Text(issue_message(item, lang))
        body.append("\n→ " + issue_fix(item, lang), style="dim")
        table.add_row(Text(t(f"severity.{sev}", lang), style=SEVERITY_STYLE[sev]), item.rule, where, body)
    parts: list[RenderableType] = [table]
    hidden = len(rows) - MAX_LINT_ROWS
    if hidden > 0:
        parts.append(Text(t("ui.more_rows", lang, count=hidden), style="dim"))
    counts = t("ui.lint_counts", lang, errors=sum(i.severity.value == "error" for i in issues),
               warnings=sum(i.severity.value == "warning" for i in issues), infos=len(infos))
    style = "bold red" if problems else "bold green"
    parts.append(Text(("✗ " if problems else "✓ ") + counts, style=style))
    if only:
        parts.append(Text(t("ui.gate_set", lang, only=only.upper()), style="dim"))
    return Group(*parts)


# ------------------------------------------------------------------ spec


def spec_view(spec: SpecSection, lang: str) -> RenderableType:
    parts: list[RenderableType] = []
    counts = spec.rows_ok_by_output_group or spec.rows_ok_by_group
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    for name, ok in counts.items():
        good = ok == spec.rows_checked
        mark = Text(f"{'✓' if good else '✗'} {ok}/{spec.rows_checked}", style="bold green" if good else "bold red")
        grid.add_row(name, Text.assemble(mark, (" " + t("ui.rows_correct", lang), "")))
    parts.append(grid)
    mapping = "  ".join(f"{s} → {', '.join(labels)} [dim]({t('how.' + spec.how.get(s, ''), lang)})[/]"
                        for s, labels in spec.mapping.items())
    parts.append(Text.from_markup(f"[dim]{t('ui.mapping', lang)}:[/] {mapping}"))
    if spec.unmapped:
        parts.append(Text(t("ui.unmapped", lang, outputs=", ".join(spec.unmapped)), style="yellow"))
    if spec.mismatches:
        parts.append(mismatch_table(spec, lang))
    if spec.dc_differences:
        parts.append(Text("ⓘ " + t("ui.dc_differences", lang, count=len(spec.dc_differences)), style="cyan"))
    parts.extend(Text(n, style="dim") for n in spec.notes)
    return Group(*parts)


def mismatch_table(spec: SpecSection, lang: str) -> Table:
    table = Table(title=t("ui.mismatches", lang), box=box.SIMPLE, title_style="bold red", title_justify="left")
    for col in ("ui.inputs_col", "ui.output", "ui.label", "ui.expected", "ui.actual"):
        table.add_column(t(col, lang))
    for m in spec.mismatches[:MAX_MISMATCH_ROWS]:
        table.add_row(m["inputs"], m["output"], m["label"], m["expected"], Text(m["actual"], style="bold red"))
    if len(spec.mismatches) > MAX_MISMATCH_ROWS:
        table.caption = t("ui.more_rows", lang, count=len(spec.mismatches) - MAX_MISMATCH_ROWS)
    return table


# ------------------------------------------------------------------ summary + groups


def summary_table(report: Report, lang: str) -> Table:
    table = Table(box=box.ROUNDED, header_style="bold", expand=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column(t("ui.outputs", lang))
    table.add_column(t("ui.technology", lang))
    table.add_column(t("ui.as_drawn", lang), justify="right", no_wrap=True)
    table.add_column(t("ui.nandnor_count", lang), justify="right", no_wrap=True)
    table.add_column(t("ui.optimum", lang), justify="right", no_wrap=True)
    table.add_column("Δ", justify="right", no_wrap=True)
    table.add_column(t("ui.verdict", lang), overflow="fold")
    for g in report.groups:
        fr = g.form_result(g.verdict_form)
        ref = fr.reference.short() if fr and fr.reference else "—"
        delta = f"−{g.delta.gates}/−{g.delta.inputs}" if g.delta and (g.delta.gates or g.delta.inputs) else "—"
        table.add_row(str(g.index), g.title, tech_label(g.technology, lang),
                      g.structural.short() if g.structural else "—",
                      g.structural.nandnor_short() if g.structural else "—", ref,
                      Text(delta, style="yellow" if delta != "—" else ""),
                      Text(f"{VERDICT_ICON[g.verdict]} {verdict_label(g.verdict, lang)}", style=VERDICT_STYLE[g.verdict]))
    table.caption = t("ui.summary_caption", lang)
    return table


def formulas_grid(cover_lines: list[tuple[str, str]]) -> Table:
    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold", justify="right")
    grid.add_column()
    for name, formula in cover_lines:
        grid.add_row(name, "= " + formula)
    return grid


def group_view(g: GroupReport, lang: str, *, show_kmaps: bool = True) -> Iterator[RenderableType]:
    yield Rule(Text(t("ui.group_title", lang, index=g.index, outputs=g.title), style="bold cyan"),
               style="cyan", align="left")
    source = t("ui.source_spec" if g.function_source == "spec" else "ui.source_circuit", lang,
               dc=max(g.dc_count.values(), default=0))
    yield Text.from_markup(f"[dim]{t('ui.variables', lang)}:[/] {' '.join(g.variables) or '—'}   [dim]·[/] {source}")
    yield implemented_view(g, lang)
    for fr in g.forms:
        yield methods_table(fr, lang)
        if fr.robustness:
            yield Text(t("ui.robustness", lang) + ": " + robustness_text(fr, lang), style="dim")
    yield verdict_panel(g, lang)
    yield from optimum_view(g, lang, show_kmaps=show_kmaps)


def implemented_view(g: GroupReport, lang: str) -> RenderableType:
    parts: list[RenderableType] = []
    if g.structural is not None:
        by_type = ", ".join(f"{k} ×{c} ({t('ui.inputs_word', lang)}: {i})" for k, (c, i) in g.structural.by_type.items())
        parts.append(Text.from_markup(
            f"[bold]{t('ui.implemented', lang)}:[/] {tech_label(g.technology, lang)} · "
            f"{t('ui.as_drawn', lang)} [bold]{g.structural.short()}[/] · {t('ui.nandnor_count', lang)} "
            f"[bold]{g.structural.nandnor_short()}[/]  [dim]{by_type}[/]"))
    if g.implemented_cover is not None:
        parts.append(Text(form_label(g.implemented_form, lang) + (
            f" · {t('ui.cover_cost', lang)} {g.implemented_cost.short()}" if g.implemented_cost else ""), style="dim"))
        parts.append(formulas_grid(cover_formulas(g.implemented_cover)))
    for reason in g.recover_reasons:
        parts.append(Text("◆ " + reason, style="magenta"))
    return Group(*parts) if parts else Text("—", style="dim")


def methods_table(fr: FormResult, lang: str) -> Table:
    title = t("ui.methods_title", lang, form=form_label(fr.form, lang))
    table = Table(title=title, title_justify="left", title_style="bold", box=box.SIMPLE_HEAD, pad_edge=False)
    # Notes go under the method name instead of a column of their own, so the table fits 80 columns.
    table.add_column(t("ui.method", lang), min_width=20, ratio=1)
    table.add_column(t("ui.cost", lang), justify="right", no_wrap=True)
    table.add_column(t("ui.proof", lang), min_width=21, overflow="fold")
    table.add_column(t("ui.verified", lang), justify="center", no_wrap=True)
    table.add_column(t("ui.time", lang), justify="right", style="dim", no_wrap=True)
    for row in fr.rows:
        cost = f"{row.gates}/{row.inputs}" if row.gates is not None else "—"
        style = "green" if row.matches_reference else ("red" if not row.verified and row.gates is not None else "")
        mark = "✓" if row.matches_reference else ""
        method = Text(f"{mark} {row.method}".strip(), style=style + (" bold" if row.method == "ilp" else ""))
        if row.note:
            method.append("\n  " + row.note, style="dim")
        table.add_row(method, Text(cost, style=style), row.proof or "—", "✓" if row.verified else "✗",
                      f"{row.runtime_s * 1000:.0f} ms")
    ref = fr.reference.short() if fr.reference else t("ui.not_proven", lang)
    agree = sum(r.matches_reference for r in fr.rows)
    table.caption = t("ui.methods_caption", lang, optimum=ref, agree=agree, total=len(fr.rows))
    table.caption_justify = "left"
    return table


def verdict_panel(g: GroupReport, lang: str) -> Panel:
    body = Text(verdict_sentence(g, lang))
    for note in g.notes:
        body.append("\n• " + msg(note, lang), style="dim")
    title = Text(f" {VERDICT_ICON[g.verdict]} {verdict_label(g.verdict, lang)} ", style=VERDICT_STYLE[g.verdict])
    color = VERDICT_STYLE[g.verdict].replace("bold ", "")
    return Panel(body, title=title, title_align="left", border_style=color, box=box.HEAVY, padding=(0, 1))


def optimum_view(g: GroupReport, lang: str, *, show_kmaps: bool) -> Iterator[RenderableType]:
    fr = best_form(g)
    if fr is None or fr.best_cover is None:
        return
    key = "ui.optimal_cover" if fr.proven else "ui.best_cover"
    cost = fr.best_cost.short() if fr.best_cost else "?"
    yield Text(t(key, lang, form=form_label(fr.form, lang), cost=cost, method=fr.best_method or "?"), style="bold")
    yield formulas_grid(cover_formulas(fr.best_cover))
    lines = [line for block in derivations(fr.best_cover) for line in block]
    if lines:
        gate = "NAND (↑)" if fr.form.value == "SOP" else "NOR (↓)"
        yield Panel(Text("\n".join(lines)), title=t("ui.derivation", lang, gate=gate), title_align="left",
                    subtitle=Text(derivation_legend(fr.form, lang), style="dim"), subtitle_align="left",
                    border_style="grey50", box=box.ROUNDED)
    if show_kmaps and fr.kmaps:
        yield Text(t("ui.kmaps", lang, form=form_label(fr.form, lang)), style="bold")
        yield Columns([kmap_table(v) for v in fr.kmaps], equal=False, expand=False)


# ------------------------------------------------------------------ truth table, sequential, closing


def truth_table_view(report: Report, lang: str) -> Table:
    truth = report.truth
    assert truth is not None
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column(" ".join(truth.inputs), style="cyan")
    table.add_column(" ".join(truth.outputs), style="bold")
    for k, (bits, outs) in enumerate(truth.rows):
        table.add_row(str(k), " ".join(bits), " ".join(outs))
    return table


def seq_view(seq: SeqSection, lang: str) -> RenderableType:
    if seq.status != "ok" or not seq.data:
        key = "ui.seq_error" if seq.status == "error" else "ui.seq_skipped"
        return Text(t(key, lang, message=seq.message), style="yellow")
    return Group(*render_seq.renderables(seq.data, lang))


def closing_panels(report: Report, lang: str) -> RenderableType:
    recs = Text("\n".join("→ " + msg(m, lang) for m in report.recommendations))
    lims = Text("\n".join("• " + msg(m, lang) for m in report.limitations), style="dim")
    return Group(
        Panel(recs, title=Text(t("ui.recommendations", lang), style="bold green"), title_align="left",
              border_style="green", box=box.ROUNDED),
        Panel(lims, title=Text(t("ui.limitations", lang), style="bold"), title_align="left", border_style="grey50",
              box=box.ROUNDED),
    )
