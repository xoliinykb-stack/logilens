"""Structural lint: acceptance numbers on the reference circuits and one fixture per rule."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from logilens.core.geometry import Point
from logilens.lint import Severity, all_rules, count_problems, lint, summarize
from logilens.parse import parse_project

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GEN = FIXTURES / "gen"


def _lint(path: Path, **kw):
    return lint(parse_project(str(path)), **kw)


def test_all_fourteen_rules_registered() -> None:
    assert [r.code for r in all_rules()] == [f"L{i:03d}" for i in range(1, 15)]


def test_converter_clean_with_nand_nor_only() -> None:
    issues = _lint(FIXTURES / "converter_nand_nor.circ", only={"nand", "nor"})
    assert count_problems(issues) == 0
    assert summarize(issues)["error"] == 0 and summarize(issues)["warning"] == 0


def test_draft_ten_not_violations_and_one_loose_nor_input() -> None:
    issues = _lint(FIXTURES / "converter_draft.circ", only="nand,nor")
    l011 = [i for i in issues if i.rule == "L011"]
    assert len(l011) == 10
    assert all(i.component.startswith("NOT ") and i.msg_key == "lint.L011.msg.not" for i in l011)
    assert all(i.severity is Severity.ERROR for i in l011)
    l001 = [i for i in issues if i.rule == "L001"]
    assert len(l001) == 1
    assert l001[0].component == "NOR (480,750)" and l001[0].loc == Point(420, 770)
    assert "(420,770)" in l001[0].message() and "NOR (480,750)" in l001[0].message()
    # duplicated a..e input sets of the two halves are flagged, and so are the two rails that end in the air
    assert sorted(i.loc.y for i in issues if i.rule == "L002") == [2020, 2480]
    assert sorted(i.params["label"] for i in issues if i.rule == "L009") == list("abcde")


def test_sample_four_loose_inputs() -> None:
    issues = _lint(FIXTURES / "sample_bcd_excess3.circ")
    l001 = sorted(i.loc for i in issues if i.rule == "L001")
    assert l001 == [Point(240, 330), Point(240, 610), Point(410, 680), Point(570, 1170)]
    assert all(i.component.startswith("NAND ") for i in issues if i.rule == "L001")
    dangling = {i.loc for i in issues if i.rule == "L002"}
    assert {Point(230, 330), Point(230, 610), Point(400, 680), Point(560, 1170)} <= dangling


def test_no_gate_restriction_without_only() -> None:
    assert not [i for i in _lint(FIXTURES / "converter_draft.circ") if i.rule == "L011"]


@pytest.mark.parametrize(("fixture", "rule", "count", "severity"), [
    ("dangling_wire", "L002", 3, Severity.WARNING),
    ("two_drivers", "L004", 1, Severity.ERROR),
    ("overlapping_wires", "L006", 1, Severity.WARNING),
    ("overlapping_wires", "L005", 2, Severity.INFO),
    ("wire_through_body", "L007", 1, Severity.WARNING),
    ("wire_through_body", "L005", 1, Severity.INFO),
    ("comb_loop", "L008", 1, Severity.WARNING),
    ("width_mismatch", "L013", 1, Severity.ERROR),
])
def test_rule_fixtures(fixture: str, rule: str, count: int, severity: Severity) -> None:
    hits = [i for i in _lint(GEN / f"{fixture}.circ") if i.rule == rule]
    assert len(hits) == count
    assert {i.severity for i in hits} == {severity}


@pytest.mark.parametrize("fixture", ["d_flipflop", "jk_flipflop", "moore_fsm", "misc_parts", "subcircuit"])
def test_functional_fixtures_are_clean(fixture: str) -> None:
    assert count_problems(_lint(GEN / f"{fixture}.circ")) == 0


def test_two_drivers_lists_both_inverters() -> None:
    (issue,) = [i for i in _lint(GEN / "two_drivers.circ") if i.rule == "L004"]
    assert issue.params["drivers"] == "NOT (200,100), NOT (200,200)"


def test_unlabeled_pins_and_issue_dict() -> None:
    issues = [i for i in _lint(FIXTURES / "mixed_gates.circ") if i.rule == "L014"]
    assert len(issues) == 2
    d = issues[0].to_dict()
    assert d["severity"] == "warning" and d["message"] and d["fix"] and d["msg_key"] == "lint.L014.msg"


def test_negated_inputs_violate_gate_set(tmp_path: Path) -> None:
    xml = ('<project source="2.7.1" version="1.0"><lib desc="#Gates" name="1"/><main name="main"/>'
           '<circuit name="main"><comp lib="1" loc="(200,100)" name="NAND Gate"><a name="inputs" val="2"/>'
           '<a name="negate1" val="true"/></comp></circuit></project>')
    path = tmp_path / "n.circ"
    path.write_text(xml)
    hits = [i for i in _lint(path, only={"nand"}) if i.rule == "L011"]
    assert [i.msg_key for i in hits] == ["lint.L011.msg.negated"]


def test_issue_counts_are_stable_on_draft() -> None:
    counts = Counter(i.rule for i in _lint(FIXTURES / "converter_draft.circ", only={"nand", "nor"}))
    assert counts["L001"] == 1 and counts["L011"] == 10 and counts["L014"] == 8
    assert counts["L009"] == 5 and counts["L002"] == 2
