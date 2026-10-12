"""The Textual application: file picker at the bottom of the screen stack, one main screen per opened file."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from logilens.i18n import normalize_lang
from logilens.tui.recent import RecentFiles
from logilens.tui.screens.help import HelpScreen
from logilens.tui.screens.main import MainScreen
from logilens.tui.screens.picker import PickerScreen
from logilens.tui.settings import TuiSettings
from logilens.tui.widgets.common import localize_bindings


class LogilensApp(App[None]):
    """``logilens`` interactive mode."""

    TITLE = "logilens"
    CSS_PATH = "styles/app.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "key.quit"),
        Binding("t", "toggle_dark", "key.theme"),
        Binding("question_mark", "help", "key.help", key_display="?"),
    ]

    def __init__(self, file: str | Path | None = None, spec: str | Path | None = None, *, lang: str = "ru",
                 backend: str = "auto", jar: str | None = None, only: str | None = None,
                 recent_path: str | Path | None = None, cwd: str | Path | None = None, forms: str = "both") -> None:
        super().__init__()
        self.settings = TuiSettings(normalize_lang(lang), backend, jar, only, forms,
                                    Path(cwd) if cwd is not None else Path.cwd())
        self.initial_file = Path(file) if file else None
        self.initial_spec = str(spec) if spec else None
        self.recent = RecentFiles(recent_path)
        self.picker = PickerScreen(self.settings.lang, self.settings.cwd, self.initial_spec)
        localize_bindings(self, self.settings.lang)

    def on_mount(self) -> None:
        self.push_screen(self.picker)
        if self.initial_file is not None:
            self.open_file(self.initial_file, self.initial_spec)

    # ------------------------------------------------------------- navigation
    def open_file(self, path: str | Path, spec: str | Path | None = None) -> MainScreen:
        """Show ``path`` in a fresh main screen (above the picker) and remember it in the recent list."""
        path = Path(path)
        if path.is_file():
            self.recent.add(path, spec)
        while len(self.screen_stack) > 1 and self.screen is not self.picker:
            self.pop_screen()
        screen = MainScreen(path, spec, self.settings)
        self.push_screen(screen)
        return screen

    def action_open_picker(self) -> None:
        while len(self.screen_stack) > 1 and self.screen is not self.picker:
            self.pop_screen()

    def action_help(self) -> None:
        if not isinstance(self.screen, HelpScreen):
            self.push_screen(HelpScreen(self.settings.lang))

    @property
    def main_screen(self) -> MainScreen | None:
        return next((s for s in reversed(self.screen_stack) if isinstance(s, MainScreen)), None)


def run_tui(file: str | Path | None = None, spec: str | Path | None = None, *, lang: str = "ru",
            backend: str = "auto", jar: str | None = None, only: str | None = None) -> None:
    LogilensApp(file, spec, lang=lang, backend=backend, jar=jar, only=only).run()


__all__ = ["LogilensApp", "run_tui"]
