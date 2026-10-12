"""Exception -> friendly message + exit code (tracebacks only with ``--debug``)."""

from __future__ import annotations

import textwrap
import traceback
from collections.abc import Callable

import typer
from rich.console import Console
from rich.text import Text

from logilens.core.errors import (
    BackendError,
    LogilensError,
    NotFoundError,
    ParseError,
    SimulationError,
    UnsupportedError,
)
from logilens.i18n import t
from logilens.spec.parse import SpecError

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_PARSE = 3
EXIT_ENV = 4


def classify_error(exc: BaseException) -> tuple[int, str]:
    """``(exit code, i18n key of the headline)``."""
    if isinstance(exc, BackendError):
        return EXIT_ENV, "error.backend"
    if isinstance(exc, NotFoundError):
        return EXIT_USAGE, "error.not_found"
    if isinstance(exc, SpecError):
        return EXIT_PARSE, "error.spec"
    if isinstance(exc, ParseError):
        return EXIT_PARSE, "error.parse"
    if isinstance(exc, (UnsupportedError, SimulationError)):
        return EXIT_PARSE, "error.unsupported"
    if isinstance(exc, LogilensError):
        return EXIT_PARSE, "error.generic"
    if isinstance(exc, (FileNotFoundError, IsADirectoryError, PermissionError)):
        return EXIT_USAGE, "error.file"
    if isinstance(exc, ValueError):
        return EXIT_USAGE, "error.usage"
    return EXIT_PARSE, "error.internal"


# Headlines that come with a "what to do next" line.
ERROR_HINTS = {
    "error.backend": "error.backend.hint",
    "error.spec": "error.spec.hint",
    "error.parse": "error.parse.hint",
    "error.not_found": "error.not_found.hint",
}
# Only these are worth a --debug run; the rest are the user's input, not a bug.
DEBUG_HINT = {"error.backend", "error.unsupported", "error.generic", "error.internal"}


def error_detail(exc: BaseException) -> str:
    if isinstance(exc, NotFoundError):
        return str(exc)
    if isinstance(exc, OSError) and exc.strerror:
        return f"{exc.filename}: {exc.strerror}" if exc.filename else exc.strerror
    return str(exc)


def _indented(console: Console, text: str, style: str) -> None:
    width = max(console.width - 2, 20)
    for line in text.splitlines() or [""]:
        for part in textwrap.wrap(line, width, break_on_hyphens=False) or [""]:
            console.print(Text("  " + part, style=style), soft_wrap=True)


def report_error(exc: BaseException, console: Console, lang: str, debug: bool) -> int:
    """Print the error for humans and return the exit code."""
    code, key = classify_error(exc)
    console.print(Text("✗ " + t(key, lang), style="bold red"))
    detail = error_detail(exc)
    if detail:
        _indented(console, detail, "red")
    if key in ERROR_HINTS:
        _indented(console, t(ERROR_HINTS[key], lang), "yellow")
    stderr = getattr(exc, "stderr", "")
    if stderr and debug:
        console.print(Text(stderr.strip()[-2000:], style="dim"))
    if debug:
        console.print(Text("".join(traceback.format_exception(exc)), style="dim"))
    elif key in DEBUG_HINT:
        console.print(Text("  " + t("error.debug_hint", lang), style="dim"))
    return code


def guarded(body: Callable[[], int | None], console: Console, lang: str, debug: bool) -> None:
    """Run a command body, translating exceptions; always ends with ``typer.Exit``."""
    try:
        code = body() or EXIT_OK
    except typer.Exit:
        raise
    except KeyboardInterrupt:
        raise typer.Exit(130) from None
    except Exception as exc:  # noqa: BLE001 - the CLI boundary turns every error into a message
        code = report_error(exc, console, lang, debug)
    raise typer.Exit(code)
