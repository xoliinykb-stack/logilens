"""``analyze``, ``check`` and ``report`` commands (all built on :func:`logilens.analysis.analyze`)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import typer
from rich.text import Text

from logilens.cli.errors import EXIT_FINDINGS, EXIT_OK
from logilens.cli.options import CircuitOpt, FileArg, JsonOpt, OnlyOpt, examples
from logilens.cli.state import State, state_of
from logilens.i18n import t

if TYPE_CHECKING:
    from logilens.report.model import Report

SpecOpt = Annotated[Path | None, typer.Option("--spec", metavar="FILE", exists=True, dir_okay=False,
                                              help="Specification: a code table, a truth table or expressions.")]
MapOpt = Annotated[list[str] | None, typer.Option("--map", metavar="SPEC=OUT,...",
                                                  help="Map a spec output to circuit outputs, e.g. A=A_N,A_R.")]
TieOpt = Annotated[bool | None, typer.Option("--tie/--no-tie",
                                             help="Merge input pins with identical labels (default: automatic).")]
Format = Literal["rich", "md", "html", "json"]
Form = Literal["auto", "sop", "pos", "both"]

ANALYZE_EXAMPLES = examples(("logilens analyze adder.circ", "the circuit's own function"),
                            ("logilens analyze adder.circ --spec task.txt", "use don't cares from the task"),
                            ("logilens analyze adder.circ --form pos --no-kmap", ""),
                            ("logilens analyze adder.circ --json > result.json", ""))
CHECK_EXAMPLES = examples(("logilens check adder.circ --spec task.txt", ""),
                          ("logilens check adder.circ --spec task.txt --map Y=Y1,Y2", "one spec output, two pins"))
REPORT_EXAMPLES = examples(("logilens report adder.circ", "in the terminal"),
                           ("logilens report adder.circ -f html -o report.html", ""),
                           ("logilens report adder.circ --spec task.txt -f md -o report.md", ""))


def _split(value: str | None) -> list[str] | None:
    return [s.strip() for s in value.split(",") if s.strip()] if value else None


def _methods(value: str | None) -> tuple[str, ...] | None:
    from logilens.minimize.compare import DEFAULT_METHODS

    methods = _split(value)
    if methods is None:
        return None
    unknown = [m for m in methods if m not in DEFAULT_METHODS]
    if unknown:
        raise typer.BadParameter(f"unknown method {', '.join(unknown)}; choose from: {', '.join(DEFAULT_METHODS)}",
                                 param_hint="'--methods'")
    return tuple(methods)


def findings(report: Report) -> bool:
    """Lint problems, a failed spec check or an improvable group."""
    from logilens.report.model import Verdict

    return bool(report.lint.problems) or report.spec_passed is False or any(
        g.verdict is Verdict.IMPROVABLE for g in report.groups)


def analyze_cmd(
    ctx: typer.Context,
    file: FileArg,
    spec: SpecOpt = None,
    map_: MapOpt = None,
    outputs: Annotated[str | None, typer.Option("--outputs", metavar="NAMES",
                                                help="Only analyze groups containing these outputs (comma list).")]
    = None,
    methods: Annotated[str | None, typer.Option("--methods", metavar="NAMES",
                                                help="Minimization methods to run, comma list (ilp always runs).")]
    = None,
    form: Annotated[Form, typer.Option("--form", case_sensitive=False,
                                       help="sop = sum of products, pos = product of sums.")] = "auto",
    no_kmap: Annotated[bool, typer.Option("--no-kmap", help="Do not draw Karnaugh maps.")] = False,
    table: Annotated[bool, typer.Option("--table", help="Also print the full truth table.")] = False,
    only: OnlyOpt = None,
    tie: TieOpt = None,
    circuit: CircuitOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Find the minimal form of a combinational circuit and check whether yours is optimal.

    Shows the truth table, Karnaugh maps, the results of every minimization method and a verdict.
    Exits with 1 when something can be improved or is wrong, 0 otherwise.
    """
    st = state_of(ctx)
    methods_list = _methods(methods)

    def body() -> int:
        from logilens.analysis import analyze
        from logilens.report import render_json, render_rich

        opts = st.options(spec=spec, map_overrides=list(map_ or []), only=only, methods=methods_list, forms=form.lower(),
                          tie_duplicate_labels=tie, circuit=circuit, outputs=_split(outputs), kmaps=not no_kmap)
        report = analyze(file, opts)
        if as_json:
            st.echo(render_json.render(report))
        else:
            render_rich.render(report, st.console, show_table=table, show_kmaps=not no_kmap)
        return EXIT_FINDINGS if findings(report) else EXIT_OK

    st.run(body)


