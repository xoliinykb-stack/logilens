"""Interactive terminal UI (Textual): file picker, seven analysis tabs, export.

Import is lazy so that the plain CLI does not pay for loading Textual.
"""

from __future__ import annotations

from pathlib import Path


def run_tui(file: str | Path | None = None, spec: str | Path | None = None, *, lang: str = "ru",
            backend: str = "auto", jar: str | None = None, only: str | None = None) -> None:
    """Start the TUI (blocks until the user quits)."""
    from logilens.tui.app import run_tui as _run

    _run(file, spec, lang=lang, backend=backend, jar=jar, only=only)


__all__ = ["run_tui"]
