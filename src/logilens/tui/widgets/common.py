"""Small helpers shared by the TUI screens and widgets."""

from __future__ import annotations

import dataclasses
import io
from typing import Any

from rich.console import Console
from textual.dom import DOMNode

from logilens.tui.i18n import tr


def localize_bindings(node: DOMNode, lang: str) -> None:
    """Translate binding descriptions that are i18n keys (``key.*``) for the Footer.

    Textual bindings are declared on the class; descriptions are replaced per instance so the language chosen
    with ``--lang`` is shown. Silently does nothing if Textual's internals change.
    """
    try:
        mapping = node._bindings.key_to_bindings
    except AttributeError:
        return
    for key, bindings in list(mapping.items()):
        mapping[key] = [dataclasses.replace(b, description=tr(b.description, lang))
                        if b.description.startswith("key.") else b for b in bindings]


def plain_text(renderable: Any, width: int = 160) -> str:
    """Render a Rich renderable (or a Static's content) to plain text — used by tests and screenshots."""
    console = Console(width=width, record=True, color_system=None, file=io.StringIO())
    console.print(renderable if renderable is not None else "")
    return console.export_text()


__all__ = ["localize_bindings", "plain_text"]
