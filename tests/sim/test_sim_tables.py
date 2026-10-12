"""Python truth tables of the reference circuits, checked against the line-code converter code table."""

from __future__ import annotations

from pathlib import Path

from logilens.backends import load_project, truth_table
from logilens.graph import classify

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def read_code_table(path: Path) -> dict[str, str]:
    """Tiny local reader for 'number abcde ABCD' lines (the real spec module belongs to the logic layer)."""
    rows = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and not line.startswith("#"):
            rows[parts[1]] = parts[2]
    return rows


def matches(table: dict, outputs: list[str], spec: dict[str, str]) -> int:
    """Number of specified codes for which the given outputs (in A..D order) match."""
    names = [c["name"] for c in table["outputs"]]
    idx = [names.index(o) for o in outputs]
    by_in = {"".join(r["in"]): r["out"] for r in table["rows"]}
    return sum(1 for code, want in spec.items() if "".join(by_in[code][i] for i in idx) == want)


def test_converter_python_12_of_12_both_groups() -> None:
    spec = read_code_table(FIXTURES / "converter.spec.txt")
    project = load_project(FIXTURES / "converter_nand_nor.circ", backend="python")
    table = truth_table(project)
    assert len(table["rows"]) == 32
    groups = classify(project.main_circuit).groups
    assert groups == [["A_N", "B_N", "C_N", "D_N"], ["A_R", "B_R", "C_R", "D_R"]]
    for group in groups:
        assert matches(table, group, spec) == 12


def test_draft_python_12_of_12_with_tied_duplicate_inputs() -> None:
    """DRAFT has two separate a..e pin sets (one per half); tying equal labels gives the 5-input function."""
    spec = read_code_table(FIXTURES / "converter.spec.txt")
    project = load_project(FIXTURES / "converter_draft.circ", backend="python")
    full = truth_table(project)
    assert len(full["rows"]) == 1024
    table = truth_table(project, tie_duplicate_labels=True)
    assert [c["name"] for c in table["inputs"]] == list("abcde")
    assert table["tied"] == {n: [n, n + "2"] for n in "abcde"}
    assert len(table["rows"]) == 32
    groups = classify(project.main_circuit).groups  # unlabeled outputs: x y z u | v w s t (left to right)
    assert groups == [["x", "y", "z", "u"], ["v", "w", "s", "t"]]
    for group in groups:
        assert matches(table, group, spec) == 12


def test_table_shape() -> None:
    table = truth_table(load_project(FIXTURES / "mixed_gates.circ", backend="python"))
    assert table["backend"] == "python"
    assert [c["name"] for c in table["inputs"]] == ["P", "Q", "R"]
    assert table["rows"][2] == {"in": ["0", "1", "0"], "out": ["1", "1"], "osc": False}
