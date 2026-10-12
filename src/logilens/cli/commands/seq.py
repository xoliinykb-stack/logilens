"""``seq`` command: sequential analysis (:mod:`logilens.seq`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.text import Text

from logilens.cli.errors import EXIT_OK
from logilens.cli.options import CircuitOpt, FileArg, JsonOpt, examples
from logilens.cli.state import state_of
from logilens.i18n import t

SEQ_EXAMPLES = examples(("logilens seq counter.circ", "transition table and state graph"),
                        ("logilens seq counter.circ --input 0110", "timing diagram for this input"),
                        ("logilens seq counter.circ --dot states.dot", "Graphviz file of the state graph"))


def seq_cmd(
    ctx: typer.Context,
    file: FileArg,
    input_sequence: Annotated[str | None, typer.Option("--input", metavar="BITS",
                                                       help="Input sequence for a timing diagram, e.g. 0110.")]
    = None,
    dot: Annotated[Path | None, typer.Option("--dot", metavar="PATH", dir_okay=False,
                                             help="Also write the state graph as a Graphviz .dot file.")] = None,
    circuit: CircuitOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Analyze a sequential circuit: flip-flops, transition table, Moore/Mealy type, state graph, timing."""
    st = state_of(ctx)

    def body() -> int:
        from logilens.analysis.service import load
        from logilens.report import render_seq
        from logilens.seq import analyze_sequential

        project = load(file, st.backend, st.jar)
        result = analyze_sequential(project, circuit, input_sequence)
        data = result.to_dict()
        if dot is not None and result.dot:
            dot.write_text(result.dot, encoding="utf-8")
        if as_json:
            st.echo(json.dumps({"schema": "logilens/seq@1", "file": str(file), **data}, ensure_ascii=False,
                               indent=2, default=str))
        else:
            for part in render_seq.renderables(data, st.lang):
                st.console.print(part)
            text = result.graph_text()
            if text:
                st.console.print(Panel(Text(text), title=t("seq.graph", st.lang), title_align="left",
                                       border_style="grey50"))
            if dot is not None and result.dot:
                st.console.print(Text("✓ " + t("report.written", st.lang, path=str(dot)), style="green"))
        return EXIT_OK

    st.run(body)
