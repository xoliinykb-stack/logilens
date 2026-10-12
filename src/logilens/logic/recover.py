"""Recover the implemented two-level cover of an output group from the netlist.

Normalisation of literals: an input pin is a positive literal; a NOT gate, a NAND/NOR with one connected input,
or a NAND/NOR whose connected inputs all sit on the same net is an inverter of a literal (``x'``); AND/OR gates
with all inputs on one net are buffers. Negated input bubbles flip the polarity of a literal.

Recognised output structures (``l`` = literal, ``G(...)`` = first-level gate of literals only):

* ``NAND(G_nand(l..) | l, ...)``  -> SOP (NAND-NAND); a literal input ``l`` is the one-literal term ``l'``;
* ``OR(G_and(l..) | l, ...)``     -> SOP (AND-OR);
* ``NOR(G_nor(l..) | l, ...)``    -> POS (NOR-NOR); a literal input ``l`` is the one-literal clause ``l'``;
* ``AND(G_or(l..) | l, ...)``     -> POS (OR-AND);
* ``INV(G_nand(l..))`` = product (SOP), ``INV(G_nor(l..))`` = clause (POS), ``INV(G_or)`` / ``INV(G_and)`` dual;
* a literal (wire or inverter chain).

Shared first-level gates become multi-output cubes automatically (the cost model counts a cube once).
Anything else (XOR, multi-level nesting, subcircuits, constants, multi-bit signals) is ``BEYOND_TWO_LEVEL``.
The recovered cover is always verified against the simulated truth table.

The structural cost is counted on the netlist itself, see :func:`structural_cost`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from logilens.core.logic_types import BoolFunction, Cover, Cube, Form
from logilens.core.netlist import CircuitNetlist, Component
from logilens.graph.topo import ComponentGraph
from logilens.logic.cube import cube_mask, full_mask

GATE_TYPES = {"AND Gate": "AND", "OR Gate": "OR", "NAND Gate": "NAND", "NOR Gate": "NOR"}
COUNTED_KINDS = frozenset({"gate", "not", "buffer", "controlled"})


class RecoverStatus(str, Enum):
    """Outcome of recovering one output group."""

    RECOVERED = "recovered"
    BEYOND_TWO_LEVEL = "beyond_two_level"
    MISMATCH = "mismatch"  # a two-level structure was found but it disagrees with the simulation


@dataclass(frozen=True)
class Literal:
    """Input variable ``var`` (index into the group variables) in ``positive`` or complemented polarity."""

    var: int
    positive: bool

    def __invert__(self) -> Literal:
        return Literal(self.var, not self.positive)


@dataclass(frozen=True)
class OutputShape:
    """Two-level shape of one output: ``kind`` 'literal' | 'sop' | 'pos'; ``terms`` products or clauses."""

    output: str
    kind: str
    terms: tuple[frozenset[Literal], ...]
    technology: str  # 'nand' | 'nor' | 'and-or' | 'or-and' | 'wire'


@dataclass
class RecoveredCover:
    """Recovered implementation of one output group."""

    status: RecoverStatus
    form: Form | None = None
    cover: Cover | None = None
    technology: str | None = None
    reasons: list[str] = field(default_factory=list)
    verified: bool = False
    unverified_rows: int = 0

    @property
    def ok(self) -> bool:
        return self.status is RecoverStatus.RECOVERED


@dataclass(frozen=True)
class StructuralCost:
    """Cost of the drawn netlist of a group.

    ``gates``/``inputs`` count every gate once with its *connected* inputs (a NOT gate has one input, a NAND with
    tied inputs has as many as are wired). ``nandnor_gates``/``nandnor_inputs`` re-count each NOT gate as a
    NAND/NOR with two tied inputs (1 gate / 2 inputs), which makes the figure comparable with the NAND/NOR
    cost of a cover.
    """

    gates: int
    inputs: int
    not_gates: int
    unconnected_inputs: int
    negated_inputs: int
    by_type: dict[str, tuple[int, int]]

    @property
    def nandnor_gates(self) -> int:
        return self.gates

    @property
    def nandnor_inputs(self) -> int:
        return self.inputs + self.not_gates

    def short(self) -> str:
        return f"{self.gates}/{self.inputs}"

    def nandnor_short(self) -> str:
        return f"{self.nandnor_gates}/{self.nandnor_inputs}"


class _Beyond(Exception):
    """Internal: the structure is not two-level (message = reason)."""


@dataclass
class _Ctx:
    circ: CircuitNetlist
    graph: ComponentGraph
    var_of_pin: Mapping[int, int]  # input pin component id -> variable index


# ------------------------------------------------------------------ structural cost


def connected_inputs(circ: CircuitNetlist, comp: Component) -> int:
    """Number of connected input ports of a gate-like component."""
    return sum(1 for p in comp.ports if p.direction == "input" and (comp.id, p.index) in circ.connected)


def _negated_count(comp: Component) -> int:
    return sum(1 for k, v in comp.attrs.items() if k.startswith("negate") and v is True)


def structural_cost(circ: CircuitNetlist, comp_ids: Iterable[int]) -> StructuralCost:
    """Gates / connected inputs of the given components (each counted once; non-gates ignored)."""
    by_type: dict[str, list[int]] = {}
    gates = inputs = nots = loose = negated = 0
    for cid in sorted(set(comp_ids)):
        comp = circ.components[cid]
        if comp.kind not in COUNTED_KINDS:
            continue
        n_in = connected_inputs(circ, comp)
        declared = sum(1 for p in comp.ports if p.direction == "input")
        if comp.kind == "gate":
            declared = int(comp.attrs.get("inputs", declared))
        gates += 1
        inputs += n_in
        loose += max(0, declared - n_in) if comp.kind == "gate" else 0
        nots += comp.kind == "not"
        negated += _negated_count(comp)
        entry = by_type.setdefault(comp.short, [0, 0])
        entry[0] += 1
        entry[1] += n_in
    return StructuralCost(gates, inputs, nots, loose, negated, {k: (v[0], v[1]) for k, v in sorted(by_type.items())})


# ------------------------------------------------------------------ signal tracing


def _driver(ctx: _Ctx, cid: int, port_index: int) -> int:
    """Component driving input port ``(cid, port_index)``; raises when ambiguous / missing / multi-bit."""
    threads = ctx.circ.port_threads((cid, port_index)) if (cid, port_index) in ctx.circ.port_net else []
    if len(threads) != 1:
        raise _Beyond(f"{ctx.circ.components[cid].describe()}: multi-bit or unconnected signal")
    drivers = {d for d, _ in ctx.graph.thread_drivers.get(threads[0], [])}
    if len(drivers) != 1:
        what = "no driver" if not drivers else "several drivers"
        raise _Beyond(f"{ctx.circ.components[cid].describe()}: input with {what}")
    return next(iter(drivers))


def _gate_inputs(ctx: _Ctx, comp: Component) -> list[tuple[int, bool]]:
    """``(driver id, negated)`` for each connected input of a gate (Logisim ignores loose inputs)."""
    out = []
    for i, port in enumerate(p for p in comp.ports if p.direction == "input"):
        if (comp.id, port.index) not in ctx.circ.connected:
            continue
        out.append((_driver(ctx, comp.id, port.index), bool(comp.attrs.get(f"negate{i}", False))))
    if not out:
        raise _Beyond(f"{comp.describe()}: no connected inputs")
    return out


def _check_width(comp: Component) -> None:
    width = comp.attrs.get("width", 1)
    if isinstance(width, int) and width > 1:
        raise _Beyond(f"{comp.describe()}: {width}-bit gate")


def _inverter_source(ctx: _Ctx, comp: Component) -> tuple[int, bool] | None:
    """For an inverter/buffer-like component, ``(source driver, inverts)``; None otherwise."""
    if comp.kind == "not":
        return _gate_inputs(ctx, comp)[0][0], True
    if comp.kind == "buffer":
        return _gate_inputs(ctx, comp)[0][0], False
    gate = GATE_TYPES.get(comp.name)
    if comp.kind != "gate" or gate is None:
        return None
    ins = _gate_inputs(ctx, comp)
    if len(set(ins)) != 1:
        return None
    src, neg = ins[0]
    return src, (gate in ("NAND", "NOR")) != neg


def as_literal(ctx: _Ctx, cid: int, depth: int = 0) -> Literal | None:
    """The literal a component's output carries, or None when it is not a (possibly inverted) input."""
    if depth > 16:
        raise _Beyond("inverter chain too deep")
    if cid in ctx.var_of_pin:
        return Literal(ctx.var_of_pin[cid], True)
    comp = ctx.circ.components[cid]
    if comp.kind == "pin":
        raise _Beyond(f"{comp.describe()}: input outside the group variables")
    if comp.kind not in ("not", "buffer", "gate"):
        return None
    _check_width(comp)
    source = _inverter_source(ctx, comp)
    if source is None:
        return None
    lit = as_literal(ctx, source[0], depth + 1)
    if lit is None:
        return None
    return ~lit if source[1] else lit


