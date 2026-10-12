"""End-to-end CLI tests on the reference circuits."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from cli_support import CONVERTER, DRAFT, FIXTURES, MIXED, SPEC, Cli

from logilens.i18n import LANGS, missing_keys

PY = ("--backend", "python")


def _groups(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {",".join(g["outputs"]): g for g in report["groups"]}


def _reference(group: dict[str, Any]) -> tuple[int, int] | None:
    form = group["verdict_form"]
    fr = next(f for f in group["forms"] if f["form"] == form)
    ref = fr["reference"]
    return (ref["gates"], ref["inputs"]) if ref else None


def _drawn(group: dict[str, Any]) -> tuple[int, int]:
    return group["structural"]["gates"], group["structural"]["inputs"]


# ------------------------------------------------------------------ entry point


def test_no_args_prints_tui_notice_and_commands(cli: Cli) -> None:
    result = cli("--lang", "en")
    assert result.exit_code == 0
    assert "TUI" in result.stdout and "analyze" in result.stdout and "doctor" in result.stdout


def test_file_only_prints_notice(cli: Cli) -> None:
    result = cli("--lang", "en", CONVERTER)
    assert result.exit_code == 0
    assert "converter_nand_nor.circ" in result.stdout and "logilens analyze" in result.stdout


def test_default_language_is_english_without_locale(cli: Cli) -> None:
    assert "Commands:" in cli().stdout


def test_version(cli: Cli) -> None:
    result = cli("--version")
    assert result.exit_code == 0 and result.stdout.startswith("logilens ")


# ------------------------------------------------------------------ converter_nand_nor (corrected circuit)


def _check_converter(report: dict[str, Any]) -> None:
    assert report["schema"] == "logilens/report@1"
    groups = _groups(report)
    nand, nor = groups["A_N,B_N,C_N,D_N"], groups["A_R,B_R,C_R,D_R"]
    assert nand["verdict"] == nor["verdict"] == "optimal"
    assert (nand["technology"], nor["technology"]) == ("nand", "nor")
    assert _drawn(nand) == (19, 48) and _drawn(nor) == (18, 45)
    assert _reference(nand) == (19, 48) and _reference(nor) == (18, 45)
    proof = next(r for f in nand["forms"] for r in f["rows"] if r["method"] == "ilp")["proof"]
    assert proof == "ilp:Optimal"
    assert report["spec"]["rows_ok_by_group"] == {"*_N": 12, "*_R": 12}
    assert report["spec_passed"] is True and report["overall_verdict"] == "optimal"
    assert report["lint"]["problems"] == 0


def test_converter_analyze_optimal(cli: Cli) -> None:
    code, report = cli.json(*PY, "analyze", CONVERTER, "--spec", SPEC, "--json")
    assert code == 0
    _check_converter(report)


@pytest.mark.java
def test_converter_analyze_optimal_java(cli: Cli) -> None:
    code, report = cli.json("--backend", "java", "analyze", CONVERTER, "--spec", SPEC, "--json")
    assert code == 0 and report["backend"] == "java"
    _check_converter(report)


def test_converter_rich_output(cli: Cli) -> None:
    result = cli(*PY, "--lang", "en", "analyze", CONVERTER, "--spec", SPEC)
    assert result.exit_code == 0
    out = result.stdout
    assert "OPTIMAL" in out and "19/48" in out and "18/45" in out and "12/12" in out
    assert "ilp:Optimal" in out and "Rewriting to NAND" in out


def test_converter_check_12_of_12(cli: Cli) -> None:
    result = cli(*PY, "--lang", "en", "check", CONVERTER, "--spec", SPEC)
    assert result.exit_code == 0
    assert result.stdout.count("12/12") == 2
    code, data = cli.json(*PY, "check", CONVERTER, "--spec", SPEC, "--json")
    assert code == 0 and data["passed"] is True and data["spec"]["rows_checked"] == 12


def test_check_fails_on_wrong_spec(cli: Cli, tmp_path: Path) -> None:
    text = Path(SPEC).read_text(encoding="utf-8").replace("4  01001 0100", "4  01001 0101")
    bad = tmp_path / "bad.spec.txt"
    bad.write_text(text, encoding="utf-8")
    code, data = cli.json(*PY, "check", CONVERTER, "--spec", str(bad), "--json")
    assert code == 1 and data["passed"] is False
    assert {(m["inputs"], m["output"]) for m in data["spec"]["mismatches"]} == {("01001", "D")}


# ------------------------------------------------------------------ DRAFT (improvable version)


def test_draft_lint_gate_set(cli: Cli) -> None:
    code, data = cli.json(*PY, "lint", DRAFT, "--only", "nand,nor", "--json")
    assert code == 1
    counts = Counter(i["rule"] for i in data["issues"])
    assert counts["L011"] == 10 and counts["L001"] == 1 and counts["L002"] == 2
    (loose,) = [i for i in data["issues"] if i["rule"] == "L001"]
    assert loose["component"] == "NOR (480,750)" and loose["loc"] == [420, 770]


def test_draft_lint_rich_exit_code(cli: Cli) -> None:
    result = cli(*PY, "--lang", "en", "lint", DRAFT, "--only", "nand,nor", "--min-severity", "error")
    assert result.exit_code == 1 and "L011" in result.stdout and "NOR (480,750)" in result.stdout


def test_draft_analyze_improvable(cli: Cli) -> None:
    code, report = cli.json(*PY, "analyze", DRAFT, "--spec", SPEC, "--json")
    assert code == 1
    groups = list(report["groups"])
    assert [g["verdict"] for g in groups] == ["improvable", "improvable"]
    nand, nor = groups
    assert (nand["technology"], nor["technology"]) == ("nand", "nor")
    assert _drawn(nand) == (22, 52) and _reference(nand) == (19, 48)
    assert _drawn(nor) == (23, 51) and _reference(nor) == (18, 45)
    assert nand["structural"]["not_gates"] == nor["structural"]["not_gates"] == 5
    assert nor["structural"]["unconnected_inputs"] == 1
    assert report["spec_passed"] is True  # functionally correct
    assert set(report["spec"]["how"].values()) == {"function"}  # unlabeled outputs matched by behavior
    assert any(n["key"] == "note.tied_auto" for n in report["notes"])
    assert {r["key"] for r in report["recommendations"]} >= {"rec.improve"}


def test_draft_rich_shows_improvement(cli: Cli) -> None:
    result = cli(*PY, "--lang", "en", "analyze", DRAFT, "--spec", SPEC, "--no-kmap")
    out = result.stdout
    assert "CAN BE IMPROVED" in out and "22/52" in out and "19/48" in out and "23/51" in out and "18/45" in out


# ------------------------------------------------------------------ mixed_gates (multi-level)


def test_mixed_gates_beyond_two_level(cli: Cli) -> None:
    code, report = cli.json(*PY, "analyze", MIXED, "--json")
    assert report["overall_verdict"] == "beyond_two_level"
    x = _groups(report)["x"]
    assert x["verdict"] == "beyond_two_level" and x["recovered"] == "beyond_two_level"
    assert x["delta"] is None
    assert any(m["key"] == "limit.no_spec" for m in report["limitations"])
    assert code == 1  # unlabeled output pins are lint warnings


# ------------------------------------------------------------------ reports


@pytest.mark.parametrize("fmt", ["md", "html", "json", "rich"])
def test_report_formats(cli: Cli, tmp_path: Path, fmt: str) -> None:
    out = tmp_path / f"draft.{fmt}"
    result = cli(*PY, "--lang", "sk", "report", DRAFT, "--spec", SPEC, "--format", fmt, "-o", str(out), "--no-image")
    assert result.exit_code == 1  # DRAFT has findings
    text = out.read_text(encoding="utf-8")
    if fmt == "json":
        assert json.loads(text)["schema"] == "logilens/report@1"
    elif fmt == "html":
        assert text.startswith("<!doctype html>") and "class='kmap'" in text and "prefers-color-scheme" in text
    elif fmt == "md":
        assert text.startswith("# logilens") and "22/52" in text
    else:
        assert "22/52" in text


def test_report_to_stdout_markdown(cli: Cli) -> None:
    result = cli(*PY, "--lang", "en", "report", CONVERTER, "--spec", SPEC, "--format", "md")
    assert result.exit_code == 0 and "## Optimality summary" in result.stdout


@pytest.mark.java
def test_html_report_embeds_logisim_drawing(cli: Cli, tmp_path: Path) -> None:
    out = tmp_path / "z.html"
    result = cli("--backend", "java", "report", CONVERTER, "--spec", SPEC, "--format", "html", "-o", str(out))
    assert result.exit_code == 0
    assert "data:image/png;base64," in out.read_text(encoding="utf-8")


# ------------------------------------------------------------------ other commands


def test_parse_json(cli: Cli) -> None:
    code, data = cli.json(*PY, "parse", MIXED, "--json")
    assert code == 0 and data["schema"] == "logilens/parse@1"
    assert [p["name"] for p in data["circuits"][0]["inputs"]] == ["P", "Q", "R"]


def test_doctor_runs(cli: Cli) -> None:
    result = cli("doctor", "--json")
    assert result.exit_code in (0, 4)
    data = json.loads(result.stdout)
    names = [c["name"] for c in data["checks"]]
    assert names[:2] == ["python", "java"] and "espresso" in names and "cache" in names
    rich = cli("--lang", "en", "doctor")
    assert "Python" in rich.stdout


def test_seq_command(cli: Cli) -> None:
    code, data = cli.json(*PY, "seq", str(FIXTURES / "gen" / "moore_fsm.circ"), "--json")
    assert code == 0 and data["schema"] == "logilens/seq@1"


def test_cache_clear_dry_run(cli: Cli) -> None:
    assert cli("cache", "clear", "--dry-run").exit_code == 0


# ------------------------------------------------------------------ errors and i18n


def test_missing_file_is_usage_error(cli: Cli) -> None:
    assert cli("analyze", "no-such-file.circ").exit_code == 2


def test_broken_file_is_parse_error(cli: Cli, tmp_path: Path) -> None:
    bad = tmp_path / "bad.circ"
    bad.write_text("<project><circuit", encoding="utf-8")
    result = cli(*PY, "--lang", "en", "analyze", str(bad))
    assert result.exit_code == 3
    assert "Traceback" not in result.output


def test_bad_option_value(cli: Cli) -> None:
    assert cli(*PY, "analyze", CONVERTER, "--form", "xyz").exit_code == 2
    assert cli("--lang", "de", "doctor").exit_code == 2


@pytest.mark.parametrize("lang", LANGS)
def test_catalogs_complete(lang: str) -> None:
    assert missing_keys(lang) == []
