"""File picker: recent files, a ``*.circ`` directory tree with a quick filter, optional specification."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DirectoryTree, Footer, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from logilens.tui.i18n import tr
from logilens.tui.recent import RecentEntry
from logilens.tui.widgets.common import localize_bindings

SKIP_DIRS = {"__pycache__", "node_modules", "site-packages", "venv", "env"}
SPEC_SUFFIXES = (".spec.txt", ".csv", ".tsv")
MAX_SPEC_SCAN_DIRS = 1500
MAX_SPECS = 200


def is_spec_file(path: Path) -> bool:
    return path.name.lower().endswith(SPEC_SUFFIXES)


def _skip_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIP_DIRS


def find_specs(root: Path, depth: int = 3) -> list[Path]:
    """Specification candidates below ``root`` (bounded walk; hidden and tool directories skipped)."""
    out: list[Path] = []
    base = len(root.parts)
    for visited, (dirpath, dirnames, filenames) in enumerate(os.walk(root), 1):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not _skip_dir(d)) if len(here.parts) - base < depth else []
        out += [here / f for f in sorted(filenames) if is_spec_file(Path(f))]
        if visited > MAX_SPEC_SCAN_DIRS or len(out) > MAX_SPECS:
            break
    return out[:MAX_SPECS]


def home_path(path: Path) -> str:
    """``~/…`` form of an absolute path."""
    try:
        return "~/" + str(path.resolve().relative_to(Path.home()))
    except ValueError:
        return str(path)


def _tail(text: str, width: int = 30) -> str:
    """Keep the end of a long path (OptionList wraps instead of cropping)."""
    return text if len(text) <= width else "…" + text[-(width - 1):]


def short_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        home = Path.home()
        try:
            return "~/" + str(path.resolve().relative_to(home))
        except ValueError:
            return str(path)


class CircTree(DirectoryTree):
    """Directory tree that lists folders and ``*.circ`` files matching the quick filter."""

    def __init__(self, path: str | Path, **kw: object) -> None:
        self.filter_text = ""
        super().__init__(path, **kw)  # type: ignore[arg-type]

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        needle = self.filter_text.lower()
        out = []
        for p in paths:
            try:
                is_dir = p.is_dir()
            except OSError:
                continue
            if is_dir:
                if not _skip_dir(p.name):
                    out.append(p)
            elif p.suffix.lower() == ".circ" and needle in p.name.lower():
                out.append(p)
        return out


class PickerScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("slash", "focus_filter", "key.filter", key_display="/"),
                Binding("escape", "focus_tree", show=False)]

    def __init__(self, lang: str, cwd: Path, spec: str | None = None) -> None:
        super().__init__(id="picker")
        self.lang = lang
        self.cwd = cwd
        self.initial_spec = str(Path(spec).resolve()) if spec else None
        self.recent: list[RecentEntry] = []
        self.spec_options: dict[str, str] = {}
        localize_bindings(self, lang)

    # ------------------------------------------------------------- layout
    def compose(self) -> ComposeResult:
        lang = self.lang
        yield Static(Text.assemble(("logilens", "bold magenta"), ("  ·  ", "dim"),
                                   (tr("picker.title", lang), "bold")), id="picker-title")
        with Horizontal(id="picker-body"):
            with Vertical(id="recent-pane", classes="card") as recent:
                recent.border_title = tr("picker.recent", lang)
                yield OptionList(id="recent-list")
                yield Static(Text(tr("picker.recent_empty", lang), style="dim italic"), id="recent-empty")
            with Vertical(id="browse-pane", classes="card") as browse:
                browse.border_title = tr("picker.browse", lang, dir=home_path(self.cwd))
                yield Input(placeholder=tr("picker.filter", lang), id="filter")
                yield CircTree(self.cwd, id="tree")
        with Horizontal(id="picker-bottom"):
            yield Label(tr("picker.spec", lang), classes="control-label")
            yield Select([], id="spec", prompt=tr("picker.spec_none", lang), allow_blank=True)
            yield Button(tr("picker.open", lang), id="open", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_recent()
        self._add_specs(find_specs(self.cwd))
        if self.initial_spec:
            self._add_specs([Path(self.initial_spec)])
            self.query_one("#spec", Select).value = self.initial_spec
        self.query_one("#tree", CircTree).focus()

    def on_screen_resume(self) -> None:
        self.refresh_recent()

    # ------------------------------------------------------------- recent files
    def refresh_recent(self) -> None:
        self.recent = [e for e in self.app.recent.load() if e.exists]  # type: ignore[attr-defined]
        options = self.query_one("#recent-list", OptionList)
        options.clear_options()
        for k, e in enumerate(self.recent):
            p = Path(e.path)
            label = Text.assemble((p.name, "bold"), ("\n  " + _tail(home_path(p.parent)), "dim"))
            if e.spec:
                label.append("\n  ⊕ " + Path(e.spec).name, style="cyan")
            options.add_option(Option(label, id=str(k)))
        self.query_one("#recent-empty", Static).display = not self.recent
        options.display = bool(self.recent)

    # ------------------------------------------------------------- specification
    def _add_specs(self, paths: Iterable[Path]) -> None:
        changed = False
        for p in paths:
            key = str(p.resolve())
            if key not in self.spec_options:
                self.spec_options[key] = short_path(p, self.cwd)
                changed = True
        if not changed:
            return
        select = self.query_one("#spec", Select)
        value = select.value
        select.set_options([(label, key) for key, label in self.spec_options.items()])
        if isinstance(value, str) and value in self.spec_options:
            select.value = value

    def selected_spec(self) -> str | None:
        value = self.query_one("#spec", Select).value
        return value if isinstance(value, str) and value else None

    # ------------------------------------------------------------- opening
    def open_path(self, path: Path, spec: str | None = None) -> None:
        if path.suffix.lower() != ".circ":
            self.app.notify(tr("picker.not_circ", self.lang), severity="warning")
            return
        if not path.is_file():
            self.app.notify(tr("picker.missing", self.lang, path=str(path)), severity="error")
            return
        self.app.open_file(path, self.selected_spec() or spec)  # type: ignore[attr-defined]

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        event.stop()
        self.open_path(Path(event.path))

    def on_tree_node_highlighted(self, event: CircTree.NodeHighlighted) -> None:  # type: ignore[name-defined]
        data = getattr(event.node, "data", None)
        path = getattr(data, "path", None)
        if isinstance(path, Path) and path.suffix.lower() == ".circ":
            try:
                self._add_specs(p for p in path.parent.iterdir() if p.is_file() and is_spec_file(p))
            except OSError:
                pass

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "recent-list" or event.option.id is None:
            return
        event.stop()
        entry = self.recent[int(event.option.id)]
        spec = entry.spec if entry.spec and Path(entry.spec).is_file() else None
        self.open_path(Path(entry.path), spec)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "open":
            return
        event.stop()
        tree = self.query_one("#tree", CircTree)
        node = tree.cursor_node
        path = getattr(getattr(node, "data", None), "path", None)
        if isinstance(path, Path) and path.is_file():
            self.open_path(path)
        else:
            self.app.notify(tr("picker.not_circ", self.lang), severity="warning")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter":
            return
        tree = self.query_one("#tree", CircTree)
        tree.filter_text = event.value.strip()
        tree.reload()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter":
            event.stop()
            self.action_focus_tree()

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_focus_tree(self) -> None:
        self.query_one("#tree", CircTree).focus()


__all__ = ["CircTree", "PickerScreen", "find_specs", "is_spec_file"]
