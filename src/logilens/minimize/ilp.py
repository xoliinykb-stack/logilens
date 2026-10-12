"""Exact multi-output two-level minimization under the NAND/NOR cost as an ILP (scipy.optimize.milp / HiGHS).

Variables (all binary):

* ``x_t``   multi-literal cube ``t`` is built (one first-level gate, ``lits(t)`` inputs);
* ``y_tF``  output ``F`` uses cube ``t`` (``t`` implicant of F touching its target ON-set);
* ``k_F``   F has >= 2 cubes (output gate with ``s_F`` inputs);
* ``inv_F`` F is a single multi-literal cube (output inverter, 1 gate / 2 inputs);
* ``n_v``   negator of variable ``v``.

Per output (non-constant): ``gates_F = k_F + inv_F`` and ``inputs_F = s_F - 1 + k_F + 2 inv_F`` where
``s_F = Σ_t y_tF`` (the ``-1`` is a constant and is added back when re-costing).
The chosen cover is always re-costed with :mod:`logilens.logic.cost` and verified.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from logilens.core.logic_types import (
    CostModel,
    Cube,
    Form,
    MinimizationResult,
    MultiFunction,
    Objective,
    Proof,
    Step,
)
from logilens.logic.cube import all_cubes, cube_mask, literal_positions
from logilens.logic.truth_table import minterms_of
from logilens.minimize.base import Problem, default_model, finish, make_cover, make_problem
from logilens.minimize.exact_mo import multi_output_primes

ALL_CUBES_MAX_N = 8
STATUS = {0: "Optimal", 1: "Limit reached", 2: "Infeasible", 3: "Unbounded", 4: "Other"}


@dataclass
class _Model:
    """Column registry + sparse rows of the ILP."""

    names: list[str] = field(default_factory=list)
    rows: list[tuple[dict[int, float], float, float]] = field(default_factory=list)

    def var(self, name: str) -> int:
        self.names.append(name)
        return len(self.names) - 1

    def add(self, coeffs: dict[int, float], lo: float, hi: float) -> None:
        self.rows.append((coeffs, lo, hi))


@dataclass
class _Vars:
    x: dict[int, int] = field(default_factory=dict)  # cube index -> column (multi-literal only)
    y: dict[tuple[int, str], int] = field(default_factory=dict)
    k: dict[str, int] = field(default_factory=dict)
    inv: dict[str, int] = field(default_factory=dict)
    neg: dict[int, int] = field(default_factory=dict)  # input index -> column


def candidate_cubes(problem: Problem) -> list[Cube]:
    """All cubes usable by >= 1 output (all 3**n cubes for n <= 8, multi-output primes above)."""
    if problem.n > ALL_CUBES_MAX_N:
        return multi_output_primes(problem)
    out = []
    for c in all_cubes(problem.n):
        mask = cube_mask(c)
        tag = sum(1 << k for k, o in enumerate(problem.outputs)
                  if not mask & problem.targets[o].off and mask & problem.targets[o].on)
        if tag:
            out.append(Cube(c.n, c.care, c.value, tag))
    return out


def _active_outputs(problem: Problem) -> list[str]:
    """Outputs with a non-empty target ON-set and non-empty target OFF-set (others are constants)."""
    return [o for o in problem.outputs if problem.targets[o].on and problem.targets[o].off]


def _build(problem: Problem, cubes: list[Cube], model: CostModel, max_negators: int | None) -> tuple[_Model, _Vars]:
    m, v = _Model(), _Vars()
    active = _active_outputs(problem)
    for ti, c in enumerate(cubes):
        if c.num_literals >= 2:
            v.x[ti] = m.var(f"x[{c}]")
        for k, o in enumerate(problem.outputs):
            if o in active and c.outputs >> k & 1:
                v.y[(ti, o)] = m.var(f"y[{c},{o}]")
    for o in active:
        v.k[o] = m.var(f"k[{o}]")
        v.inv[o] = m.var(f"inv[{o}]")
    if not model.complemented_inputs_available:
        for i in range(problem.n):
            v.neg[i] = m.var(f"n[{problem.inputs[i]}]")
    _cover_rows(problem, cubes, m, v, active)
    _structure_rows(cubes, m, v, active)
    if v.neg:
        _negator_rows(problem.form, cubes, m, v, active)
        if max_negators is not None:
            m.add({col: 1.0 for col in v.neg.values()}, -np.inf, float(max_negators))
    return m, v


def _cover_rows(problem: Problem, cubes: list[Cube], m: _Model, v: _Vars, active: list[str]) -> None:
    masks = [cube_mask(c) for c in cubes]
    for o in active:
        for mt in minterms_of(problem.targets[o].on):
            cols = {col: 1.0 for (ti, oo), col in v.y.items() if oo == o and masks[ti] >> mt & 1}
            m.add(cols, 1.0, np.inf)


def _structure_rows(cubes: list[Cube], m: _Model, v: _Vars, active: list[str]) -> None:
    for (ti, o), col in v.y.items():
        if ti in v.x:
            m.add({col: 1.0, v.x[ti]: -1.0}, -np.inf, 0.0)  # y <= x
            m.add({col: 1.0, v.k[o]: -1.0, v.inv[o]: -1.0}, -np.inf, 0.0)  # inv >= y - k
    for o in active:
        ys = {col: 1.0 for (ti, oo), col in v.y.items() if oo == o}
        big = float(len(ys))
        m.add({**ys, v.k[o]: -2.0}, 0.0, np.inf)  # s >= 2k
        m.add({**ys, v.k[o]: -big}, -np.inf, 1.0)  # s <= 1 + big*k


def _negator_rows(form: Form, cubes: list[Cube], m: _Model, v: _Vars, active: list[str]) -> None:
    neg = form.negated_char
    for ti, c in enumerate(cubes):
        lits = literal_positions(c)
        if ti in v.x:
            for i, val in lits:
                if str(val) == neg:
                    m.add({v.x[ti]: 1.0, v.neg[i]: -1.0}, -np.inf, 0.0)
        elif len(lits) == 1:
            (i, val), = lits
            for o in active:
                col = v.y.get((ti, o))
                if col is None:
                    continue
                if str(val) == neg:  # single negated literal as whole output: n >= y - k
                    m.add({col: 1.0, v.k[o]: -1.0, v.neg[i]: -1.0}, -np.inf, 0.0)
                else:  # positive literal inside a multi-cube cover: n >= y + k - 1
                    m.add({col: 1.0, v.k[o]: 1.0, v.neg[i]: -1.0}, -np.inf, 1.0)


def _cost_vectors(cubes: list[Cube], v: _Vars, size: int, model: CostModel) -> tuple[np.ndarray, ...]:
    """(gates, inputs, negators) coefficient vectors (constants omitted)."""
    not_in = 2.0 if model.not_as_tied_gate else 1.0
    gates, inputs, negs = np.zeros(size), np.zeros(size), np.zeros(size)
    for ti, col in v.x.items():
        gates[col] = 1.0
        inputs[col] = cubes[ti].num_literals
    for col in v.y.values():
        inputs[col] += 1.0
    for o in v.k:
        gates[v.k[o]] += 1.0
        inputs[v.k[o]] += 1.0
        gates[v.inv[o]] += 1.0
        inputs[v.inv[o]] += not_in
    for col in v.neg.values():
        gates[col] += 1.0
        inputs[col] += not_in
        negs[col] = 1.0
    return gates, inputs, negs


def _objective(gates: np.ndarray, inputs: np.ndarray, negs: np.ndarray, objective: Objective) -> np.ndarray:
    big_in = float(inputs.sum() + 1)
    big_n = float(negs.sum() + 1)
    if objective is Objective.INPUTS_GATES:
        return inputs * (gates.sum() + 1) + gates
    if objective is Objective.GATES_NO_NEGATORS:
        return ((gates - negs) * (big_in * big_n) + (inputs - 2 * negs) * big_n + negs)
    if objective is Objective.MIN_NEGATORS:
        return negs * ((gates.sum() + 1) * big_in) + gates * big_in + inputs
    return gates * big_in + inputs


def _solve(m: _Model, c: np.ndarray, time_limit: float | None):
    data, ri, ci, lo, hi = [], [], [], [], []
    for r, (coeffs, low, high) in enumerate(m.rows):
        for col, val in coeffs.items():
            ri.append(r)
            ci.append(col)
            data.append(val)
        lo.append(low)
        hi.append(high)
    a = coo_matrix((data, (ri, ci)), shape=(len(m.rows), len(m.names))).tocsr()
    options: dict[str, float] = {"mip_rel_gap": 0.0}  # weighted lexicographic objective: no gap allowed
    if time_limit:
        options["time_limit"] = time_limit
    return milp(c, constraints=LinearConstraint(a, lo, hi), integrality=np.ones(len(m.names)),
                bounds=Bounds(0, 1), options=options)


def ilp_minimize(
    mf: MultiFunction,
    form: Form,
    model: CostModel | None = None,
    max_negators: int | None = None,
    time_limit: float | None = 60.0,
) -> MinimizationResult:
    """Cost-optimal multi-output cover. ``proof.status`` is 'Optimal' only if HiGHS proved it."""
    started = time.perf_counter()
    model = model or default_model(form)
    problem = make_problem(mf, form)
    cubes = candidate_cubes(problem)
    m, v = _build(problem, cubes, model, max_negators)
    gates, inputs, negs = _cost_vectors(cubes, v, len(m.names), model)
    res = _solve(m, _objective(gates, inputs, negs, model.objective), time_limit)
    status = STATUS.get(res.status, "Other")
    proof = Proof("ilp", status, float(res.fun) if res.fun is not None else None,
                  getattr(res, "mip_gap", None), "scipy.milp/HiGHS")
    notes = [f"{len(cubes)} candidate cubes, {len(m.names)} variables, {len(m.rows)} constraints",
             f"objective: {model.objective.value}"]
    if max_negators is not None:
        notes.append(f"negator limit: {max_negators}")
    if not model.single_literal_free:
        notes.append("single_literal_free=False is not modeled by the ILP; the NAND/NOR re-cost is authoritative")
    if res.x is None:
        return finish("ilp", problem, None, multi_output=True, model=model, proof=proof, started=started,
                      notes=notes + [f"solver: {res.message}"])
    terms: dict[str, list[Cube]] = {o: [] for o in problem.outputs}
    for (ti, o), col in v.y.items():
        if res.x[col] > 0.5:
            terms[o].append(cubes[ti])
    terms.update(_constant_outputs(problem))
    cover = make_cover(problem, terms)
    ilp_cost = (round(float(gates @ res.x)), round(float(inputs @ res.x)) - len(v.k))
    step = Step("ilp.model", "ILP model", tuple(notes), {"ilp_cost": ilp_cost})
    result = finish("ilp", problem, cover, multi_output=True, model=model, proof=proof, started=started,
                    steps=[step], notes=notes)
    if result.cost is not None and (result.cost.gates, result.cost.inputs) != ilp_cost:
        result.notes.append(f"ILP model cost {ilp_cost[0]}/{ilp_cost[1]} differs from the NAND/NOR re-cost "
                            f"{result.cost.short()} (the re-cost is authoritative)")
    return result


def _constant_outputs(problem: Problem) -> dict[str, list[Cube]]:
    """Covers of constant outputs: empty target ON-set -> no cube; empty target OFF-set -> universal cube."""
    out: dict[str, list[Cube]] = {}
    for o in problem.outputs:
        t = problem.targets[o]
        if not t.on:
            out[o] = []
        elif not t.off:
            out[o] = [Cube(problem.n, 0, 0)]
    return out