def _input_literal(ctx: _Ctx, driver: int, negated: bool) -> Literal | None:
    lit = as_literal(ctx, driver)
    if lit is None:
        return None
    return ~lit if negated else lit


def first_level(ctx: _Ctx, cid: int) -> tuple[str, frozenset[Literal]] | None:
    """``(gate type, literals)`` when the component is an AND/OR/NAND/NOR gate fed by literals only."""
    comp = ctx.circ.components[cid]
    gate = GATE_TYPES.get(comp.name)
    if comp.kind != "gate" or gate is None:
        return None
    _check_width(comp)
    lits = []
    for driver, negated in _gate_inputs(ctx, comp):
        lit = _input_literal(ctx, driver, negated)
        if lit is None:
            return None
        lits.append(lit)
    return gate, frozenset(lits)


# second-level gate -> (form, technology, first-level gate type it accepts, literal input enters complemented)
_SECOND_LEVEL = {
    "NAND": ("sop", "nand", "NAND", True),
    "OR": ("sop", "and-or", "AND", False),
    "NOR": ("pos", "nor", "NOR", True),
    "AND": ("pos", "or-and", "OR", False),
}
# inverter of a first-level gate -> (kind, technology, literals complemented)
_INVERTED_TERM = {
    "NAND": ("sop", "nand", False),
    "OR": ("sop", "nor", True),
    "NOR": ("pos", "nor", False),
    "AND": ("pos", "nand", True),
}


