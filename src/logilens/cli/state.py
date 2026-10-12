"""Global CLI state (options given before the sub-command)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from logilens.cli.errors import guarded
from logilens.i18n import system_lang

if TYPE_CHECKING:
    from logilens.analysis.options import Options


@dataclass
class State:
    lang: str = field(default_factory=system_lang)
    backend: str = "auto"
    jar: str | None = None
    debug: bool = False
    no_color: bool = False
    console: Console = field(default_factory=Console)
    err: Console = field(default_factory=lambda: Console(stderr=True))

    def options(self, **kw: object) -> Options:
        """Analysis options with the global settings filled in."""
        from logilens.analysis.options import Options

        return Options(backend=self.backend, jar=self.jar, lang=self.lang, **kw)  # type: ignore[arg-type]

    def run(self, body: Callable[[], int | None]) -> None:
        guarded(body, self.err, self.lang, self.debug)

    def echo(self, text: str) -> None:
        """Raw text to stdout (JSON, Markdown) without rich wrapping or markup."""
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        sys.stdout.flush()


def state_of(ctx: typer.Context) -> State:
    """The :class:`State` stored by the root callback (a default one when invoked directly)."""
    root = ctx.find_root()
    if not isinstance(root.obj, State):
        root.obj = State()
    return root.obj
