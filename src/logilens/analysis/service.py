"""The analysis facade: ``analyze(path, options) -> Report`` (used by the CLI and the TUI).

Pipeline: load -> lint -> classify -> truth table (+ spec mapping/check) -> per output group:
recover the implemented cover + structural cost, minimize with every method, robustness, verdict, K-maps ->
sequential section -> limitations / recommendations.
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from logilens import __version__
from logilens.analysis.groups import GroupContext, analyze_group
from logilens.analysis.mapping import map_spec_outputs
from logilens.analysis.options import Options
from logilens.analysis.tables import TableView, single_bit, table_view
from logilens.backends import load_project, truth_table
from logilens.core.errors import BackendError, LogilensError, NotFoundError
from logilens.core.logic_types import Spec
from logilens.core.netlist import CircuitNetlist, ProjectNetlist
from logilens.graph.classify import Classification, classify
from logilens.lint import count_problems, lint, summarize
from logilens.parse.circ_xml import read_circ
from logilens.report.model import (
    LintSection,
    Msg,
    Report,
    SeqSection,
    SpecSection,
    TruthSection,
    Verdict,
)
from logilens.spec.check import CheckResult, check_against_spec
from logilens.spec.mapping import OutputMapping, parse_map_args
from logilens.spec.parse import load_spec

log = logging.getLogger(__name__)
RENDER_TIMEOUT = 120.0  # seconds; big circuits take a while in headless AWT


def analyze(path: str | os.PathLike[str], options: Options | None = None) -> Report:
    """Analyze one `.circ` file. Raises :class:`LogilensError` subclasses on load/backend failures."""
    options = options or Options()
    project = load(path, options.backend, options.jar)
    circ = project.circuit(options.circuit)
    cl = classify(circ)
    report = _header(project, circ, cl, options)
    report.lint = lint_section(project, options.only)
    spec = load_spec(options.spec) if options.spec else None
    if not spec:
        report.limitations.append(Msg("limit.no_spec"))
    if cl.is_sequential:
        report.limitations.append(Msg("limit.sequential_no_comb"))
    elif circ.outputs:
        _combinational(report, project, circ, cl, spec, options)
    else:
        report.limitations.append(Msg("limit.no_outputs"))
    if options.sequential and cl.is_sequential:
        report.seq = sequential_section(project, circ.name, options.input_sequence)
    if options.render_image:
        report.image_png = render_png(project, circ.name, options.jar)
    _finish(report, project)
    return report


def load(path: str | os.PathLike[str], backend: str = "auto", jar: str | os.PathLike[str] | None = None) -> ProjectNetlist:
    """Load a project; the XML is validated in Python first so that broken files give a clean ParseError
    (Logisim itself would try to open an error dialog)."""
    read_circ(path)
    return load_project(path, backend, jar)


# ------------------------------------------------------------------ sections


def _header(project: ProjectNetlist, circ: CircuitNetlist, cl: Classification, options: Options) -> Report:
    stats = Counter(c.short for c in circ.components if c.kind not in ("text",))
    return Report(
        file=project.path, circuit=circ.name, backend=project.backend, source_version=project.source_version,
        file_format=project.format, lang=options.lang, tool_version=__version__,
        generated_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        inputs=[p.name for p in circ.inputs], outputs=[p.name for p in circ.outputs],
        stats=dict(sorted(stats.items(), key=lambda kv: (-kv[1], kv[0]))), circuits=list(project.circuits),
        is_sequential=cl.is_sequential, comb_loops=len(cl.comb_loops),
        notes=[Msg("note.raw", {"text": n}) for n in project.notes],
    )


def lint_section(project: ProjectNetlist, only: str | None) -> LintSection:
    issues = lint(project, only=only)
    return LintSection(issues, summarize(issues), count_problems(issues), only)


def duplicate_input_labels(circ: CircuitNetlist) -> list[str]:
    counts = Counter(p.label.strip() for p in circ.inputs if p.label.strip())
    return sorted(label for label, k in counts.items() if k > 1)


def _table(report: Report, project: ProjectNetlist, circ: CircuitNetlist, options: Options) -> dict[str, Any] | None:
    tie = options.tie_duplicate_labels
    dups = duplicate_input_labels(circ)
    if tie is None:
        tie = bool(dups)
        if tie:
            report.notes.append(Msg("note.tied_auto", {"labels": ", ".join(dups)}))
    bits = sum(p.width for p in circ.inputs)
    if bits > options.max_bits:
        report.limitations.append(Msg("limit.too_many_inputs", {"bits": bits, "max": options.max_bits}))
        return None
    table = truth_table(project, circ.name, max_bits=options.max_bits, tie_duplicate_labels=tie, jar=options.jar)
    report.notes.extend(Msg("note.raw", {"text": n}) for n in table.get("notes", [])
                        if not n.startswith("inputs with identical labels were tied"))
    if not single_bit(table):
        report.limitations.append(Msg("limit.multibit"))
        return None
    return table


def _combinational(report: Report, project: ProjectNetlist, circ: CircuitNetlist, cl: Classification,
                   spec: Spec | None, options: Options) -> None:
    table = _table(report, project, circ, options)
    if table is None:
        return
    view = table_view(table)
    alias = {name: kept for kept, names in table.get("tied", {}).items() for name in names}
    report.truth = TruthSection(list(view.inputs), list(view.outputs), list(view.rows), view.oscillating,
                                dict(table.get("tied", {})))
    if view.oscillating:
        report.limitations.append(Msg("limit.oscillation", {"rows": view.oscillating}))
    mapping = None
    if spec is not None:
        overrides = parse_map_args(options.map_overrides) if options.map_overrides else None
        mapping = map_spec_outputs(spec, view, cl.groups, overrides)
        report.spec = spec_section(spec, mapping, view, cl.groups)
    ctx = GroupContext(circ, cl, view, alias, spec, mapping)
    wanted = set(options.outputs or [])
    unknown = sorted(wanted - {o for group in cl.groups for o in group})
    if unknown:
        raise NotFoundError(", ".join(unknown))
    for k, outputs in enumerate(cl.groups, 1):
        if wanted and not wanted & set(outputs):
            continue
        report.groups.append(analyze_group(ctx, k, list(outputs), options))


def spec_section(spec: Spec, mapping: OutputMapping, view: TableView,
                 groups: list[list[str]] | None = None) -> SpecSection:
    """Check the circuit table against the spec (rows correct per label group and per circuit output group)."""
    res: CheckResult = check_against_spec(view.row_major(), spec, mapping, list(view.inputs))
    mapped = {lab for labels in mapping.mapping.values() for lab in labels}
    by_output_group = {}
    for group in groups or []:
        labels = [o for o in group if o in mapped]
        if labels:
            bad = {m.minterm for m in res.mismatches if m.label in labels}
            by_output_group[", ".join(labels)] = res.rows_checked - len(bad)
    return SpecSection(
        path=spec.source, kind=spec.kind, inputs=list(spec.inputs), outputs=list(spec.outputs),
        listed_rows=len(spec.rows), mapping={k: list(v) for k, v in mapping.mapping.items()}, how=dict(mapping.how),
        unmapped=list(mapping.unmapped_spec), passed=res.passed, rows_checked=res.rows_checked,
        rows_ok_by_group=dict(res.rows_ok_by_group), rows_ok_by_output_group=by_output_group,
        mismatches=[{"inputs": m.inputs, "output": m.output, "label": m.label, "expected": m.expected,
                     "actual": m.actual} for m in res.mismatches],
        dc_differences=[{"inputs": d.inputs, "output": d.output, "values": dict(d.values)}
                        for d in res.dc_differences],
        missing_labels=list(res.missing_labels), notes=list(res.notes))


def sequential_section(project: ProjectNetlist, circuit: str, inputs: str | None) -> SeqSection:
    """Sequential analysis of ``circuit`` as a report section."""
    from logilens.seq import analyze_sequential

    try:
        result = analyze_sequential(project, circuit, inputs)
    except LogilensError as exc:
        return SeqSection("error", message=str(exc))
    return SeqSection("ok", result.to_dict())


def render_png(project: ProjectNetlist, circuit: str, jar: str | os.PathLike[str] | None) -> str | None:
    """Printer-view PNG of the circuit through the Java helper (base64), None when Java is unavailable."""
    from logilens.backends.java.backend import JavaBridge

    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "circuit.png"
        try:
            JavaBridge(jar, timeout=RENDER_TIMEOUT).render(project.path, str(png), 1.5, circuit)
        except (BackendError, OSError):
            log.debug("circuit render failed", exc_info=True)
            return None
        return base64.b64encode(png.read_bytes()).decode("ascii") if png.is_file() else None


# ------------------------------------------------------------------ limitations / recommendations


def _finish(report: Report, project: ProjectNetlist) -> None:
    for item in project.unsupported:
        report.limitations.append(Msg("limit.unsupported", {"name": item.name, "where": str(item.loc or ""),
                                                            "reason": item.reason}))
    if any("espresso binary not available" in r.note for g in report.groups for f in g.forms for r in f.rows):
        report.limitations.append(Msg("limit.no_espresso"))
    if any(len(g.variables) > 8 for g in report.groups if g.forms):
        report.limitations.append(Msg("limit.ilp_primes"))
    report.limitations.append(Msg("limit.multilevel"))
    report.recommendations.extend(recommendations(report))


def recommendations(report: Report) -> list[Msg]:
    out: list[Msg] = []
    if report.lint.problems:
        out.append(Msg("rec.fix_lint", {"count": report.lint.problems}))
    if report.spec is not None and not report.spec.passed:
        out.append(Msg("rec.fix_spec", {"count": len(report.spec.mismatches)}))
    if report.spec is not None and any(h in ("function", "position") for h in report.spec.how.values()):
        out.append(Msg("rec.label_outputs"))
    for g in report.groups:
        if g.verdict is Verdict.IMPROVABLE and g.delta is not None:
            fr = g.form_result(g.verdict_form)
            out.append(Msg("rec.improve", {"group": g.title, "drawn": g.structural.short() if g.structural else "?",
                                           "optimum": fr.reference.short() if fr and fr.reference else "?",
                                           "gates": g.delta.gates, "inputs": g.delta.inputs}))
        elif g.verdict is Verdict.BEYOND_TWO_LEVEL:
            out.append(Msg("rec.beyond", {"group": g.title}))
    if report.spec is None and report.groups:
        out.append(Msg("rec.give_spec"))
    if not out:
        out.append(Msg("rec.none"))
    return out


__all__ = ["Options", "analyze", "lint_section", "load", "sequential_section", "spec_section"]