def check_cmd(
    ctx: typer.Context,
    file: FileArg,
    spec: Annotated[Path, typer.Option("--spec", metavar="FILE", exists=True, dir_okay=False,
                                       help="Specification: a code table, a truth table or expressions.")],
    map_: MapOpt = None,
    tie: TieOpt = None,
    circuit: CircuitOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Check that the circuit does what the specification says.

    Exits with 1 on any mismatching row, 0 when everything matches.
    """
    st = state_of(ctx)

    def body() -> int:
        from logilens.analysis import analyze
        from logilens.report import render_json

        opts = st.options(spec=spec, map_overrides=list(map_ or []), tie_duplicate_labels=tie, circuit=circuit,
                          minimize=False, robustness=False, kmaps=False, sequential=False)
        report = analyze(file, opts)
        if report.spec is None:
            raise ValueError(t("check.no_table", st.lang))
        if as_json:
            st.echo(render_json.dumps({"schema": "logilens/check@1", "file": str(file), "spec": report.spec,
                                       "passed": report.spec.passed, "notes": report.notes}, st.lang))
        else:
            _print_check(st, report)
        ok = report.spec.passed and not report.spec.unmapped
        return EXIT_OK if ok else EXIT_FINDINGS

    st.run(body)


def _print_check(st: State, report: Report) -> None:
    from logilens.report import render_rich
    from logilens.report.text import msg

    assert report.spec is not None
    st.console.print(Text.assemble(("logilens check ", "bold magenta"), (Path(report.file).name, "bold"),
                                   ("  ↔  ", "dim"), (Path(report.spec.path).name, "bold")))
    for note in report.notes:
        st.console.print(Text("• " + msg(note, st.lang), style="dim"))
    st.console.print(render_rich.spec_view(report.spec, st.lang))
    passed = report.spec.passed and not report.spec.unmapped
    st.console.print(Text(("✓ " if passed else "✗ ") + t("check.passed" if passed else "check.failed", st.lang),
                          style="bold green" if passed else "bold red"))


def report_cmd(
    ctx: typer.Context,
    file: FileArg,
    fmt: Annotated[Format, typer.Option("--format", "-f", case_sensitive=False,
                                        help="rich = terminal, md = Markdown, html, json.")] = "rich",
    output: Annotated[Path | None, typer.Option("--output", "-o", metavar="PATH", dir_okay=False,
                                                help="Write the report to this file instead of the terminal.")]
    = None,
    spec: SpecOpt = None,
    map_: MapOpt = None,
    only: OnlyOpt = None,
    tie: TieOpt = None,
    no_image: Annotated[bool, typer.Option("--no-image", help="HTML: do not embed the Logisim drawing.")] = False,
    circuit: CircuitOpt = None,
) -> None:
    """Write the full analysis as one report: in the terminal or as Markdown, HTML or JSON.

    Exits with 1 when the report contains problems, 0 otherwise.
    """
    st = state_of(ctx)
    fmt = fmt.lower()  # type: ignore[assignment]

    def body() -> int:
        from logilens.analysis import analyze

        opts = st.options(spec=spec, map_overrides=list(map_ or []), only=only, tie_duplicate_labels=tie,
                          circuit=circuit, render_image=fmt == "html" and not no_image)
        report = analyze(file, opts)
        _emit(st, report, fmt, output)
        return EXIT_FINDINGS if findings(report) else EXIT_OK

    st.run(body)


def _emit(st: State, report: Report, fmt: str, output: Path | None) -> None:
    from logilens.report import render_html, render_json, render_md, render_rich

    if fmt == "rich" and output is None:
        render_rich.render(report, st.console, show_table=True)
        return
    if fmt == "rich":
        from rich.console import Console

        with output.open("w", encoding="utf-8") as fh:  # type: ignore[union-attr]
            render_rich.render(report, Console(file=fh, width=120, no_color=True), show_table=True)
        text = None
    else:
        text = {"md": render_md.render, "html": render_html.render, "json": render_json.render}[fmt](report)
    if output is None:
        st.echo(text or "")
        return
    if text is not None:
        output.write_text(text, encoding="utf-8")
    st.console.print(Text("✓ " + t("report.written", st.lang, path=str(output)), style="green"))
