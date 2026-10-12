"""«Отчёт» tab: export Markdown / HTML / JSON next to the circuit and open the HTML in a browser."""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from logilens.report import render_html, render_json, render_md
from logilens.report.model import Report
from logilens.tui.i18n import tr

FORMATS = {"md": "Markdown", "html": "HTML", "json": "JSON"}


def export_path(source: Path, fmt: str) -> Path:
    """``<folder>/<stem>.report.<fmt>`` next to the circuit."""
    return source.parent / f"{source.stem}.report.{fmt}"


def render_report(report: Report, fmt: str, lang: str) -> str:
    if fmt == "md":
        return render_md.render(report, lang)
    if fmt == "html":
        return render_html.render(report, lang)
    if fmt == "json":
        return render_json.render(report, lang)
    raise ValueError(f"unknown format {fmt!r}")


def open_in_browser(path: Path) -> None:
    """``open`` on macOS, the default browser elsewhere."""
    if sys.platform == "darwin":
        try:
            subprocess.run(["open", "--", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            webbrowser.open(path.resolve().as_uri())
    else:
        webbrowser.open(path.resolve().as_uri())


class ExportView(Vertical):
    def __init__(self, lang: str, **kw: Any) -> None:
        super().__init__(**kw)
        self.lang = lang
        self.report: Report | None = None
        self.source: Path | None = None
        self.saved: dict[str, Path] = {}
        self.log_lines: list[Text] = []

    def compose(self) -> ComposeResult:
        yield Static(Text(tr("export.title", self.lang), style="bold"), id="export-title")
        yield Static("", id="export-hint")
        with Horizontal(id="export-buttons"):
            for fmt, label in FORMATS.items():
                yield Button(label, id=f"export-{fmt}", variant="primary" if fmt == "html" else "default")
            yield Button(tr("export.open", self.lang), id="export-open", disabled=True)
        yield Static("", id="export-log")

    def show(self, report: Report | None, source: Path) -> None:
        self.report, self.source = report, source
        self.saved.clear()
        self.log_lines.clear()
        self.query_one("#export-hint", Static).update(
            Text(tr("export.hint", self.lang, dir=str(source.parent)), style="dim"))
        self.query_one("#export-open", Button).disabled = True
        self.query_one("#export-log", Static).update("")
        for fmt in FORMATS:
            self.query_one(f"#export-{fmt}", Button).disabled = report is None

    def _log(self, line: Text) -> None:
        self.log_lines.append(line)
        self.query_one("#export-log", Static).update(Text("\n").join(self.log_lines[-8:]))

    def export(self, fmt: str) -> Path | None:
        """Write the report in ``fmt``; returns the path (None on failure, the reason is shown)."""
        if self.report is None or self.source is None:
            self.app.notify(tr("export.no_report", self.lang), severity="warning")
            return None
        path = export_path(self.source, fmt)
        try:
            path.write_text(render_report(self.report, fmt, self.lang), encoding="utf-8")
        except OSError as exc:
            self._log(Text("✗ " + tr("export.failed", self.lang, path=str(path), message=exc.strerror or str(exc)),
                           style="bold red"))
            return None
        self.saved[fmt] = path
        self._log(Text("✓ " + tr("export.saved", self.lang, path=str(path)), style="green"))
        if fmt == "html":
            self.query_one("#export-open", Button).disabled = False
        return path

    def open_html(self) -> None:
        path = self.saved.get("html") or self.export("html")
        if path is None:
            return
        try:
            open_in_browser(path)
        except OSError as exc:
            self._log(Text("✗ " + tr("export.open_failed", self.lang, message=str(exc)), style="bold red"))
            return
        self._log(Text("↗ " + tr("export.opened", self.lang, path=str(path)), style="cyan"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "export-open":
            event.stop()
            self.open_html()
        elif bid.startswith("export-") and bid.removeprefix("export-") in FORMATS:
            event.stop()
            self.export(bid.removeprefix("export-"))


__all__ = ["ExportView", "export_path", "open_in_browser", "render_report"]
