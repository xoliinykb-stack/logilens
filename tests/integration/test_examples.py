"""The README quick start, run on examples/ with the Python engine (no Java needed)."""

from __future__ import annotations

from pathlib import Path

from cli_support import Cli

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SPEC = str(EXAMPLES / "converter.spec.txt")
PY = ("--lang", "en", "--backend", "python")


def test_lint_finds_the_draft_mistakes(cli: Cli) -> None:
    code, data = cli.json(*PY, "lint", "--json", str(EXAMPLES / "converter_draft.circ"))
    assert code == 1
    rules = {issue["rule"] for issue in data["issues"]}
    assert {"L001", "L002", "L009", "L014"} <= rules


def test_check_passes_on_the_corrected_circuit(cli: Cli) -> None:
    result = cli(*PY, "check", "--spec", SPEC, str(EXAMPLES / "converter_nand_nor.circ"))
    assert result.exit_code == 0
    assert result.stdout.count("12/12 rows correct") == 2


def test_analyze_reports_the_draft_as_improvable(cli: Cli) -> None:
    code, data = cli.json(*PY, "analyze", "--json", "--no-kmap", "--methods", "qm+petrick", "--spec", SPEC,
                          str(EXAMPLES / "converter_draft.circ"))
    assert code == 1
    assert [g["verdict"] for g in data["groups"]] == ["improvable", "improvable"]


def test_seq_reads_the_moore_machine(cli: Cli) -> None:
    code, data = cli.json(*PY, "seq", "--json", "--input", "0110", str(EXAMPLES / "moore_fsm.circ"))
    assert code == 0
    assert data["fsm"]["kind"] == "moore" and data["fsm"]["ff_kinds"] == ["D", "D"]
    assert data["timing"] is not None


def test_spec_kind_is_translated(cli: Cli) -> None:
    args = ("--backend", "python", "analyze", "--no-kmap", "--methods", "qm+petrick", "--spec", SPEC,
            str(EXAMPLES / "converter_nand_nor.circ"))
    assert "converter.spec.txt (таблица кодов, строк: 12)" in cli("--lang", "ru", *args).stdout
    assert "converter.spec.txt (code table, 12 rows)" in cli("--lang", "en", *args).stdout


def test_unknown_output_or_circuit_is_a_usage_error(cli: Cli) -> None:
    circ = str(EXAMPLES / "converter_nand_nor.circ")
    result = cli(*PY, "analyze", "--outputs", "A_N,TYPO", circ)
    assert result.exit_code == 2 and "'TYPO'" in result.output
    assert cli(*PY, "check", "--spec", SPEC, "--circuit", "nope", circ).exit_code == 2


def test_internal_key_error_is_not_reported_as_user_error() -> None:
    from logilens.cli.errors import EXIT_PARSE, classify_error

    assert classify_error(KeyError("bug")) == (EXIT_PARSE, "error.internal")
