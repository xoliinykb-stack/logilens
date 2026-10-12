"""``?`` help: key bindings and what each tab shows."""

from __future__ import annotations

from typing import ClassVar

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from logilens.tui.i18n import tr
from logilens.tui.widgets.common import localize_bindings

KEYS = (("1 … 7", "help.k.tabs"), ("o", "help.k.open"), ("r", "help.k.rerun"), ("e", "help.k.export"),
        ("t", "help.k.theme"), ("?", "help.k.help"), ("q", "help.k.quit"), ("↑ ↓ Tab Enter", "help.k.nav"))
TABS = ("overview", "issues", "truth", "kmaps", "minimize", "fsm", "report")


def help_renderable(lang: str) -> Group:
    keys = Table.grid(padding=(0, 2))
    keys.add_column(style="bold magenta", no_wrap=True, justify="right")
    keys.add_column()
    for key, text in KEYS:
        keys.add_row(key, tr(text, lang))
    tabs = Table.grid(padding=(0, 2))
    tabs.add_column(style="bold cyan", no_wrap=True, justify="right")
    tabs.add_column(style="dim", no_wrap=True)
    tabs.add_column()
    for k, tab in enumerate(TABS, 1):
        tabs.add_row(str(k), tr(f"tab.{tab}", lang), tr(f"help.t.{tab}", lang))
    return Group(Text(tr("help.keys", lang), style="bold underline"), keys, Text(""),
                 Text(tr("help.tabs", lang), style="bold underline"), tabs, Text(""),
                 Text(tr("help.close", lang), style="dim italic"))


class HelpScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "key.close"),
        Binding("q", "close", show=False),
        Binding("question_mark", "close", show=False),
    ]

    def __init__(self, lang: str) -> None:
        super().__init__()
        self.lang = lang
        localize_bindings(self, lang)

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-box") as box:
            box.border_title = tr("help.title", self.lang)
            yield Static(help_renderable(self.lang), id="help-body")

    def action_close(self) -> None:
        self.dismiss(None)


__all__ = ["HelpScreen", "help_renderable"]
