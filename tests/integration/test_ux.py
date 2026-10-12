"""First-run experience: language choice, help texts, error messages, output wording."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from logilens.cli.app import app
from logilens.i18n import LANGS, system_lang

GEN = Path(__file__).resolve().parents[1] / "fixtures" / "gen"
NOT_GATE = str(GEN / "dangling_wire.circ")
FSM = str(GEN / "moore_fsm.circ")
PY = ("--backend", "python")
NO_LOCALE = {"LC_ALL": None, "LC_MESSAGES": None, "LANG": None, "LOGILENS_LANG": None}
COMMANDS = ("parse", "lint", "analyze", "check", "seq", "report", "doctor", "setup")


def run(*args: str, columns: int = 200, **env: str | None) -> Any:
    runner = CliRunner(env={**NO_LOCALE, "COLUMNS": str(columns), **env})
    return runner.invoke(app, list(args), catch_exceptions=False)


# ------------------------------------------------------------------ language


@pytest.mark.parametrize(("env", "expected"), [
    ({}, "en"),
    ({"LANG": "ru_RU.UTF-8"}, "ru"),
    ({"LANG": "sk_SK.UTF-8"}, "sk"),
    ({"LANG": "de_DE.UTF-8"}, "en"),
    ({"LANG": "C"}, "en"),
    ({"LANG": "ru_RU.UTF-8", "LC_ALL": "en_US.UTF-8"}, "en"),
    ({"LC_MESSAGES": "sk_SK", "LANG": "en_US"}, "sk"),
])
def test_system_lang(monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected: str) -> None:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    assert system_lang() == expected


def test_default_language_follows_locale() -> None:
    assert "Commands:" in run().stdout
    assert "Команды" in run(LANG="ru_RU.UTF-8").stdout
    assert "Príkazy" in run(LANG="sk_SK.UTF-8").stdout


def test_lang_option_and_env_override_locale() -> None:
    assert "Commands:" in run("--lang", "en", LANG="ru_RU.UTF-8").stdout
    assert "Commands:" in run(LANG="ru_RU.UTF-8", LOGILENS_LANG="en").stdout
    assert "Команды" in run("--lang", "RU").stdout


@pytest.mark.parametrize("lang", LANGS)
def test_overview_has_no_placeholder_text(lang: str) -> None:
    out = run("--lang", lang).stdout.lower()
    for word in ("next stage", "следующем этапе", "ďalšej etape", "todo", "coming soon"):
        assert word not in out


# ------------------------------------------------------------------ help


def test_root_help_has_examples() -> None:
    out = run("--help").stdout
    assert "Examples" in out and "logilens lint" in out


@pytest.mark.parametrize("command", COMMANDS)
def test_command_help_has_examples(command: str) -> None:
    result = run(command, "--help")
    assert result.exit_code == 0
    assert "Examples" in result.stdout
    assert "prechodová" not in result.stdout  # no stray Slovak in the English help


def test_help_lists_choices() -> None:
    assert "auto|java|python" in run("--help").stdout
    assert "auto|sop|pos|both" in run("analyze", "--help").stdout
    assert "rich|md|html|json" in run("report", "--help").stdout


# ------------------------------------------------------------------ mistakes


@pytest.mark.parametrize("args", [
    ("--lang", "de", "doctor"),
    ("--backend", "jav", "doctor"),
    ("analyze", NOT_GATE, "--form", "xyz"),
    ("report", NOT_GATE, "--format", "pdf"),
    ("lint", NOT_GATE, "--min-severity", "loud"),
    ("lint", NOT_GATE, "--only", "nand,foo"),
    ("analyze", NOT_GATE, "--methods", "foo"),
])
def test_bad_option_values_are_usage_errors(args: tuple[str, ...]) -> None:
    result = run(*PY, *args)
    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert "Invalid value" in result.output


def test_unknown_gate_lists_known_ones() -> None:
    result = run(*PY, "lint", NOT_GATE, "--only", "nand,foo")
    assert "foo" in result.output and "nor" in result.output


def test_missing_and_empty_files(tmp_path: Path) -> None:
    assert run("lint", str(tmp_path / "nope.circ")).exit_code == 2
    empty = tmp_path / "empty.circ"
    empty.write_text("", encoding="utf-8")
    result = run(*PY, "lint", str(empty))
    assert result.exit_code == 2 and "is empty" in result.output


def test_root_with_missing_file() -> None:
    result = run("nope.circ")
    assert result.exit_code == 2 and "File not found: nope.circ" in result.output


@pytest.mark.parametrize("content", ["just some notes\n", "<project><circuit", "<html><body/></html>"])
def test_not_a_circuit_explains_what_to_do(tmp_path: Path, content: str) -> None:
    bad = tmp_path / "bad.circ"
    bad.write_text(content, encoding="utf-8")
    result = run(*PY, "--lang", "en", "lint", str(bad))
    assert result.exit_code == 3
    assert "Logisim" in result.output and "--debug" not in result.output
    assert "Traceback" not in result.output


def test_bad_spec_explains_the_format(tmp_path: Path) -> None:
    spec = tmp_path / "task.txt"
    spec.write_text("hello\n", encoding="utf-8")
    result = run(*PY, "--lang", "en", "check", NOT_GATE, "--spec", str(spec))
    assert result.exit_code == 3
    assert "specification could not be read" in result.output and "truth table" in result.output


def test_unknown_circuit_name_points_to_parse() -> None:
    result = run(*PY, "--lang", "en", "analyze", NOT_GATE, "--circuit", "nope")
    assert result.exit_code == 2
    assert "'nope'" in result.output and "logilens parse" in result.output


def test_unwritable_output_path(tmp_path: Path) -> None:
    out = tmp_path / "missing" / "report.md"
    result = run(*PY, "--lang", "en", "report", NOT_GATE, "-f", "md", "-o", str(out))
    assert result.exit_code == 2
    assert "No such file or directory" in result.output and "Errno" not in result.output


def test_error_lines_wrap_with_indent() -> None:
    result = run(*PY, "--lang", "en", "analyze", NOT_GATE, "--circuit", "nope", columns=60)
    lines = result.output.splitlines()
    assert all(len(line) <= 60 for line in lines)
    assert all(line == line.rstrip() for line in lines)
    assert all(line.startswith("  ") for line in lines[1:])


# ------------------------------------------------------------------ output wording


def test_english_analysis_uses_plain_words() -> None:
    result = run(*PY, "--lang", "en", "analyze", NOT_GATE, "--no-kmap", columns=100)
    out = result.stdout
    assert "minimal SOP" in out and "as NAND/NOR" in out
    assert "a↑b = NAND(a, b)" in out
    for word in ("course", "MDNF", "MKNF", "gates_inputs", "min_negators", "1 inputs"):
        assert word not in out, word


def test_method_table_fits_80_columns() -> None:
    out = run(*PY, "--lang", "en", "analyze", NOT_GATE, "--no-kmap", columns=80).stdout
    assert "exhaustive:per-output" in out  # not cut with an ellipsis
    assert all(len(line) <= 80 for line in out.splitlines())


@pytest.mark.parametrize("fmt", ["md", "html"])
def test_exports_use_plain_words(fmt: str) -> None:
    out = run(*PY, "--lang", "en", "report", NOT_GATE, "-f", fmt).stdout
    assert "gates_inputs" not in out and "course" not in out
    assert "NAND(a, b)" in out


def test_doctor_narrow_terminal_is_a_list() -> None:
    out = run("--lang", "en", "doctor", columns=60).stdout
    assert "╭" not in out and "Python" in out
    home = str(Path.home())
    assert home == "/" or home not in out


def test_seq_runs_on_fsm() -> None:
    result = run(*PY, "--lang", "en", "seq", FSM)
    assert result.exit_code == 0 and "Traceback" not in result.output


def test_no_color_and_pipe_have_no_escape_codes() -> None:
    out = run(*PY, "--lang", "en", "lint", NOT_GATE, NO_COLOR="1").stdout
    assert "\x1b[" not in out


# ------------------------------------------------------------------ internals behind the UX


def test_gate_tokens_match_lint() -> None:
    from logilens.cli.options import GATE_TOKENS
    from logilens.lint.engine import GATE_TYPES

    assert set(GATE_TOKENS) == set(GATE_TYPES.values())


def test_help_does_not_import_heavy_modules() -> None:
    code = ("import sys, logilens.cli.app; "
            "print(','.join(m for m in ('scipy', 'numpy', 'textual') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == ""


def test_run_quiet_missing_tool() -> None:
    from logilens.env.tools import run_quiet

    code, text = run_quiet(["/nonexistent/logilens-tool"])
    assert code == -1 and text


def test_recent_save_cleans_up_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from logilens.tui.recent import RecentFiles

    recent = RecentFiles(tmp_path / "recent.json")

    def fail(*_: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    recent.add(NOT_GATE)
    assert not list(tmp_path.glob(".recent-*"))


def test_espresso_force_keeps_other_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from logilens.env import espresso_build as eb

    src = tmp_path / "src"
    src.mkdir()
    (src / "Makefile").write_text("all:\n\tmkdir -p ../bin && touch ../bin/espresso && chmod +x ../bin/espresso\n",
                                  encoding="utf-8")
    cache = tmp_path / "cache" / "espresso"
    (cache / "espresso-src").mkdir(parents=True)
    (cache / "espresso-src" / "stale.o").write_text("", encoding="utf-8")
    keep = tmp_path / "cache" / "logisim.jar"
    keep.write_text("jar", encoding="utf-8")
    monkeypatch.setattr(eb, "source_dir", lambda: src)
    monkeypatch.setattr(eb, "cache_dir", lambda: cache)
    if not eb.toolchain_available():
        pytest.skip("make / cc not available")
    result = eb.build_espresso(force=True)
    assert result.ok, result.log
    assert keep.exists() and not (cache / "espresso-src" / "stale.o").exists()
