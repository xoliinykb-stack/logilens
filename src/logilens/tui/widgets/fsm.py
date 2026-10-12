"""«Автомат» tab: summary, transition table, state graph and a timing diagram re-simulated on demand."""

from __future__ import annotations

from typing import Any

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Input, Static

from logilens.core.netlist import ProjectNetlist
from logilens.i18n import t
from logilens.report import render_seq
from logilens.report.model import Report
from logilens.report.render_rich import seq_view
from logilens.tui.i18n import tr


def fsm_renderable(data: dict[str, Any], graph: str, lang: str) -> RenderableType:
    """Summary panel, transition table, graph text, encodings and notes (timing is shown separately)."""
    if not data.get("applicable", True):
        return Text(t("seq.not_applicable", lang, reason=data.get("reason", "")), style="yellow")
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column()
    for k, v in render_seq.summary_rows(data, lang):
        grid.add_row(k, v)
    parts: list[RenderableType] = [Panel(grid, border_style="cyan", box=box.ROUNDED)]
    table = render_seq.transition_table(data, lang)
    if table is not None:
        parts.append(table)
    if graph:
        parts.append(Panel(Text(graph), title=t("seq.graph", lang), title_align="left", border_style="grey50",
                           box=box.ROUNDED))
    encodings = render_seq.encodings_table(data, lang)
    if encodings is not None:
        parts.append(encodings)
    notes = list((data.get("analysis") or {}).get("notes") or []) + list(data.get("warnings") or [])
    if notes:
        parts.append(Text("\n".join("• " + n for n in notes), style="dim"))
    return Group(*parts)


class FsmView(VerticalScroll):
    """Sequential section of the report plus an input field for the timing diagram."""

    def __init__(self, lang: str, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.lang = lang
        self.project: ProjectNetlist | None = None
        self.seq_result: Any = None
        self.circuit: str | None = None
        self.timing: Any = None  # last seq.timing.Timing
        self.timing_error: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="fsm-body")
        yield Static(Text(tr("fsm.timing_title", self.lang), style="bold"), id="timing-title")
        with Horizontal(id="timing-controls"):
            yield Input(placeholder=tr("fsm.timing_placeholder", self.lang), id="timing-input",
                        restrict=r"[01 ,;]*")
            yield Button(tr("fsm.simulate", self.lang), id="timing-run", variant="primary")
        yield Static(Text(tr("fsm.timing_hint", self.lang), style="dim"), id="timing-body")

    def show(self, report: Report, project: ProjectNetlist | None, seq_result: Any) -> None:
        self.project, self.seq_result, self.circuit = project, seq_result, report.circuit
        self.timing = None
        body = self.query_one("#fsm-body", Static)
        seq = report.seq
        can_simulate = bool(seq_result is not None and getattr(seq_result, "applicable", False) and project)
        for wid in ("#timing-title", "#timing-controls", "#timing-body"):
            self.query_one(wid).display = can_simulate
        if not report.is_sequential or seq is None:
            body.update(Text(tr("fsm.not_seq", self.lang), style="yellow"))
            return
        if seq.status != "ok" or not seq.data:
            body.update(seq_view(seq, self.lang))
            return
        graph = seq_result.graph_text() if can_simulate else ""
        body.update(fsm_renderable(seq.data, graph, self.lang))
        self.query_one("#timing-body", Static).update(Text(tr("fsm.timing_hint", self.lang), style="dim"))

    # ------------------------------------------------------------- timing
    def simulate(self, sequence: str) -> None:
        sequence = sequence.strip()
        if not sequence or self.project is None or self.seq_result is None:
            return
        self.query_one("#timing-body", Static).update(Text(tr("fsm.running", self.lang), style="italic dim"))
        self._simulate(sequence)

    @work(thread=True, exclusive=True, group="timing", exit_on_error=False)
    def _simulate(self, sequence: str) -> None:
        from logilens.seq import Runner, find_structure, parse_sequence, simulate_timing

        try:
            fsm = self.seq_result.fsm
            ex = find_structure(self.project, self.circuit)
            steps = parse_sequence(sequence, fsm)
            timing = simulate_timing(Runner(self.project, ex), fsm, steps)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - shown in the panel instead of crashing the app
            self._call(self._show_timing_error, str(exc) or type(exc).__name__)
            return
        self._call(self._show_timing, timing)

    def _call(self, fn: Any, *args: Any) -> None:
        try:
            self.app.call_from_thread(fn, *args)
        except RuntimeError:
            pass

    def _show_timing(self, timing: Any) -> None:
        if not self.is_attached:
            return
        self.timing, self.timing_error = timing, None
        parts: list[RenderableType] = [Panel(timing.rich(), title=t("seq.timing", self.lang), title_align="left",
                                             border_style="cyan", box=box.ROUNDED)]
        if timing.mismatches:
            parts.append(Text("\n".join("⚠ " + m for m in timing.mismatches), style="yellow"))
        self.query_one("#timing-body", Static).update(Group(*parts))

    def _show_timing_error(self, message: str) -> None:
        if not self.is_attached:
            return
        self.timing, self.timing_error = None, message
        self.query_one("#timing-body", Static).update(Text(tr("fsm.timing_error", self.lang, message=message),
                                                           style="bold red"))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "timing-input":
            event.stop()
            self.simulate(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "timing-run":
            event.stop()
            self.simulate(self.query_one("#timing-input", Input).value)


__all__ = ["FsmView", "fsm_renderable"]
