"""Specification parsing, output mapping and circuit-vs-spec checking."""

from __future__ import annotations

import pytest

from logilens.core.logic_types import Spec
from logilens.logic.cube import cube_from_str, cube_mask
from logilens.spec.check import check_against_spec
from logilens.spec.mapping import map_outputs, parse_map_args
from logilens.spec.parse import SpecError, detect_kind, parse_spec, spec_function


def test_code_table_fixture(conv_spec: Spec) -> None:
    assert conv_spec.kind == "codes"
    assert conv_spec.inputs == ("a", "b", "c", "d", "e")
    assert conv_spec.outputs == ("A", "B", "C", "D")
    assert len(conv_spec.codes) == 12 and len(conv_spec.rows) == 12
    assert conv_spec.rows[0b01001] == "0100"
    assert conv_spec.codes[4].number == 4
    f = spec_function(conv_spec).functions["A"]
    assert f.dc.bit_count() == 20 and f.on.bit_count() == 4  # digits 8..11


def test_code_table_default_names_and_conflict() -> None:
    spec = parse_spec("00 1\n01 0\n1- 1\n")
    assert spec.inputs == ("a", "b") and spec.outputs == ("A",)
    assert spec.rows == {0: "1", 1: "0", 2: "1", 3: "1"}
    with pytest.raises(SpecError):
        parse_spec("00 1\n00 0\n")


def test_csv_truth_table_with_separator_and_dc() -> None:
    text = "a,b,c,|,F,G\n0,0,0,|,1,0\n0,0,1,|,X,1\n1,-,1,|,0,-\n"
    spec = parse_spec(text)
    assert spec.kind == "table"
    assert spec.inputs == ("a", "b", "c") and spec.outputs == ("F", "G")
    assert spec.rows[1] == "-1" and spec.rows[5] == "0-" and spec.rows[7] == "0-"


def test_tsv_grouped_bits_and_case_split() -> None:
    spec = parse_spec("abc\tFG\n000\t10\n111\t01\n")
    assert spec.inputs == ("a", "b", "c") and spec.outputs == ("F", "G")
    assert spec.rows == {0: "10", 7: "01"}


def test_expressions() -> None:
    spec = parse_spec("A = a'b + c(d+e')\nB = !a & ~b | a^b\n")
    assert spec.kind == "expr" and spec.inputs == ("a", "b", "c", "d", "e")
    mf = spec_function(spec)
    a_on = mf.functions["A"].on
    # a'b covers 01xxx; c(d+e') e.g. 00100 (m4)
    assert a_on & cube_mask(cube_from_str("01---")) == cube_mask(cube_from_str("01---"))
    assert a_on >> 0b00100 & 1 and not a_on >> 0b00101 & 1
    # a'b' + (a xor b) is 0 only for a = b = 1
    assert mf.functions["B"].on == ((1 << 32) - 1) & ~cube_mask(cube_from_str("11---"))
    assert detect_kind("F = a") == "expr"


def test_mapping_rules() -> None:
    labels = ["A_N", "A_R", "b", "C", "D_x", "other"]
    mp = map_outputs(["A", "B", "C", "D", "E"], labels)
    assert mp.mapping["A"] == ("A_N", "A_R") and mp.how["A"] == "prefix"
    assert mp.mapping["B"] == ("b",) and mp.how["B"] == "case-insensitive"
    assert mp.mapping["C"] == ("C",) and mp.how["C"] == "exact"
    assert mp.unmapped_spec == ("E",) and mp.unused_labels == ("other",)
    mp2 = map_outputs(["A"], labels, parse_map_args(["A=other"]))
    assert mp2.mapping["A"] == ("other",) and mp2.how["A"] == "override"


def _circuit_table(spec: Spec, flip: int | None = None) -> dict[str, dict[str, str]]:
    mf = spec_function(spec)
    table = {}
    for m in range(32):
        row = {}
        for o in spec.outputs:
            f = mf.functions[o]
            v = "1" if f.on >> m & 1 else "0"
            row[f"{o}_N"] = v
            row[f"{o}_R"] = ("1" if m % 2 else "0") if f.dc >> m & 1 else v
        if m == flip:
            row["B_R"] = "1" if row["B_R"] == "0" else "0"
        table[format(m, "05b")] = row
    return table


def test_check_against_spec(conv_spec: Spec) -> None:
    labels = [f"{o}_{s}" for o in "ABCD" for s in "NR"]
    mp = map_outputs(conv_spec.outputs, labels)
    ok = check_against_spec(_circuit_table(conv_spec), conv_spec, mp, list("abcde"))
    assert ok.passed and ok.rows_checked == 12
    assert ok.rows_ok_by_group == {"*_N": 12, "*_R": 12}
    assert ok.dc_differences  # N and R differ on odd DC rows -> info only
    bad = check_against_spec(_circuit_table(conv_spec, flip=0b00001), conv_spec, mp)
    assert not bad.passed
    assert [(x.inputs, x.label) for x in bad.mismatches] == [("00001", "B_R")]
    assert bad.rows_ok_by_group == {"*_N": 12, "*_R": 11}


def test_check_per_label_orientation_and_x(conv_spec: Spec) -> None:
    mp = map_outputs(conv_spec.outputs, ["A", "B", "C", "D"])
    rows = _circuit_table(conv_spec)
    per_label = {o: {bits: row[f"{o}_N"] for bits, row in rows.items()} for o in "ABCD"}
    per_label["A"]["00000"] = "x"
    res = check_against_spec(per_label, conv_spec, mp)
    assert [(x.inputs, x.actual) for x in res.mismatches] == [("00000", "x")]


def test_map_override_rejects_unknown_names():
    import pytest

    from logilens.spec.mapping import map_outputs

    with pytest.raises(ValueError, match="no output 'Z'"):
        map_outputs(["A", "B"], ["A_N", "B_N"], {"Z": ["A_N"]})
    with pytest.raises(ValueError, match="no output labelled 'nope'"):
        map_outputs(["A", "B"], ["A_N", "B_N"], {"A": ["nope"]})
    assert map_outputs(["A"], ["A_N", "X"], {"A": ["X"]}).mapping == {"A": ("X",)}