def _shape_inverted(ctx: _Ctx, output: str, source: int) -> OutputShape:
    term = first_level(ctx, source)
    if term is None:
        raise _Beyond(f"{output}: inverter of a multi-level signal")
    gate, lits = term
    kind, tech, complement = _INVERTED_TERM[gate]
    lits = frozenset(~lit for lit in lits) if complement else lits
    return OutputShape(output, kind, (lits,), tech)


def output_shape(ctx: _Ctx, output: str, pin_id: int) -> OutputShape:
    """Two-level shape of the output pin (raises :class:`_Beyond`)."""
    pin = ctx.circ.components[pin_id]
    root = _driver(ctx, pin_id, pin.ports[0].index)
    lit = as_literal(ctx, root)
    if lit is not None:
        return OutputShape(output, "literal", (frozenset({lit}),), "wire")
    comp = ctx.circ.components[root]
    source = _inverter_source(ctx, comp) if comp.kind in ("not", "buffer", "gate") else None
    if source is not None and source[1]:
        return _shape_inverted(ctx, output, source[0])
    gate = GATE_TYPES.get(comp.name)
    if comp.kind != "gate" or gate is None:
        raise _Beyond(f"{output}: driven by {comp.describe()} (not a two-level gate)")
    _check_width(comp)
    kind, tech, wanted, complement = _SECOND_LEVEL[gate]
    terms: list[frozenset[Literal]] = []
    for driver, negated in _gate_inputs(ctx, comp):
        lit = _input_literal(ctx, driver, negated)
        if lit is not None:
            terms.append(frozenset({~lit if complement else lit}))
            continue
        if negated:
            raise _Beyond(f"{output}: negated input bubble on a non-literal signal of {comp.describe()}")
        term = first_level(ctx, driver)
        if term is None or term[0] != wanted:
            what = ctx.circ.components[driver].describe()
            raise _Beyond(f"{output}: {what} feeding {comp.describe()} is not a first-level {wanted} of input "
                          "literals (multi-level structure)")
        terms.append(term[1])
    return OutputShape(output, kind, tuple(terms), tech)


