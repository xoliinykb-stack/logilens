"""Behavioral models of Logisim 2.7.1 components (``propagate`` methods, see cited Java classes).

A model is ``fn(comp, ins, conn, state, ctx) -> {port_index: Value}`` where ``ins[i]`` is the current value
of port i (LSB-first bits, ``x`` when floating), ``conn[i]`` is Logisim's ``isPortConnected`` and ``state`` is
a per-instance dict for stateful parts. Only driven ports appear in the result.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import reduce
from typing import Any

from logilens.core.netlist import Component
from logilens.sim.values import (
    ONE,
    ZERO,
    Bit,
    E,
    Value,
    X,
    b_and,
    b_not,
    b_or,
    b_xor,
    bitwise,
    error,
    from_int,
    fully_defined,
    to_int,
    unknown,
    v_not,
)


@dataclass(frozen=True)
class SimContext:
    """Project options affecting simulation (``file/Options``)."""

    gate_undefined_error: bool = False


Model = Callable[[Component, Sequence[Value], Sequence[bool], dict[str, Any], SimContext], dict[int, Value]]


def _w(comp: Component, key: str = "width", default: int = 1) -> int:
    return int(comp.attrs.get(key) or default)


# ------------------------------------------------------------------ gates (std/gates)
def pull_output(v: Value, out_type: str) -> Value:
    """``AbstractGate.pullOutput``: '0Z' turns 1 into floating, 'Z1' turns 0 into floating."""
    if out_type == "0Z":
        return tuple(X if b == ONE else b for b in v)
    if out_type == "Z1":
        return tuple(X if b == ZERO else b for b in v)
    return v


def _exactly_one(vals: list[Value], width: int) -> Value:
    out: list[Bit] = []
    for i in range(width):
        count = 0
        for v in vals:
            b = v[i] if i < len(v) else E
            if b == ONE:
                count += 1
            elif b != ZERO:
                count = -1
                break
        out.append(E if count < 0 else (ONE if count == 1 else ZERO))
    return tuple(out)


def _reduce(op: Callable[[Bit, Bit], Bit]) -> Callable[[list[Value], int], Value]:
    return lambda vals, width: reduce(lambda a, b: bitwise(op, a, b), vals)


def _gate_function(comp: Component) -> tuple[Callable[[list[Value], int], Value], bool]:
    name = comp.name
    xor_mode = comp.attrs.get("xor", "1")
    if name in ("AND Gate", "NAND Gate"):
        fn = _reduce(b_and)
    elif name in ("OR Gate", "NOR Gate"):
        fn = _reduce(b_or)
    elif name in ("XOR Gate", "XNOR Gate") and xor_mode != "odd":
        fn = _exactly_one
    else:  # parity gates, XOR/XNOR in 'odd' mode
        fn = _reduce(b_xor)
    negate = name in ("NAND Gate", "NOR Gate", "XNOR Gate", "Even Parity")
    return fn, negate


def gate(comp: Component, ins: Sequence[Value], conn: Sequence[bool], st: dict[str, Any], ctx: SimContext) -> dict[int, Value]:
    """``AbstractGate.propagate``: unconnected inputs are skipped (or force E with gateUndefined=error)."""
    width = _w(comp)
    vals: list[Value] = []
    err = False
    for i in range(int(comp.attrs["inputs"])):
        if conn[i + 1]:
            v = tuple(ins[i + 1])
            vals.append(v_not(v) if comp.attrs.get(f"negate{i}") else v)
        elif ctx.gate_undefined_error:
            err = True
    if not vals or err:
        return {0: error(width)}
    fn, negate = _gate_function(comp)
    out = fn(vals, width)
    if negate:
        out = v_not(out)
    return {0: pull_output(out, comp.attrs.get("out", "01"))}


def _repair(comp: Component, v: Value, ctx: SimContext) -> Value:
    """``Buffer.repair``."""
    if ctx.gate_undefined_error:
        width = _w(comp)
        v = tuple((v[i] if i < len(v) and v[i] in (ZERO, ONE) else E) for i in range(width))
    return pull_output(v, comp.attrs.get("out", "01"))


def not_gate(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    return {0: _repair(comp, v_not(ins[1]), ctx)}


def buffer(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    return {0: _repair(comp, tuple(ins[1]), ctx)}


def controlled(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    """``ControlledBuffer.propagate``: control 1 passes, X/E -> E, 0 -> floating."""
    width = _w(comp)
    control = ins[2][0] if ins[2] else X
    if control == ONE:
        v = tuple(ins[1])
        return {0: v_not(v) if comp.name == "Controlled Inverter" else v}
    if control in (E, X):
        return {0: error(width)}
    return {0: unknown(width)}


# ------------------------------------------------------------------ wiring sources
def pin(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    """Input pins drive their poked value (initially X when tristate, else 0); output pins drive nothing."""
    if comp.attrs.get("output"):
        return {}
    width = _w(comp)
    default = unknown(width) if comp.attrs.get("tristate", True) else from_int(0, width)
    return {0: st.get("value", default)}


def constant(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    width = _w(comp)
    if comp.name == "Power":
        return {0: from_int(-1, width)}
    if comp.name == "Ground":
        return {0: from_int(0, width)}
    return {0: from_int(int(comp.attrs.get("value", 1)), width)}


def clock(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    return {0: (st.get("value", ZERO),)}


def bit_extender(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    """``BitExtender.propagate`` (Value.extendWidth)."""
    win, wout = _w(comp, "in_width", 8), _w(comp, "out_width", 16)
    v = tuple(ins[1])[:win] or unknown(win)
    kind = comp.attrs.get("type", "zero")
    ext = {"one": ONE, "zero": ZERO}.get(kind)
    if kind == "sign":
        ext = v[-1] if v else E
    elif kind == "input":
        ext = ins[2][0] if len(ins[2]) == 1 else E
    return {0: (v + (ext,) * max(0, wout - len(v)))[:wout]}


# ------------------------------------------------------------------ plexers (std/plexers)
def _enable(comp: Component, ins: Sequence[Value], conn: Sequence[bool], idx: int) -> Bit:
    return ins[idx][0] if comp.attrs.get("enable") and ins[idx] else ONE


def multiplexer(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    width, sbits = _w(comp), _w(comp, "select")
    n = 1 << sbits
    en_idx = n + 1
    out_idx = n + (2 if comp.attrs.get("enable") else 1)
    en = _enable(comp, ins, conn, en_idx)
    if en == ZERO:
        out = from_int(0, width) if comp.attrs.get("disabled") == "0" else unknown(width)
    elif en == E and conn[en_idx]:
        out = error(width)
    else:
        sel = ins[n]
        if fully_defined(sel):
            out = tuple(ins[to_int(sel)])
        elif E in sel:
            out = error(width)
        else:
            out = unknown(width)
    return {out_idx: out}


def demultiplexer(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    width, sbits = _w(comp), _w(comp, "select")
    n = 1 << sbits
    en_idx = n + 1
    in_idx = n + (2 if comp.attrs.get("enable") else 1)
    others = from_int(0, width) if not comp.attrs.get("tristate") else unknown(width)
    en = _enable(comp, ins, conn, en_idx)
    sel_idx, out = -1, others
    if en == ZERO:
        others = from_int(0, width) if comp.attrs.get("disabled") == "0" else unknown(width)
    elif en == E and conn[en_idx]:
        others = error(width)
    else:
        sel = ins[n]
        if fully_defined(sel):
            sel_idx, out = to_int(sel), tuple(ins[in_idx])
        elif E in sel:
            others = error(width)
        else:
            others = unknown(width)
    return {i: (out if i == sel_idx else others) for i in range(n)}


def decoder(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    sbits = _w(comp, "select")
    n = 1 << sbits
    others: Value = (X,) if comp.attrs.get("tristate") else (ZERO,)
    en = _enable(comp, ins, conn, n + 1)
    sel_idx = -1
    if en == ZERO:
        others = (ZERO,) if comp.attrs.get("disabled") == "0" else (X,)
    elif en == E and conn[n + 1]:
        others = (E,)
    else:
        sel = ins[n]
        if fully_defined(sel):
            sel_idx = to_int(sel)
        elif E in sel:
            others = (E,)
        else:
            others = (X,)
    return {i: ((ONE,) if i == sel_idx else others) for i in range(n)}


# ------------------------------------------------------------------ arithmetic (std/arith)
def _sum(width: int, a: Value, b: Value, cin: Bit) -> tuple[Value, Bit]:
    """``Adder.computeSum``."""
    if cin == X:
        cin = ZERO
    if fully_defined(a) and fully_defined(b) and cin in (ZERO, ONE):
        total = to_int(a) + to_int(b) + (1 if cin == ONE else 0)
        return from_int(total, width), ONE if (total >> width) & 1 else ZERO
    bits: list[Bit] = []
    carry = cin
    for i in range(width):
        if carry in (E, X):
            bits.append(carry)
            continue
        ab, bb = (a[i] if i < len(a) else E), (b[i] if i < len(b) else E)
        if E in (ab, bb):
            bits.append(E)
            carry = E
        elif X in (ab, bb):
            bits.append(X)
            carry = X
        else:
            s = (ab == ONE) + (bb == ONE) + (carry == ONE)
            bits.append(ONE if s & 1 else ZERO)
            carry = ONE if s >= 2 else ZERO
    return tuple(bits), carry


def adder(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    width = _w(comp, default=8)
    out, cout = _sum(width, ins[0], ins[1], ins[3][0] if ins[3] else X)
    return {2: out, 4: (cout,)}


def subtractor(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    width = _w(comp, default=8)
    bin_ = ins[3][0] if ins[3] else X
    if bin_ == X:
        bin_ = ZERO
    out, cout = _sum(width, ins[0], v_not(ins[1]), b_not(bin_))
    return {2: out, 4: (b_not(cout),)}


def comparator(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    a, b = tuple(ins[0]), tuple(ins[1])
    gt, eq, lt = ZERO, ONE, ZERO
    n = max(len(a), len(b))
    for pos in range(n - 1, -1, -1):
        ab = a[pos] if pos < len(a) else E
        bb = b[pos] if pos < len(b) else E
        if pos == len(a) - 1 and ab != bb and comp.attrs.get("mode") != "unsigned":
            ab, bb = bb, ab
        if E in (ab, bb):
            gt = eq = lt = E
            break
        if X in (ab, bb):
            gt = eq = lt = X
            break
        if ab != bb:
            eq = ZERO
            if ab == ONE:
                gt = ONE
            else:
                lt = ONE
            break
    return {2: (gt,), 3: (eq,), 4: (lt,)}


def negator(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    width = _w(comp, default=8)
    v = tuple(ins[0])
    if fully_defined(v) and v:
        return {1: from_int(-to_int(v), width)}
    bits = list(v)
    fill, pos = ZERO, 0
    while pos < len(bits):
        if bits[pos] == ZERO:
            bits[pos] = fill
        elif bits[pos] == ONE:
            if fill != ZERO:
                bits[pos] = fill
            pos += 1
            break
        elif bits[pos] == E:
            fill = E
        elif fill == ZERO:
            fill = bits[pos]
        else:
            bits[pos] = fill
        pos += 1
    while pos < len(bits):
        bits[pos] = {ONE: ZERO, ZERO: ONE}.get(bits[pos], bits[pos])
        pos += 1
    return {1: tuple(bits)}


# ------------------------------------------------------------------ memory (std/memory)
def triggered(st: dict[str, Any], new_clock: Bit, trigger: str) -> bool:
    """``ClockState.updateClock``: remembers the last clock value; rising edge = exactly 0 -> 1."""
    old = st.get("last_clock", ZERO)
    st["last_clock"] = new_clock
    if trigger == "falling":
        return old == ONE and new_clock == ZERO
    if trigger == "high":
        return new_clock == ONE
    if trigger == "low":
        return new_clock == ZERO
    return old == ZERO and new_clock == ONE


def _ff_next(name: str, data: list[Bit], cur: Bit) -> Bit:
    if name == "D Flip-Flop":
        return data[0]
    if name == "T Flip-Flop":
        cur = ZERO if cur == X else cur
        return b_not(cur) if data[0] == ONE else cur
    j, k = data
    table = {(ZERO, ZERO): cur, (ZERO, ONE): ZERO, (ONE, ZERO): ONE}
    if (j, k) in table:
        return table[(j, k)]
    if (j, k) == (ONE, ONE):
        return b_not(cur) if name == "J-K Flip-Flop" else E
    return X


def flip_flop(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    """``AbstractFlipFlop.propagate``: async reset > preset > clocked update (enable floating = enabled)."""
    n = 1 if comp.name in ("D Flip-Flop", "T Flip-Flop") else 2
    bit = lambda i: ins[i][0] if ins[i] else X
    fired = triggered(st, bit(n), comp.attrs.get("trigger", "rising"))
    cur = st.get("q", ZERO)
    if bit(n + 3) == ONE:
        cur = ZERO
    elif bit(n + 4) == ONE:
        cur = ONE
    elif fired and bit(n + 5) != ZERO:
        new = _ff_next(comp.name, [bit(i) for i in range(n)], cur)
        if new in (ZERO, ONE):
            cur = new
    st["q"] = cur
    return {n + 1: (cur,), n + 2: (b_not(cur),)}


def register(comp, ins, conn, st, ctx):  # type: ignore[no-untyped-def]
    """``Register.propagate``: clear (async) > clocked load when enable != 0 and d fully defined."""
    width = _w(comp, default=8)
    fired = triggered(st, ins[2][0] if ins[2] else X, comp.attrs.get("trigger", "rising"))
    if (ins[3][0] if ins[3] else X) == ONE:
        st["value"] = 0
    elif fired and (ins[4][0] if ins[4] else X) != ZERO and fully_defined(ins[1]) and ins[1]:
        st["value"] = to_int(ins[1])
    return {0: from_int(st.get("value", 0), width)}


MODELS: dict[str, Model] = {
    **{name: gate for name in ("AND Gate", "OR Gate", "NAND Gate", "NOR Gate", "XOR Gate", "XNOR Gate",
                               "Odd Parity", "Even Parity")},
    "NOT Gate": not_gate, "Buffer": buffer, "Controlled Buffer": controlled, "Controlled Inverter": controlled,
    "Pin": pin, "Constant": constant, "Power": constant, "Ground": constant, "Clock": clock,
    "Bit Extender": bit_extender,
    "Multiplexer": multiplexer, "Demultiplexer": demultiplexer, "Decoder": decoder,
    "Adder": adder, "Subtractor": subtractor, "Comparator": comparator, "Negator": negator,
    "D Flip-Flop": flip_flop, "T Flip-Flop": flip_flop, "J-K Flip-Flop": flip_flop, "S-R Flip-Flop": flip_flop,
    "Register": register,
}

PASSIVE = frozenset({"Probe", "Tunnel", "Splitter", "Pull Resistor", "Text", "LED", "7-Segment Display",
                     "Hex Digit Display", "DotMatrix"})
"""Components with no driven outputs (pure wiring or display only)."""


def model_for(comp: Component) -> Model | None:
    """The model of a component, ``None`` for passive parts."""
    if comp.lib is None:
        return None
    return MODELS.get(comp.name)


def is_simulated(comp: Component) -> bool:
    """True when the Python simulator handles this component exactly (or it is passive)."""
    return comp.kind == "subcircuit" or comp.name in MODELS or comp.name in PASSIVE
