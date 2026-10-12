"""NAND/NOR cost model for two-level NAND-NAND (SOP) / NOR-NOR (POS) multi-output covers.

Rules:

* every distinct cube with >= 2 literals used by any output is one first-level gate (#literals inputs);
* an output with >= 2 cubes gets one output gate (#cubes inputs);
* an output that is a single multi-literal cube = that term gate + one output inverter (1 gate, 2 inputs);
* an output equal to a single literal needs no gate;
* negators (NOT = NAND/NOR with tied inputs, 1 gate / 2 inputs), one per variable needed complemented:
  - a multi-literal term with the variable in negated polarity (SOP cube '0', POS cube '1');
  - a single-literal cube inside a multi-cube cover in *positive* polarity (it enters the output gate
    complemented);
  - an output equal to a single negated literal.
"""

from __future__ import annotations

from logilens.core.logic_types import Cost, CostModel, Cover, Cube, Form, Objective
from logilens.logic.cube import literal_positions


def _single_literal(c: Cube) -> tuple[int, str]:
    """``(input_index, cube_char)`` of a one-literal cube."""
    (i, v), = literal_positions(c)
    return i, str(v)


def _term_negations(c: Cube, form: Form) -> set[int]:
    neg = form.negated_char
    return {i for i, v in literal_positions(c) if str(v) == neg}


def _output_needs(cubes: tuple[Cube, ...], form: Form, model: CostModel) -> tuple[int, int, int, set[int]]:
    """Second-level needs of one output: (output_gates, output_gate_inputs, output_inverters, negated vars)."""
    neg = form.negated_char
    if not cubes or (len(cubes) == 1 and cubes[0].num_literals == 0):
        return 0, 0, 0, set()  # constant output
    if len(cubes) == 1 and cubes[0].num_literals >= 2:
        return 0, 0, 1, set()
    if len(cubes) == 1 and model.single_literal_free:
        i, ch = _single_literal(cubes[0])
        return 0, 0, 0, ({i} if ch == neg else set())
    needs: set[int] = set()
    for c in cubes:
        if c.num_literals == 1:
            i, ch = _single_literal(c)
            if ch != neg:
                needs.add(i)
    if len(cubes) == 1:  # single literal, not free: a tied output gate fed with the opposite literal
        return 1, 2 if model.not_as_tied_gate else 1, 0, needs
    return 1, len(cubes), 0, needs


def nandnor_cost(cover: Cover, model: CostModel | None = None) -> Cost:
    """Gates / inputs of ``cover`` under the NAND/NOR cost model (see module docstring)."""
    model = model or CostModel(tech=cover.form.tech)
    form = cover.form
    terms = {c.key: c for c in cover.distinct_cubes() if c.num_literals >= 2}
    negated: set[int] = set()
    for c in terms.values():
        negated |= _term_negations(c, form)
    out_gates = out_inputs = out_inv = 0
    for cubes in cover.terms.values():
        g, i, inv, needs = _output_needs(tuple(cubes), form, model)
        out_gates, out_inputs, out_inv = out_gates + g, out_inputs + i, out_inv + inv
        negated |= needs
    not_inputs = 2 if model.not_as_tied_gate else 1
    negators = 0 if model.complemented_inputs_available else len(negated)
    term_inputs = sum(c.num_literals for c in terms.values())
    gates = len(terms) + out_gates + out_inv + negators
    inputs = term_inputs + out_inputs + not_inputs * (out_inv + negators)
    breakdown: dict[str, object] = {
        "terms": len(terms),
        "term_inputs": term_inputs,
        "output_gates": out_gates,
        "output_gate_inputs": out_inputs,
        "output_inverters": out_inv,
        "negators": negators,
        "negated_vars": tuple(cover.inputs[i] for i in sorted(negated)),
    }
    return Cost(gates, inputs, negators, breakdown)


def objective_key(cost: Cost, objective: Objective = Objective.GATES_INPUTS) -> tuple[int, ...]:
    """Lexicographic comparison key for ``objective`` (smaller is better)."""
    neg = cost.inverters
    if objective is Objective.INPUTS_GATES:
        return (cost.inputs, cost.gates)
    if objective is Objective.GATES_NO_NEGATORS:
        return (cost.gates - neg, cost.inputs - 2 * neg, neg)
    if objective is Objective.MIN_NEGATORS:
        return (neg, cost.gates, cost.inputs)
    return (cost.gates, cost.inputs)


def cost_lines(cost: Cost) -> list[str]:
    """Human-readable breakdown lines."""
    b = cost.breakdown
    return [
        f"terms: {b.get('terms')} gates, {b.get('term_inputs')} inputs",
        f"output gates: {b.get('output_gates')} gates, {b.get('output_gate_inputs')} inputs",
        f"output inverters: {b.get('output_inverters')}",
        f"negators: {b.get('negators')} ({', '.join(b.get('negated_vars', ())) or '-'})",  # type: ignore[arg-type]
        f"total: {cost.gates} gates / {cost.inputs} inputs",
    ]