# ------------------------------------------------------------------ cover building + verification


def _cube(n: int, literals: frozenset[Literal], form: Form) -> Cube:
    """SOP: product -> ON cube. POS: clause -> OFF cube (positive literal x -> char '0')."""
    care = value = 0
    for lit in literals:
        bit = 1 << (n - 1 - lit.var)
        if care & bit and bool(value & bit) != (lit.positive == (form is Form.SOP)):
            raise _Beyond("term contains a variable in both polarities")
        care |= bit
        if lit.positive == (form is Form.SOP):
            value |= bit
    return Cube(n, care, value)


def _group_form(shapes: list[OutputShape]) -> tuple[Form, str]:
    kinds = {s.kind for s in shapes if s.kind != "literal"}
    techs = sorted({s.technology for s in shapes if s.technology != "wire"})
    if len(kinds) > 1:
        raise _Beyond("outputs of the group mix SOP and POS structures")
    form = Form.POS if kinds == {"pos"} else Form.SOP
    tech = techs[0] if len(techs) == 1 else ("mixed" if techs else ("nand" if form is Form.SOP else "nor"))
    return form, tech


def cover_function(cover: Cover, output: str) -> int:
    """ON-set mask the cover realises for ``output``."""
    n = len(cover.inputs)
    union = 0
    for c in cover.terms.get(output, ()):
        union |= cube_mask(c)
    return union if cover.form is Form.SOP else full_mask(n) & ~union


def verify(cover: Cover, functions: Mapping[str, BoolFunction]) -> tuple[bool, int]:
    """Compare on all rows where the circuit value is defined; returns (ok, undefined row count)."""
    undefined = 0
    for name, f in functions.items():
        on = cover_function(cover, name)
        if (on & f.off) or (f.on & ~on):
            return False, undefined
        undefined = max(undefined, f.dc.bit_count())
    return True, undefined


def recover_group(
    circ: CircuitNetlist,
    graph: ComponentGraph,
    outputs: list[str],
    variables: tuple[str, ...],
    var_of_pin: Mapping[int, int],
    functions: Mapping[str, BoolFunction],
) -> RecoveredCover:
    """Recover and verify the two-level cover of ``outputs`` over ``variables``.

    ``var_of_pin`` maps input-pin component ids to variable indices (tied duplicate pins map to the same index);
    ``functions`` is the simulated behavior of each output over the variables (undefined rows as DC).
    """
    ctx = _Ctx(circ, graph, var_of_pin)
    pins = {p.name: p.comp_id for p in circ.outputs}
    try:
        shapes = [output_shape(ctx, o, pins[o]) for o in outputs]
        form, tech = _group_form(shapes)
        n = len(variables)
        terms = {s.output: tuple(dict.fromkeys(_cube(n, t, form) for t in s.terms)) for s in shapes}
    except _Beyond as exc:
        return RecoveredCover(RecoverStatus.BEYOND_TWO_LEVEL, reasons=[str(exc)])
    cover = Cover(form, variables, terms)
    ok, undefined = verify(cover, functions)
    if not ok:
        return RecoveredCover(RecoverStatus.MISMATCH, form, cover, tech,
                              ["recovered two-level structure disagrees with the simulated truth table"])
    return RecoveredCover(RecoverStatus.RECOVERED, form, cover, tech, [], True, undefined)


__all__ = [
    "Literal",
    "OutputShape",
    "RecoverStatus",
    "RecoveredCover",
    "StructuralCost",
    "connected_inputs",
    "cover_function",
    "recover_group",
    "structural_cost",
    "verify",
]
