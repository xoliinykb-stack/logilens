"""Four-valued logic and component models (Logisim 2.7.1 propagate semantics)."""

from __future__ import annotations

import pytest

from logilens.core.geometry import Point
from logilens.core.netlist import Component, Port
from logilens.sim.models import SimContext, adder, controlled, flip_flop, gate, multiplexer
from logilens.sim.values import (
    ONE,
    ZERO,
    E,
    X,
    b_and,
    b_combine,
    b_not,
    b_or,
    b_xor,
    from_int,
    from_str,
    to_int,
    to_str,
)


def test_bit_ops_match_logisim() -> None:
    assert b_and(ZERO, X) == ZERO and b_and(ONE, X) == E and b_and(ONE, ONE) == ONE
    assert b_or(ONE, E) == ONE and b_or(ZERO, X) == E
    assert b_xor(ONE, X) == E and b_xor(ONE, ZERO) == ONE
    assert b_not(X) == E and b_not(ZERO) == ONE
    assert b_combine(X, ONE) == ONE and b_combine(ONE, ZERO) == E and b_combine(E, X) == E


def test_value_conversions() -> None:
    v = from_int(6, 4)
    assert to_str(v) == "0110" and to_int(v) == 6 and from_str("0110") == v
    assert to_str(from_int(-1, 3)) == "111"
    with pytest.raises(ValueError):
        from_str("01z")


def _gate(name: str, inputs: int, **attrs: object) -> Component:
    a = {"inputs": inputs, "width": 1, "out": "01", "xor": "1", **attrs}
    ports = [Port(0, "out", "output", 1, Point(0, 0))] + [Port(i + 1, f"in{i}", "input", 1, Point(-50, i))
                                                          for i in range(inputs)]
    return Component(0, name, "#Gates", Point(0, 0), a, {}, ports, "gate")


def _run(comp: Component, bits: list[str], conn: list[bool], err: bool = False) -> str:
    ins = [(X,)] + [(b,) for b in bits]
    return gate(comp, ins, [True] + conn, {}, SimContext(err))[0][0]


def test_unconnected_inputs_are_skipped() -> None:
    nor = _gate("NOR Gate", 4)
    # input 3 floating (not connected): behaves as a 3-input NOR
    assert _run(nor, [ZERO, ZERO, ZERO, X], [True, True, True, False]) == ONE
    # gateUndefined=error: any unconnected input -> E
    assert _run(nor, [ZERO, ZERO, ZERO, X], [True, True, True, False], err=True) == E
    # nothing connected -> E
    assert _run(nor, [X] * 4, [False] * 4) == E
    # connected but undriven input carries X and is used as X
    assert _run(nor, [ZERO, ZERO, ZERO, X], [True] * 4) == E


def test_negated_inputs_and_out_option() -> None:
    nand = _gate("NAND Gate", 2, negate0=True)
    assert _run(nand, [ZERO, ONE], [True, True]) == ZERO
    and0z = _gate("AND Gate", 2, out="0Z")
    assert _run(and0z, [ONE, ONE], [True, True]) == X


@pytest.mark.parametrize(("mode", "bits", "expected"), [
    ("1", [ONE, ONE, ONE], ZERO), ("odd", [ONE, ONE, ONE], ONE), ("1", [ONE, ZERO, ZERO], ONE)])
def test_xor_modes(mode: str, bits: list[str], expected: str) -> None:
    assert _run(_gate("XOR Gate", 3, xor=mode), bits, [True] * 3) == expected


def test_controlled_buffer() -> None:
    comp = Component(0, "Controlled Buffer", "#Gates", Point(0, 0), {"width": 1}, {}, [], "controlled")
    assert controlled(comp, [(X,), (ONE,), (ONE,)], [True] * 3, {}, SimContext())[0] == (ONE,)
    assert controlled(comp, [(X,), (ONE,), (ZERO,)], [True] * 3, {}, SimContext())[0] == (X,)
    assert controlled(comp, [(X,), (ONE,), (X,)], [True] * 3, {}, SimContext())[0] == (E,)


def test_multiplexer_and_adder() -> None:
    mux = Component(0, "Multiplexer", "#Plexers", Point(0, 0), {"width": 2, "select": 1, "enable": False}, {},
                    [], "plexer")
    out = multiplexer(mux, [from_int(1, 2), from_int(2, 2), (ONE,), (X, X)], [True] * 4, {}, SimContext())
    assert out == {3: from_int(2, 2)}
    add = Component(0, "Adder", "#Arithmetic", Point(0, 0), {"width": 2}, {}, [], "arith")
    res = adder(add, [from_int(3, 2), from_int(2, 2), (X, X), (X,), (X,)], [True] * 5, {}, SimContext())
    assert res == {2: from_int(1, 2), 4: (ONE,)}


def _ff(name: str) -> Component:
    return Component(0, name, "#Memory", Point(0, 0), {"trigger": "rising"}, {}, [], "flipflop")


def test_d_flip_flop_rising_edge_and_async_reset() -> None:
    ff, st = _ff("D Flip-Flop"), {}
    # ports: d, clock, q, nq, reset, preset, enable
    step = lambda d, clk, rst=X: flip_flop(ff, [(d,), (clk,), (X,), (X,), (rst,), (X,), (X,)],
                                           [True] * 7, st, SimContext())[2][0]
    assert step(ONE, ZERO) == ZERO
    assert step(ONE, ONE) == ONE        # rising edge samples d
    assert step(ZERO, ONE) == ONE       # no edge
    assert step(ZERO, ZERO) == ONE
    assert step(ONE, ZERO, rst=ONE) == ZERO  # asynchronous reset


def test_jk_toggle_and_initial_clock_x() -> None:
    ff, st = _ff("J-K Flip-Flop"), {}
    step = lambda j, k, clk: flip_flop(ff, [(j,), (k,), (clk,), (X,), (X,), (X,), (X,), (X,)],
                                       [True] * 8, st, SimContext())[3][0]
    assert step(ONE, ONE, X) == ZERO   # first evaluation sees a floating clock (fresh Logisim state)
    assert step(ONE, ONE, ONE) == ZERO  # X -> 1 is not a rising edge
    assert step(ONE, ONE, ZERO) == ZERO
    assert step(ONE, ONE, ONE) == ONE   # toggle
    assert step(ONE, ONE, ZERO) == ONE
    assert step(ONE, ONE, ONE) == ZERO
