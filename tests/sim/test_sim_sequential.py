"""Sequential simulation: flip-flops and the 4-state Moore FSM fixture."""

from __future__ import annotations

from pathlib import Path

from logilens.parse import flatten, parse_project
from logilens.sim import SequentialSimulator, run_trace

GEN = Path(__file__).resolve().parents[1] / "fixtures" / "gen"


def _sim(name: str) -> SequentialSimulator:
    return SequentialSimulator(flatten(parse_project(str(GEN / f"{name}.circ"))))


def test_moore_fsm_sequence() -> None:
    """S0=10 -> S1=00 -> S2=01 -> S3=11 -> S0 on x=1; x=0 holds; y=0 only in S0."""
    sim = _sim("moore_fsm")
    assert [p.name for p, _ in sim.flat.inputs] == ["x", "rst"]
    sim.set_inputs([0, 1])  # async reset into S0
    assert sim.outputs() == ["1", "0", "0"]
    sim.set_inputs([1, 0])
    seen = [tuple(sim.cycle().outputs) for _ in range(5)]
    assert seen == [("0", "0", "1"), ("0", "1", "1"), ("1", "1", "1"), ("1", "0", "0"), ("0", "0", "1")]
    sim.set_inputs([0, 0])
    assert [tuple(sim.cycle().outputs) for _ in range(3)] == [("0", "0", "1")] * 3


def test_moore_fsm_power_on_state_is_s1() -> None:
    sim = _sim("moore_fsm")
    sim.set_inputs([0, 0])
    assert sim.outputs()[:2] == ["0", "0"]  # both flip-flops start at 0 (Logisim initial value)
    assert len(sim.memory_state()) == 2


def test_d_flipflop_trace_with_clock_component() -> None:
    flat = flatten(parse_project(str(GEN / "d_flipflop.circ")))
    rows = run_trace(flat, ["1", "t", "t", "0", "t"])
    assert [r.outputs for r in rows] == [["0", "1"], ["1", "0"], ["1", "0"], ["1", "0"], ["0", "1"]]


def test_jk_flipflop_toggle_with_pin_clock() -> None:
    sim = _sim("jk_flipflop")  # inputs: j, k, clk, rst
    sim.set_inputs([1, 1, 0, 0])
    qs = []
    for _ in range(3):
        sim.set_inputs([1, 1, 1, 0])
        qs.append(sim.outputs()[0])
        sim.set_inputs([1, 1, 0, 0])
    assert qs == ["1", "0", "1"]
    sim.set_inputs([1, 1, 0, 1])  # asynchronous reset
    assert sim.outputs() == ["0", "1"]
