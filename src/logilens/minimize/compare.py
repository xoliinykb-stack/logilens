"""Run every minimization method for SOP and POS and build a comparison table."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from logilens.core.logic_types import CostModel, Form, MinimizationResult, MultiFunction, Objective
from logilens.minimize.base import make_problem
from logilens.minimize.espresso import espresso_minimize
from logilens.minimize.exact_mo import exact_multi_output
from logilens.minimize.ilp import ilp_minimize
from logilens.minimize.petrick import independent_minimize, petrick_all
from logilens.minimize.shared_terms import best_sharing

DEFAULT_METHODS: tuple[str, ...] = (
    "qm+petrick",
    "tison+petrick",
    "petrick+sharing",
    "exact_mo",
    "ilp",
    "espresso:default",
    "espresso:exact",
    "espresso:signature",
    "espresso:qm",
    "espresso:so",
    "espresso:efast",
)


@dataclass(frozen=True)
class ComparisonRow:
    """One table row. ``gates``/``inputs`` are None when the method produced no cover."""

    method: str
    form: Form
    gates: int | None
    inputs: int | None
    proof: str | None
    verified: bool
    runtime_s: float
    note: str = ""


@dataclass
class Comparison:
    """Rows, raw results and agreement groups (``(gates, inputs)`` -> methods) per form."""

    rows: list[ComparisonRow] = field(default_factory=list)
    results: dict[tuple[str, Form], MinimizationResult] = field(default_factory=dict)
    agreement: dict[Form, dict[tuple[int, int], list[str]]] = field(default_factory=dict)
    reference: dict[Form, tuple[int, int] | None] = field(default_factory=dict)

    def agreeing_with_reference(self, form: Form) -> list[str]:
        """Methods whose cost equals the proven (ILP) optimum of ``form``."""
        ref = self.reference.get(form)
        return list(self.agreement.get(form, {}).get(ref, [])) if ref else []


def run_method(
    mf: MultiFunction, form: Form, method: str, model: CostModel | None = None, espresso_binary: Path | None = None
) -> MinimizationResult:
    """Run one named method (see :data:`DEFAULT_METHODS`)."""
    if method == "qm+petrick":
        return independent_minimize(mf, form, "qm", model)
    if method == "tison+petrick":
        res = independent_minimize(mf, form, "tison", model)
        res.notes.append(_prime_agreement(mf, form))
        return res
    if method == "petrick+sharing":
        return best_sharing(mf, form, model)[0]
    if method == "exact_mo":
        return exact_multi_output(mf, form, model)
    if method == "ilp":
        return ilp_minimize(mf, form, model)
    if method.startswith("espresso:"):
        return espresso_minimize(mf, form, method.split(":", 1)[1], espresso_binary, model)
    raise ValueError(f"unknown method {method!r}")


def _prime_agreement(mf: MultiFunction, form: Form) -> str:
    problem = make_problem(mf, form)
    qm = petrick_all(problem, "qm")
    tison = petrick_all(problem, "tison")
    same = all({p.key for p in qm[o].primes} == {p.key for p in tison[o].primes} for o in problem.outputs)
    return "Tison prime sets identical to QM" if same else "Tison prime sets DIFFER from QM"


def _row(res: MinimizationResult) -> ComparisonRow:
    proof = f"{res.proof.kind}:{res.proof.status}" if res.proof else None
    gates = res.cost.gates if res.cost else None
    inputs = res.cost.inputs if res.cost else None
    note = "; ".join(n for n in res.notes if n.startswith(("unsupported", "espresso", "Tison", "ILP")))
    return ComparisonRow(res.method, res.form, gates, inputs, proof, res.verified, res.runtime_s, note)


def compare_methods(
    mf: MultiFunction,
    forms: Iterable[Form] = (Form.SOP, Form.POS),
    methods: Iterable[str] = DEFAULT_METHODS,
    objective: Objective = Objective.GATES_INPUTS,
    espresso_binary: Path | None = None,
) -> Comparison:
    """Run ``methods`` for each form; group methods by identical (gates, inputs)."""
    comp = Comparison()
    for form in forms:
        model = CostModel(tech=form.tech, objective=objective)
        groups: dict[tuple[int, int], list[str]] = {}
        for method in methods:
            res = run_method(mf, form, method, model, espresso_binary)
            comp.results[(method, form)] = res
            comp.rows.append(_row(res))
            if res.cost is not None and res.verified:
                groups.setdefault((res.cost.gates, res.cost.inputs), []).append(method)
        comp.agreement[form] = groups
        ilp = comp.results.get(("ilp", form))
        proven = ilp is not None and ilp.cost is not None and ilp.proof is not None and ilp.proof.optimal
        comp.reference[form] = (ilp.cost.gates, ilp.cost.inputs) if proven else None  # type: ignore[union-attr]
    return comp
