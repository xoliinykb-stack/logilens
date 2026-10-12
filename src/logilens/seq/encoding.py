"""State encodings (current, binary, Gray, one-hot) with an estimated two-level cost.

For each encoding of the reachable, minimized machine the flip-flop input functions (D, and J/K via the
excitation table) plus the output functions are derived — codes that no state uses are don't cares — and
minimized together with the exact ILP of ``minimize/ilp.py`` under the NAND/NOR cost model, in SOP (NAND) and
POS (NOR); the cheaper form is reported. "proven" is true only when HiGHS proved both forms optimal.
Encodings with more than ``max_vars`` variables are skipped (not estimated).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, log2
from typing import Any

from logilens.core.logic_types import Form, MinimizationResult, MultiFunction
from logilens.logic.cost import objective_key
from logilens.logic.expr import cover_to_expr, to_text
from logilens.minimize.ilp import ilp_minimize
from logilens.seq.excitation import next_state_functions, output_functions
from logilens.seq.fsm import FSM

MAX_VARS = 8


@dataclass
class EncodingCost:
    ff: str  # D | JK
    form: str | None
    gates: int | None
    inputs: int | None
    proven: bool
    equations: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ff": self.ff, "form": self.form, "gates": self.gates, "inputs": self.inputs,
                "proven": self.proven, "equations": dict(self.equations), "note": self.note}


@dataclass
class Encoding:
    name: str  # current | binary | gray | one-hot
    state_vars: list[str]
    codes: dict[str, str]  # state code (original) -> new code
    costs: list[EncodingCost] = field(default_factory=list)
    skipped: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def flip_flops(self) -> int:
        return len(self.state_vars)

    def best(self) -> EncodingCost | None:
        done = [c for c in self.costs if c.gates is not None]
        return min(done, key=lambda c: (c.gates, c.inputs)) if done else None

    def to_dict(self, fsm: FSM | None = None) -> dict[str, Any]:
        name = (lambda s: fsm.name(s)) if fsm is not None else (lambda s: s)
        return {"name": self.name, "flip_flops": self.flip_flops, "state_vars": list(self.state_vars),
                "codes": {name(s): c for s, c in self.codes.items()},
                "costs": [c.to_dict() for c in self.costs], "skipped": self.skipped, "notes": list(self.notes)}


def _bits(n_states: int) -> int:
    return max(1, ceil(log2(n_states))) if n_states > 1 else 1


def _var_names(prefix: str, k: int, taken: set[str]) -> list[str]:
    while any(f"{prefix}{i}" in taken for i in range(1, k + 1)):
        prefix = prefix + "_"
    return [f"{prefix}{i}" for i in range(1, k + 1)]


def assignments(fsm: FSM, order: list[str]) -> list[Encoding]:
    """Current codes plus binary / Gray / one-hot in ``order`` (initial state first => all-zero code)."""
    n = len(order)
    taken = set(fsm.inputs)
    k = _bits(n)
    q = _var_names("q", k, taken)
    out = [Encoding("current", list(fsm.state_vars), {s: s for s in order})]
    out.append(Encoding("binary", q, {s: format(i, f"0{k}b") for i, s in enumerate(order)}))
    out.append(Encoding("gray", q, {s: format(i ^ (i >> 1), f"0{k}b") for i, s in enumerate(order)}))
    oh = _var_names("q", n, taken)
    one_hot = Encoding("one-hot", oh, {s: "".join("1" if j == i else "0" for j in range(n))
                                       for i, s in enumerate(order)})
    one_hot.notes.append("Logisim flip-flops power on at 0: one-hot needs a preset of the initial state's "
                         "flip-flop (or a reset input) to start correctly")
    out.append(one_hot)
    return out


def _minimize(mf: MultiFunction, time_limit: float) -> tuple[MinimizationResult | None, bool]:
    best: MinimizationResult | None = None
    proven = True
    for form in (Form.SOP, Form.POS):
        res = ilp_minimize(mf, form, time_limit=time_limit)
        proven = proven and res.proof is not None and res.proof.optimal
        if res.cost is None or not res.verified:
            proven = False
            continue
        if best is None or objective_key(res.cost) < objective_key(best.cost):  # type: ignore[arg-type]
            best = res
    return best, proven


def estimate(fsm: FSM, enc: Encoding, ff: str, time_limit: float = 20.0) -> EncodingCost:
    care = set(enc.codes)
    kinds = [ff] * len(enc.state_vars)
    ns = next_state_functions(enc.codes, fsm.delta, fsm.input_codes, enc.state_vars, fsm.inputs, kinds, care)
    outs = output_functions(fsm, enc.codes, enc.state_vars, care)
    funcs = {**ns.functions, **outs.functions}
    mf = MultiFunction(ns.inputs, tuple(funcs), funcs)
    res, proven = _minimize(mf, time_limit)
    if res is None or res.cover is None or res.cost is None:
        return EncodingCost(ff, None, None, None, False, note="minimization failed")
    eqs = {o: to_text(cover_to_expr(res.cover.terms[o], mf.inputs, res.form)) for o in mf.outputs}
    return EncodingCost(ff, res.form.value, res.cost.gates, res.cost.inputs, proven, eqs,
                        "" if proven else "optimality not proven")


def compare_encodings(fsm: FSM, order: list[str], *, flip_flops: tuple[str, ...] = ("D", "JK"),
                      max_vars: int = MAX_VARS, time_limit: float = 20.0) -> list[Encoding]:
    """Encodings of the machine restricted to ``order`` (reachable states, initial first) with costs.

    ``fsm`` must be closed on ``order`` (e.g. the reduced machine from ``state_min.reduced_fsm``).
    """
    encs = assignments(fsm, order)
    for enc in encs:
        n = len(enc.state_vars) + len(fsm.inputs)
        if n > max_vars:
            enc.skipped = f"{n} variables > {max_vars}: cost not estimated"
            continue
        if len(set(enc.codes.values())) != len(enc.codes):
            enc.skipped = "codes are not distinct"
            continue
        for ff in flip_flops:
            enc.costs.append(estimate(fsm, enc, ff, time_limit))
    return encs
