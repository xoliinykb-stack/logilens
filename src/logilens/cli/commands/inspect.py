"""``parse`` and ``lint`` commands."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

import typer
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from logilens.cli.errors import EXIT_FINDINGS, EXIT_OK
from logilens.cli.options import FileArg, JsonOpt, OnlyOpt, examples
from logilens.cli.state import State, state_of
from logilens.i18n import t

if TYPE_CHECKING:
    from logilens.core.netlist import CircuitNetlist, ProjectNetlist


def circuit_stats(circ: CircuitNetlist) -> dict[str, Any]:
    counts = Counter(c.short for c in circ.components if c.kind != "text")
    return {
        "name": circ.name,
        "components": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "inputs": [{"name": p.name, "label": p.label, "width": p.width, "loc": list(p.loc)} for p in circ.inputs],
        "outputs": [{"name": p.name, "label": p.label, "width": p.width, "loc": list(p.loc)} for p in circ.outputs],
        "nets": len(circ.nets),
        "wires": len(circ.wires),
    }


def project_dict(project: ProjectNetlist) -> dict[str, Any]:
    return {
        "schema": "logilens/parse@1",
        "file": project.path, "backend": project.backend, "format": project.format,
        "source_version": project.source_version, "main": project.main,
        "circuits": [circuit_stats(c) for c in project.circuits.values()],
        "unsupported": [{"kind": u.kind, "name": u.name, "circuit": u.circuit,
                         "loc": list(u.loc) if u.loc else None, "reason": u.reason} for u in project.unsupported],
        "notes": list(project.notes),
    }


def project_tree(project: ProjectNetlist, lang: str) -> Tree:
    app = "Logisim-evolution" if project.format == "logisim-evolution" else "Logisim"
    root = Tree(Text.assemble((Path(project.path).name, "bold magenta"),
                              (f"  {app} {project.source_version} · {t('ui.backend', lang)} {project.backend}",
                               "dim")))
    for circ in project.circuits.values():
        stats = circuit_stats(circ)
        main = " ★" if circ.name == project.main else ""
        node = root.add(Text(f"{circ.name}{main}", style="bold cyan"))
        node.add(t("parse.components", lang) + ": "
                 + (", ".join(f"{k} ×{v}" for k, v in stats["components"].items()) or "—"))
        node.add(t("parse.inputs", lang) + ": " + (" ".join(p["name"] for p in stats["inputs"]) or "—"))
        node.add(t("parse.outputs", lang) + ": " + (" ".join(p["name"] for p in stats["outputs"]) or "—"))
        node.add(t("parse.nets", lang, nets=stats["nets"], wires=stats["wires"]))
    for item in project.unsupported:
        root.add(Text(t("parse.unsupported", lang, name=item.name, where=str(item.loc or ""), reason=item.reason),
                      style="yellow"))
    for note in project.notes:
        root.add(Text(note, style="dim"))
    return root


def crossval_table(report: Any, lang: str) -> Table:
    table = Table(title=t("parse.crossval", lang), title_justify="left")
    for col in ("circuit", "components", "ports", "rows", "result"):
        table.add_column(t(f"parse.cv.{col}", lang))
    for c in report.circuits:
        problems = c.component_mismatches + c.port_mismatches + c.pin_mismatches + c.net_mismatches + c.table_mismatches
        table.add_row(c.name, str(c.components), str(c.ports_compared), str(c.table_rows or "—"),
                      Text("✓" if c.ok else "✗ " + "; ".join(problems[:3]), style="green" if c.ok else "red"))
    return table


PARSE_EXAMPLES = examples(("logilens parse adder.circ", "circuits, components and pins"),
                          ("logilens parse adder.circ --json", ""))
LINT_EXAMPLES = examples(("logilens lint adder.circ", ""),
                         ("logilens lint adder.circ --only nand,nor", "only NAND and NOR gates allowed"),
                         ("logilens lint adder.circ --min-severity warning", "hide info notes"))


def parse_cmd(
    ctx: typer.Context,
    file: FileArg,
    crossval: Annotated[bool, typer.Option("--crossval", help="Compare the Python parser with Logisim (needs Java).")]
    = False,
    as_json: JsonOpt = False,
) -> None:
    """Show what is in a circuit file: circuits, components, input and output pins."""
    st = state_of(ctx)

    def body() -> int:
        from logilens.analysis.service import load

        project = load(file, st.backend, st.jar)
        cv = None
        if crossval:
            from logilens.backends.crossval import crossval as run_crossval

            cv = run_crossval(file, st.jar)
        if as_json:
            data = project_dict(project)
            if cv is not None:
                data["crossval"] = {"ok": cv.ok, "circuits": [vars(c) for c in cv.circuits]}
            st.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        else:
            st.console.print(project_tree(project, st.lang))
            if cv is not None:
                st.console.print(crossval_table(cv, st.lang))
        return EXIT_FINDINGS if cv is not None and not cv.ok else EXIT_OK

    st.run(body)


def lint_cmd(
    ctx: typer.Context,
    file: FileArg,
    only: OnlyOpt = None,
    min_severity: Annotated[Literal["error", "warning", "info"],
                            typer.Option("--min-severity", case_sensitive=False,
                                         help="Hide issues below this level.")] = "info",
    as_json: JsonOpt = False,
) -> None:
    """Check the wiring: loose wires, unconnected inputs, short circuits, loops, labels (rules L001–L014).

    Exits with 1 when an error or warning is found, 0 otherwise.
    """
    st = state_of(ctx)

    def body() -> int:
        from logilens.analysis.service import load
        from logilens.lint import Severity, count_problems, lint, summarize
        from logilens.report.render_json import dumps
        from logilens.report.render_rich import lint_view

        level = Severity(min_severity.lower())
        project = load(file, st.backend, st.jar)
        issues = [i for i in lint(project, only=only) if i.severity.rank <= level.rank]
        if as_json:
            st.echo(dumps({"schema": "logilens/lint@1", "file": str(file), "only": only,
                           "summary": summarize(issues), "problems": count_problems(issues), "issues": issues},
                          st.lang))
        else:
            _print_lint_header(st, file, only)
            st.console.print(lint_view(issues, st.lang))
        return EXIT_FINDINGS if count_problems(issues) else EXIT_OK

    st.run(body)


def _print_lint_header(st: State, file: Path, only: str | None) -> None:
    st.console.print(Text.assemble(("logilens lint ", "bold magenta"), (file.name, "bold"),
                                   (f"  ({t('ui.gate_set', st.lang, only=only.upper())})" if only else "", "dim")))
