"""``logilens`` command line (typer).

Global options come before the sub-command: ``--lang --backend --logisim-jar --debug --no-color --version``.
Without a sub-command the TUI opens (file picker; ``logilens FILE [--spec S]`` opens FILE directly). With
``--no-tui`` or when stdin/stdout is not a terminal (scripts, pipes, tests) a short command overview is printed
instead.

Heavy modules (scipy, textual, the analysis itself) are imported inside the commands so that ``--help`` and
``--version`` stay fast.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any, Literal

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typer.core import TyperGroup

from logilens import __version__
from logilens.cli.commands.analyze import (
    ANALYZE_EXAMPLES,
    CHECK_EXAMPLES,
    REPORT_EXAMPLES,
    analyze_cmd,
    check_cmd,
    report_cmd,
)
from logilens.cli.commands.env import DOCTOR_EXAMPLES, SETUP_EXAMPLES, cache_app, doctor_cmd, setup_cmd
from logilens.cli.commands.inspect import LINT_EXAMPLES, PARSE_EXAMPLES, lint_cmd, parse_cmd
from logilens.cli.commands.seq import SEQ_EXAMPLES, seq_cmd
from logilens.cli.errors import EXIT_USAGE
from logilens.cli.options import check_only, examples
from logilens.cli.state import State
from logilens.i18n import LANGS, normalize_lang, system_lang, t

ROOT_EXAMPLES = examples(("logilens", "interactive view"),
                         ("logilens adder.circ --spec task.txt", "open a file in it"),
                         ("logilens lint adder.circ", "check the wiring"),
                         ("logilens analyze adder.circ --spec task.txt", "minimize, prove"),
                         ("logilens report adder.circ -f html -o report.html", ""),
                         ("logilens --lang sk lint adder.circ", "Slovak output"),
                         ("logilens doctor", "optional tools"))

VALUE_OPTIONS = {"--lang", "--backend", "--logisim-jar", "--spec", "--only"}


class FileAwareGroup(TyperGroup):
    """Lets ``logilens FILE.circ`` through: a leading path that is not a command is kept as ``ctx.meta``."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        args = list(args)
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--":
                break
            if arg.startswith("-"):
                i += 2 if arg in VALUE_OPTIONS else 1
                continue
            if arg not in self.commands and (arg.endswith(".circ") or Path(arg).exists()):
                ctx.meta["logilens.file"] = args.pop(i)
            break
        return super().parse_args(ctx, args)


app = typer.Typer(
    cls=FileAwareGroup,
    name="logilens",
    help="Analyze Logisim 2.7.1 circuits (.circ) in the terminal: wiring checks, truth tables, Karnaugh maps, "
         "minimization with proofs, state machines and reports.\n\n"
         "Run without a command to open the interactive view.",
    epilog=ROOT_EXAMPLES,
    invoke_without_command=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.command("parse", epilog=PARSE_EXAMPLES)(parse_cmd)
app.command("lint", epilog=LINT_EXAMPLES)(lint_cmd)
app.command("analyze", epilog=ANALYZE_EXAMPLES)(analyze_cmd)
app.command("check", epilog=CHECK_EXAMPLES)(check_cmd)
app.command("seq", epilog=SEQ_EXAMPLES)(seq_cmd)
app.command("report", epilog=REPORT_EXAMPLES)(report_cmd)
app.command("doctor", epilog=DOCTOR_EXAMPLES)(doctor_cmd)
app.command("setup", epilog=SETUP_EXAMPLES)(setup_cmd)
app.add_typer(cache_app, name="cache")

COMMAND_KEYS = ("parse", "lint", "analyze", "check", "seq", "report", "doctor", "setup", "cache")


def _version(value: bool) -> None:
    if value:
        typer.echo(f"logilens {__version__}")
        raise typer.Exit()


def welcome(console: Console, lang: str, file: str | None) -> None:
    """Shown instead of the TUI when there is no terminal (or with --no-tui): a short command overview."""
    body = Text(t("cli.intro", lang), style="bold")
    if file:
        body.append("\n" + t("cli.tui_file", lang, file=Path(file).name), style="")
        body.append("\n\n" + t("cli.try_analyze", lang, file=file), style="cyan")
    console.print(Panel(body, title=Text("logilens " + __version__, style="bold magenta"), title_align="left",
                        border_style="magenta"))
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    for name in COMMAND_KEYS:
        table.add_row(name, t(f"cli.cmd.{name}", lang))
    console.print(Text(t("cli.commands", lang), style="bold"))
    console.print(table)
    console.print(Text(t("cli.global", lang), style="dim"))
    console.print(Text(t("cli.help_hint", lang), style="dim"))


@app.callback()
def root(
    ctx: typer.Context,
    lang: Annotated[str | None, typer.Option(
        "--lang", envvar="LOGILENS_LANG", metavar="<" + "|".join(LANGS) + ">", show_default="system language, else en",
        help="Interface language.")] = None,
    backend: Annotated[Literal["auto", "java", "python"], typer.Option(
        "--backend", case_sensitive=False,
        help="Simulation engine: java = real Logisim (needs Java), python = built-in, auto = java if available.")]
    = "auto",
    logisim_jar: Annotated[str | None, typer.Option("--logisim-jar", metavar="PATH",
                                                    help="Path to logisim.jar (version 2.7.1).")] = None,
    debug: Annotated[bool, typer.Option("--debug", help="Show full error details (Python tracebacks).")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Plain output without colors (also: NO_COLOR=1).")]
    = False,
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True,
                                          help="Print the version and exit.")] = False,
    spec: Annotated[str | None, typer.Option("--spec", metavar="FILE",
                                             help="Interactive view: specification for FILE.")] = None,
    only: Annotated[str | None, typer.Option("--only", metavar="GATES", callback=check_only,
                                             help="Interactive view: allowed gate types, e.g. nand,nor.")] = None,
    no_tui: Annotated[bool, typer.Option("--no-tui", help="Print the command overview instead of opening the "
                                                          "interactive view.")] = False,
) -> None:
    """Analyze Logisim circuits in the terminal."""
    console = Console(no_color=no_color, highlight=False)
    err = Console(stderr=True, no_color=no_color, highlight=False)
    if lang is not None and lang.strip().lower() not in LANGS:
        raise typer.BadParameter("'{}' is not one of {}.".format(lang, ", ".join(f"'{x}'" for x in LANGS)), param_hint="'--lang'")
    ctx.obj = State(normalize_lang(lang) if lang else system_lang(), backend.lower(), logisim_jar, debug, no_color,
                    console, err)
    if ctx.invoked_subcommand is None:
        file = ctx.meta.get("logilens.file")
        if file and not Path(file).is_file():
            err.print(Text("✗ " + t("error.no_such_file", ctx.obj.lang, path=file), style="bold red"))
            raise typer.Exit(EXIT_USAGE)
        if no_tui or not interactive():
            welcome(console, ctx.obj.lang, file)
            raise typer.Exit()
        from logilens.tui import run_tui

        run_tui(file, spec, lang=ctx.obj.lang, backend=ctx.obj.backend, jar=logisim_jar, only=only)
        raise typer.Exit()


def interactive() -> bool:
    """The TUI needs a real terminal on both ends."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
