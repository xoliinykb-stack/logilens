"""One-line header of the main screen: brand · file · backend · spec · lint badge · verdict badge."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from logilens.i18n import t
from logilens.report.model import Report, Verdict
from logilens.report.text import VERDICT_ICON, VERDICT_STYLE, verdict_label
from logilens.tui.i18n import tr


def verdict_badge(report: Report, lang: str) -> Text:
    v = report.overall
    if v is Verdict.NOT_APPLICABLE and report.is_sequential:
        return Text(f" ⟳ {tr('tab.fsm', lang)} ", style="bold black on cyan")
    color = VERDICT_STYLE[v].replace("bold ", "")
    fg = "white" if color in ("magenta", "dim") else "black"
    bg = "grey50" if color == "dim" else color
    return Text(f" {VERDICT_ICON[v]} {verdict_label(v, lang)} ", style=f"bold {fg} on {bg}")


def lint_badge(report: Report, lang: str) -> Text:
    n = report.lint.problems
    if n:
        return Text(f" {tr('main.lint_bad', lang, count=n)} ", style="bold white on red")
    return Text(f" {tr('main.lint_ok', lang)} ", style="bold black on green")


class TopBar(Horizontal):
    """Header line; ``set_*`` methods switch between loading, report and error states."""

    def __init__(self, lang: str, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.lang = lang

    def compose(self) -> ComposeResult:
        yield Static("logilens", id="brand")
        yield Static("", id="file-info")
        yield Static("", id="lint-badge")
        yield Static("", id="verdict-badge")

    def _set(self, info: Text, lint: Text | str = "", verdict: Text | str = "") -> None:
        self.query_one("#file-info", Static).update(info)
        self.query_one("#lint-badge", Static).update(lint)
        self.query_one("#verdict-badge", Static).update(verdict)

    def show_loading(self, path: Path) -> None:
        self._set(Text(tr("main.loading", self.lang, file=path.name), style="italic"))

    def set_error(self, path: Path) -> None:
        self._set(Text.assemble((path.name, "bold")), "", Text(f" ✗ {tr('error.title', self.lang)} ",
                                                                 style="bold white on red"))

    def set_report(self, report: Report, path: Path) -> None:
        lang = self.lang
        info = Text.assemble(
            (path.name, "bold"), (f" ({report.circuit})" if report.circuit != "main" else "", "dim"), ("  │  ", "dim"),
            (f"{t('ui.backend', lang)} ", "dim"), (report.backend, "bold"))
        if report.spec is not None:
            info.append("  │  ", style="dim")
            info.append("⊕ ", style="dim")
            info.append(Path(report.spec.path).name, style="bold")
        info.no_wrap = True
        info.overflow = "ellipsis"
        self._set(info, lint_badge(report, lang), verdict_badge(report, lang))


__all__ = ["TopBar", "lint_badge", "verdict_badge"]
