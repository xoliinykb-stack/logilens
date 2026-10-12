"""Main screen: one analyzed circuit in seven tabs; the analysis runs in a worker thread."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, ClassVar

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static, TabbedContent, TabPane

from logilens.analysis import analyze
from logilens.analysis.service import load
from logilens.cli.errors import ERROR_HINTS, classify_error, error_detail
from logilens.i18n import t
from logilens.report import render_rich
from logilens.report.model import Report
from logilens.report.text import msg
from logilens.tui.i18n import tr
from logilens.tui.settings import TuiSettings
from logilens.tui.widgets.common import localize_bindings
from logilens.tui.widgets.export import ExportView
from logilens.tui.widgets.fsm import FsmView
from logilens.tui.widgets.issues import IssuesView
from logilens.tui.widgets.kmap import KMapPanel
from logilens.tui.widgets.topbar import TopBar
from logilens.tui.widgets.truth import TruthView

log = logging.getLogger(__name__)

TAB_IDS = ("overview", "issues", "truth", "kmaps", "minimize", "fsm", "report")


def overview_renderable(report: Report, lang: str) -> RenderableType:
    parts: list[RenderableType] = [render_rich.header(report, lang)]
    if report.notes:
        parts.append(Text("\n".join("• " + msg(n, lang) for n in report.notes), style="dim"))
    if report.spec is not None:
        parts += [render_rich.section_title(t("ui.spec_check", lang)), render_rich.spec_view(report.spec, lang)]
    if report.groups:
        parts += [render_rich.section_title(t("ui.summary", lang)), render_rich.summary_table(report, lang)]
        parts += [render_rich.verdict_panel(g, lang) for g in report.groups]
    parts.append(render_rich.closing_panels(report, lang))
    return Group(*parts)


def minimize_renderable(report: Report, lang: str) -> RenderableType:
    if not report.groups:
        return Text(tr("min.none", lang), style="yellow")
    parts: list[RenderableType] = []
    for g in report.groups:
        parts += list(render_rich.group_view(g, lang, show_kmaps=False))
        parts.append(Text(""))
    return Group(*parts)


def error_renderable(exc: BaseException, path: Path, lang: str) -> RenderableType:
    _, key = classify_error(exc)
    detail = error_detail(exc)
    body = Text.assemble(("✗ " + t(key, lang), "bold red"), "\n\n", (str(path), "bold"))
    if detail:
        body.append("\n" + detail, style="red")
    if key in ERROR_HINTS:
        body.append("\n" + t(ERROR_HINTS[key], lang), style="yellow")
    body.append("\n\n" + tr("error.hint", lang), style="dim")
    return Panel(body, title=Text(tr("error.title", lang), style="bold red"), title_align="left",
                 border_style="red", box=box.ROUNDED, padding=(1, 2))


class MainScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "tab(1)", "key.tabs", key_display="1-7"),
        *[Binding(str(k), f"tab({k})", show=False) for k in range(2, 8)],
        Binding("o", "open", "key.open"),
        Binding("r", "rerun", "key.rerun"),
        Binding("e", "export", "key.export"),
    ]

    def __init__(self, path: str | Path, spec: str | Path | None, settings: TuiSettings) -> None:
        super().__init__()
        self.path = Path(path)
        self.spec = str(spec) if spec else None
        self.settings = settings
        self.lang = settings.lang
        self.only = settings.only
        self.report: Report | None = None
        self.project: Any = None
        self.seq_result: Any = None
        self.error: BaseException | None = None
        self._generation = 0
        localize_bindings(self, self.lang)

    # ------------------------------------------------------------- layout
    def compose(self) -> ComposeResult:
        lang = self.lang
        yield TopBar(lang, id="topbar")
        with Container(id="main-content"):
            with TabbedContent(id="tabs", initial="overview"):
                with TabPane(tr("tab.overview", lang), id="overview"), VerticalScroll(classes="pane-scroll"):
                    yield Static("", id="overview-body")
                with TabPane(tr("tab.issues", lang), id="issues"):
                    yield IssuesView(lang, self.only, id="issues-view")
                with TabPane(tr("tab.truth", lang), id="truth"):
                    yield TruthView(lang, id="truth-view")
                with TabPane(tr("tab.kmaps", lang), id="kmaps"):
                    yield KMapPanel(lang, id="kmap-panel")
                with TabPane(tr("tab.minimize", lang), id="minimize"), VerticalScroll(classes="pane-scroll"):
                    yield Static("", id="minimize-body")
                with TabPane(tr("tab.fsm", lang), id="fsm"):
                    yield FsmView(lang, id="fsm-view")
                with TabPane(tr("tab.report", lang), id="report"):
                    yield ExportView(lang, id="export-view")
            yield Static("", id="error-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(TabbedContent).hide_tab("fsm")
        self.run_analysis()

    # ------------------------------------------------------------- analysis
    def run_analysis(self) -> None:
        self._generation += 1
        self.report = None
        self.error = None
        self.query_one(TopBar).show_loading(self.path)
        self.query_one("#error-panel").display = False
        tabs = self.query_one(TabbedContent)
        tabs.display = True
        tabs.loading = True
        self.query_one(ExportView).show(None, self.path)
        self._analyze(self._generation, self.path, self.spec, self.only)

    @work(thread=True, exclusive=True, group="analysis", exit_on_error=False)
    def _analyze(self, generation: int, path: Path, spec: str | None, only: str | None) -> None:
        project = seq_result = None
        try:
            report = analyze(path, self.settings.options(spec, only))
            if report.is_sequential and report.seq is not None and report.seq.status == "ok":
                project, seq_result = self._sequential(path, report)
        except Exception as exc:  # noqa: BLE001 - every failure becomes a friendly panel
            self._from_thread(self._show_error, generation, exc)
            return
        self._from_thread(self._show_report, generation, report, project, seq_result)

    def _sequential(self, path: Path, report: Report) -> tuple[Any, Any]:
        """Project + SeqResult objects for the state graph and timing re-simulation (best effort)."""
        from logilens.seq import analyze_sequential

        try:
            project = load(path, self.settings.backend, self.settings.jar)
            return project, analyze_sequential(project, report.circuit, None, estimate_encodings=False)
        except Exception:  # the report itself already has the sequential section
            log.debug("sequential re-analysis of %s failed", path, exc_info=True)
            note = tr("fsm.partial", self.lang)
            self._from_thread(lambda: self.notify(note, severity="warning"))
            return None, None

    def _from_thread(self, fn: Any, *args: Any) -> None:
        try:
            self.app.call_from_thread(fn, *args)
        except RuntimeError:  # app already closed
            pass

    def _show_error(self, generation: int, exc: BaseException) -> None:
        if generation != self._generation or not self.is_attached:
            return
        self.error = exc
        self.query_one(TopBar).set_error(self.path)
        tabs = self.query_one(TabbedContent)
        tabs.loading = False
        tabs.display = False
        panel = self.query_one("#error-panel", Static)
        panel.update(error_renderable(exc, self.path, self.lang))
        panel.display = True

    def _show_report(self, generation: int, report: Report, project: Any, seq_result: Any) -> None:
        if generation != self._generation or not self.is_attached:
            return
        self.report, self.project, self.seq_result = report, project, seq_result
        lang = self.lang
        self.query_one(TopBar).set_report(report, self.path)
        self.query_one("#overview-body", Static).update(overview_renderable(report, lang))
        self.query_one(IssuesView).show(report)
        self.query_one(TruthView).show(report)
        self.query_one(KMapPanel).show(report)
        self.query_one("#minimize-body", Static).update(minimize_renderable(report, lang))
        self.query_one(FsmView).show(report, project, seq_result)
        self.query_one(ExportView).show(report, self.path)
        tabs = self.query_one(TabbedContent)
        count = len(report.lint.issues)
        with contextlib.suppress(Exception):  # cosmetic only
            tabs.get_tab("issues").label = tr("tab.issues", lang) + (f" ({count})" if count else "")
        if report.is_sequential:
            tabs.show_tab("fsm")
        else:
            if tabs.active == "fsm":
                tabs.active = "overview"
            tabs.hide_tab("fsm")
        tabs.loading = False

    # ------------------------------------------------------------- events / actions
    def on_issues_view_gate_set_changed(self, event: IssuesView.GateSetChanged) -> None:
        self.only = event.only
        self.run_analysis()

    def action_tab(self, index: int) -> None:
        if not 1 <= index <= len(TAB_IDS):
            return
        tab_id = TAB_IDS[index - 1]
        tabs = self.query_one(TabbedContent)
        if tab_id == "fsm" and (self.report is None or not self.report.is_sequential):
            self.notify(tr("fsm.hidden", self.lang), severity="information")
            return
        tabs.active = tab_id

    def action_open(self) -> None:
        self.app.action_open_picker()  # type: ignore[attr-defined]

    def action_rerun(self) -> None:
        self.run_analysis()

    def action_export(self) -> None:
        view = self.query_one(ExportView)
        if self.report is None:
            self.notify(tr("export.no_report", self.lang), severity="warning")
            return
        self.query_one(TabbedContent).active = "report"
        path = view.export("html")
        if path is not None:
            self.notify(tr("export.saved", self.lang, path=str(path)))


__all__ = ["TAB_IDS", "MainScreen", "error_renderable", "minimize_renderable", "overview_renderable"]
