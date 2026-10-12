"""Option types and checks shared by the sub-commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from logilens.i18n import t

# Kept in sync with logilens.lint.engine.GATE_TYPES (not imported here to keep startup fast).
GATE_TOKENS = ("and", "or", "nand", "nor", "xor", "xnor", "not", "buffer", "odd_parity", "even_parity",
               "controlled_buffer", "controlled_inverter")


def _lang(ctx: typer.Context) -> str:
    from logilens.cli.state import state_of

    return state_of(ctx).lang


def check_circuit_file(ctx: typer.Context, value: Path | None) -> Path | None:
    """Reject an empty file before the parser turns it into an XML error."""
    if value is not None and value.is_file() and value.stat().st_size == 0:
        raise typer.BadParameter(t("error.empty_file", _lang(ctx), path=str(value)))
    return value


def check_only(ctx: typer.Context, value: str | None) -> str | None:
    """``--only nand,nor``: every name must be a known gate type."""
    if value is None:
        return None
    names = [s.strip().lower().replace(" ", "_") for s in value.split(",") if s.strip()]
    unknown = [n for n in names if n not in GATE_TOKENS]
    if not names or unknown:
        raise typer.BadParameter(t("error.bad_gates", _lang(ctx), gates=", ".join(unknown) or value,
                                   known=", ".join(GATE_TOKENS)))
    return value


def examples(*lines: tuple[str, str]) -> str:
    """Help epilog: ``(command, comment)`` pairs."""
    rows = [f"  [cyan]{cmd}[/cyan]" + (f"  [dim]# {note}[/dim]" if note else "") for cmd, note in lines]
    return "[bold]Examples[/bold]\n\n" + "\n".join(rows)


FileArg = Annotated[Path, typer.Argument(metavar="FILE", help="Logisim .circ file.", exists=True, dir_okay=False,
                                         readable=True, callback=check_circuit_file)]
JsonOpt = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON instead of tables.")]
CircuitOpt = Annotated[str | None, typer.Option("--circuit", metavar="NAME",
                                                help="Circuit to analyze (default: the main circuit).")]
OnlyOpt = Annotated[str | None, typer.Option("--only", metavar="GATES", callback=check_only,
                                             help="Allowed gate types, e.g. nand,nor; anything else is reported.")]
