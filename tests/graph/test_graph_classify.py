"""Graph algorithms and circuit classification."""

from __future__ import annotations

from pathlib import Path

from logilens.graph import classify, fan_in_cone, levelize, tarjan_scc
from logilens.parse import parse_project

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_tarjan_and_levelize() -> None:
    succ = {1: {2}, 2: {3}, 3: {2, 4}, 4: set()}
    sccs = tarjan_scc([1, 2, 3, 4], succ)
    assert sorted(map(tuple, sccs)) == [(1,), (2, 3), (4,)]
    assert sccs.index([4]) < sccs.index([2, 3]) < sccs.index([1])  # reverse topological order
    levels = levelize([1, 2, 3, 4], succ)
    assert levels == {1: 0, 2: 1, 3: 1, 4: 2}
    pred = {2: {1, 3}, 3: {2}, 4: {3}}
    assert fan_in_cone(4, pred) == {1, 2, 3}
    assert fan_in_cone(4, pred, stop={3}) == {3}


def test_converter_output_groups_and_supports() -> None:
    cls = classify(parse_project(str(FIXTURES / "converter_nand_nor.circ")).main_circuit)
    assert cls.groups == [["A_N", "B_N", "C_N", "D_N"], ["A_R", "B_R", "C_R", "D_R"]]
    assert not cls.is_sequential and not cls.comb_loops
    assert all(cls.supports[o] for o in cls.cones)
    assert not cls.cones["A_N"] & cls.cones["A_R"]


def test_comb_loop_detected() -> None:
    cls = classify(parse_project(str(FIXTURES / "gen" / "comb_loop.circ")).main_circuit)
    assert len(cls.comb_loops) == 1 and len(cls.comb_loops[0]) == 2
    assert cls.is_sequential


def test_moore_fsm_state_elements_cut_feedback() -> None:
    circ = parse_project(str(FIXTURES / "gen" / "moore_fsm.circ")).main_circuit
    cls = classify(circ)
    assert len(cls.state_elements) == 2 and not cls.comb_loops and len(cls.clocks) == 1
    # y depends only on the state (Moore): its support is the two flip-flops, not x
    assert all(s.startswith("D Flip-Flop") for s in cls.supports["y"])
    assert "x" in cls.supports["z1"] or any(s.startswith("D Flip-Flop") for s in cls.supports["z1"])
