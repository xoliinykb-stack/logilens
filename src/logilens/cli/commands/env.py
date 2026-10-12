"""``doctor``, ``setup`` and ``cache clear`` commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from logilens.cli.errors import EXIT_ENV, EXIT_OK
from logilens.cli.options import JsonOpt, examples
from logilens.cli.state import state_of
from logilens.env.doctor import Check, Status, healthy, run_checks, setup
from logilens.env.paths import cache_dir, cache_entries, clear_cache
from logilens.i18n import t

STATUS_STYLE = {Status.OK: ("✓", "green"), Status.WARN: ("!", "yellow"), Status.FAIL: ("✗", "bold red"),
                Status.INFO: ("·", "cyan")}

cache_app = typer.Typer(help="Manage the cache (compiled Logisim helper, Espresso build).", no_args_is_help=True)

DOCTOR_EXAMPLES = examples(("logilens doctor", ""), ("logilens doctor --fix", "also build what is missing"),
                           ("logilens --logisim-jar ~/logisim.jar doctor", "use a specific Logisim jar"))
SETUP_EXAMPLES = examples(("logilens setup", ""), ("logilens setup --force", "rebuild from scratch"))
NARROW = 90


def short_path(text: str) -> str:
    """``/Users/me/x`` -> ``~/x`` (paths in doctor output get long)."""
    home = str(Path.home())
    return text.replace(home, "~") if home and home != "/" else text


def check_detail(c: Check, lang: str) -> str:
    return short_path(t(c.note, lang, extra=c.extra) if c.note else c.detail)


def doctor_table(checks: list[Check], lang: str) -> Table:
    table = Table(box=box.ROUNDED, title=t("doctor.title", lang), title_justify="left", title_style="bold magenta")
    table.add_column("", width=1)
    table.add_column(t("doctor.component", lang), style="bold", no_wrap=True)
    table.add_column(t("doctor.detail", lang), overflow="fold")
    table.add_column(t("doctor.fix", lang), style="dim", overflow="fold")
    for c in checks:
        icon, style = STATUS_STYLE[c.status]
        table.add_row(Text(icon, style=style), t(f"doctor.check.{c.name}", lang), check_detail(c, lang),
                      t(c.fix, lang) if c.fix else "")
    return table


def doctor_list(checks: list[Check], lang: str) -> RenderableType:
    """Same content as :func:`doctor_table`, one check per line, for narrow terminals."""
    lines: list[RenderableType] = [Text(t("doctor.title", lang), style="bold magenta")]
    for c in checks:
        icon, style = STATUS_STYLE[c.status]
        lines.append(Text.assemble((f"{icon} ", style), (t(f"doctor.check.{c.name}", lang), "bold"), "  ",
                                   check_detail(c, lang)))
        if c.fix:
            lines.append(Text("  → " + t(c.fix, lang), style="dim"))
    return Group(*lines)


def doctor_cmd(
    ctx: typer.Context,
    fix: Annotated[bool, typer.Option("--fix", help="Build the Java helper and Espresso when possible.")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Check what logilens can use on this machine: Python, Java, Logisim, Espresso, Graphviz.

    Only Python is required; everything else unlocks extra features. Exits with 4 when a check failed.
    """
    st = state_of(ctx)

    def body() -> int:
        checks = run_checks(st.jar, fix=fix)
        ok = healthy(checks)
        if as_json:
            st.echo(json.dumps({"schema": "logilens/doctor@1", "healthy": ok,
                                "checks": [c.to_dict() for c in checks]}, ensure_ascii=False, indent=2))
        else:
            view = doctor_list if st.console.width < NARROW else doctor_table
            st.console.print(view(checks, st.lang))
            key = "doctor.healthy" if ok else "doctor.unhealthy"
            st.console.print(Text(("✓ " if ok else "✗ ") + t(key, st.lang), style="bold green" if ok else "bold red"))
        return EXIT_OK if ok else EXIT_ENV

    st.run(body)


def setup_cmd(
    ctx: typer.Context,
    force: Annotated[bool, typer.Option("--force", help="Rebuild even if builds exist.")] = False,
) -> None:
    """Build the optional helpers: the Logisim bridge (needs Java and Logisim) and the Espresso minimizer.

    Safe to run again; builds go to the user cache, never into the project.
    """
    st = state_of(ctx)

    def body() -> int:
        with st.console.status(t("setup.building", st.lang)):
            steps = setup(st.jar, force=force)
        for step in steps:
            icon, style = ("✓", "green") if step.ok else ("!", "yellow") if step.note else ("✗", "red")
            detail = t(step.note, st.lang) if step.note else step.detail
            st.console.print(Text.assemble((f"{icon} ", style), (t(f"doctor.check.{step.name}", st.lang), "bold"),
                                           ("  " + short_path(detail), "dim")))
        espresso_ok = all(s.ok for s in steps if s.name == "espresso")
        return EXIT_OK if espresso_ok else EXIT_ENV

    st.run(body)


@cache_app.command("clear")
def cache_clear(
    ctx: typer.Context,
    include_jar: Annotated[bool, typer.Option("--all", help="Also delete a downloaded logisim.jar.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Only list what would be deleted.")] = False,
) -> None:
    """Delete cached builds (they are recreated on demand)."""
    st = state_of(ctx)

    def body() -> int:
        entries = cache_entries(include_jar) if dry_run else clear_cache(include_jar)
        key = "cache.would_remove" if dry_run else "cache.removed"
        st.console.print(Text(t(key, st.lang, count=len(entries), path=short_path(str(cache_dir()))), style="bold"))
        for entry in entries:
            st.console.print(Text("  " + short_path(str(entry)), style="dim"))
        return EXIT_OK

    st.run(body)
