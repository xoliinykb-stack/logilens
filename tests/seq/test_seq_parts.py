"""Flip-flop fixtures, excitation tables, Mealy detection, T counter, register, input-sequence parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from logilens.backends import load_project
from logilens.seq import analyze_sequential, excitation_functions, parse_sequence
from logilens.seq.excitation import EXCITATION, excitation_table_text, excite
from logilens.seq.validate import covering_walk

GEN = Path(__file__).resolve().parents[1] / "fixtures" / "gen"


def _load(path: Path):  # type: ignore[no-untyped-def]
    return load_project(path, backend="python")


# ------------------------------------------------------------------ excitation tables
def test_excitation_tables() -> None:
    assert EXCITATION["D"] == {("0", "0"): ("0",), ("0", "1"): ("1",), ("1", "0"): ("0",), ("1", "1"): ("1",)}
    assert EXCITATION["T"] == {("0", "0"): ("0",), ("0", "1"): ("1",), ("1", "0"): ("1",), ("1", "1"): ("0",)}
    assert excite("JK", "0", "0") == {"J": "0", "K": "X"}
    assert excite("JK", "0", "1") == {"J": "1", "K": "X"}
    assert excite("JK", "1", "0") == {"J": "X", "K": "1"}
    assert excite("JK", "1", "1") == {"J": "X", "K": "0"}
    assert excite("SR", "0", "0") == {"S": "0", "R": "X"}
    assert excite("SR", "0", "1") == {"S": "1", "R": "0"}
    assert excite("SR", "1", "0") == {"S": "0", "R": "1"}
    assert excite("SR", "1", "1") == {"S": "X", "R": "0"}
    assert "J K" in excitation_table_text("JK")


def test_moore_excitation_functions() -> None:
    res = analyze_sequential(_load(GEN / "moore_fsm.circ"), estimate_encodings=False)
    exc = res.excitation
    mf = exc.functions  # variables z1 z2 x, minterm = z1 z2 x
    assert mf.inputs == ("z1", "z2", "x") and mf.outputs == ("D_z1", "D_z2")
    # D1 = x'z1 + x z2 -> minterms 100, 110, 011, 111 ; D2 = x'z2 + x z1' -> 010, 110, 001, 011
    assert mf.functions["D_z1"].on == sum(1 << m for m in (0b100, 0b110, 0b011, 0b111))
    assert mf.functions["D_z2"].on == sum(1 << m for m in (0b010, 0b110, 0b001, 0b011))
    assert exc.mismatches == [] and exc.implemented == mf
    jk = excitation_functions(res.fsm, "JK").functions
    assert jk.outputs == ("J_z1", "K_z1", "J_z2", "K_z2")
    # J_z1: z1=0 rows: 000->0, 001->0 (S1->S2 keeps z1=0), 010->0, 011->1 ; z1=1 rows are DC
    j1 = jk.functions["J_z1"]
    assert j1.on == 1 << 0b011 and j1.dc == sum(1 << m for m in range(4, 8))
    from logilens.kmap.groups import views_for_cover

    assert len(views_for_cover(jk)) == 4  # ready for K-maps


def test_jk_flipflop() -> None:
    res = analyze_sequential(_load(GEN / "jk_flipflop.circ"), input_sequence="10 11 11 01 00")
    fsm = res.fsm
    assert fsm.ff_kinds == ["JK"] and fsm.inputs == ["j", "k"] and fsm.clock_inputs == ["clk"]
    assert fsm.async_inputs == ["rst"]
    assert {x: fsm.delta[("0", x)] for x in fsm.input_codes} == {"00": "0", "01": "0", "10": "1", "11": "1"}
    assert {x: fsm.delta[("1", x)] for x in fsm.input_codes} == {"00": "1", "01": "0", "10": "1", "11": "0"}
    assert fsm.kind == "moore" and res.excitation.mismatches == []
    assert res.timing.trace == "0 1 0 1 0 0"
    j = res.excitation.functions.functions["J_q"]  # J = j where q=0, DC where q=1 (variables q j k)
    assert j.on == (1 << 0b010) | (1 << 0b011) and j.dc == 0b11110000


def test_d_flipflop() -> None:
    res = analyze_sequential(_load(GEN / "d_flipflop.circ"), input_sequence="1101")
    fsm = res.fsm
    assert fsm.ff_kinds == ["D"] and fsm.state_vars == ["q"] and fsm.clock_sources == ["clk"]
    assert all(fsm.delta[(s, x)] == x for s in fsm.states for x in fsm.input_codes)
    assert res.timing.trace == "0 1 1 0 1"
    assert res.analysis.self_loops == [("0", "0"), ("1", "1")]


def test_mealy_detection(mealy_circ: Path) -> None:
    res = analyze_sequential(_load(mealy_circ), input_sequence="0110111")
    fsm = res.fsm
    assert fsm.kind == "mealy" and fsm.state_vars == ["q"]
    assert fsm.lam[("1", "1")] == ("1",) and fsm.lam[("1", "0")] == ("0",) and fsm.lam[("0", "1")] == ("0",)
    assert '"1" -> "1" [label="1/1"];' in res.dot and '"1" -> "0" [label="0/0"];' in res.dot
    assert res.timing.output_trace == list("00100111")  # y = x AND q, last column holds x=1
    row = next(r for r in res.analysis.rows if r.state == "1")
    assert row.outputs == ["0", "1"]


def test_t_counter_autonomous(t_counter_circ: Path) -> None:
    res = analyze_sequential(_load(t_counter_circ), input_sequence=5)
    fsm = res.fsm
    assert fsm.state_vars == ["a", "b"] and fsm.ff_kinds == ["T", "T"] and fsm.inputs == []
    assert [fsm.delta[(s, "")] for s in ("00", "01", "10", "11")] == ["01", "10", "11", "00"]
    assert res.timing.trace == "00 01 10 11 00 01"
    t = res.excitation.functions
    assert t.outputs == ("T_a", "T_b")
    assert t.functions["T_b"].on == 0b1111 and t.functions["T_a"].on == (1 << 0b01) | (1 << 0b11)
    assert res.analysis.strongly_connected and res.analysis.self_loops == []


def test_register(register_circ: Path) -> None:
    res = analyze_sequential(_load(register_circ), input_sequence="00 11 10 01", estimate_encodings=False)
    fsm = res.fsm
    assert fsm.ff_kinds == ["REG", "REG"] and fsm.state_vars == ["r1", "r0"] and fsm.inputs == ["d1", "d0"]
    assert all(fsm.delta[(s, x)] == x for s in fsm.states for x in fsm.input_codes)
    assert res.timing.trace == "00 00 11 10 01"


def test_parse_sequence() -> None:
    fsm = analyze_sequential(_load(GEN / "jk_flipflop.circ"), estimate_encodings=False).fsm
    assert parse_sequence("0110 1011", fsm) == ["01", "10", "10", "11"]
    assert parse_sequence("01,10", fsm) == ["01", "10"]
    assert parse_sequence([{"j": 1}, {"k": 1}, {"j": 0}], fsm) == ["10", "11", "01"]
    with pytest.raises(ValueError):
        parse_sequence("011", fsm)
    with pytest.raises(ValueError):
        parse_sequence([{"zz": 1}], fsm)


def test_covering_walk_uses_every_transition() -> None:
    fsm = analyze_sequential(_load(GEN / "moore_fsm.circ"), estimate_encodings=False).fsm
    walk = covering_walk(fsm)
    used, s = set(), fsm.initial
    for x in walk:
        used.add((s, x))
        s = fsm.delta[(s, x)]
    assert used == set(fsm.delta)
