"""Reference numbers for the line-code converter fixture."""

from __future__ import annotations

import time

import pytest

from logilens.core.logic_types import CostModel, Form, MultiFunction, Objective
from logilens.env.espresso_build import find_espresso, toolchain_available
from logilens.minimize.base import make_problem
from logilens.minimize.compare import compare_methods
from logilens.minimize.espresso import espresso_minimize
from logilens.minimize.exact_mo import exact_multi_output, multi_output_primes
from logilens.minimize.ilp import ilp_minimize
from logilens.minimize.petrick import independent_minimize, petrick_all
from logilens.minimize.qm import qm_primes
from logilens.minimize.robustness import robustness
from logilens.minimize.shared_terms import best_sharing
from logilens.minimize.tison import tison_primes

PRIMES = {Form.SOP: {"A": 8, "B": 9, "C": 12, "D": 11}, Form.POS: {"A": 5, "B": 13, "C": 11, "D": 11}}
PETRICK = {
    Form.SOP: {"A": ((2, 5), 3), "B": ((3, 8), 1), "C": ((3, 8), 1), "D": ((3, 7), 1)},
    Form.POS: {"A": ((3, 4), 1), "B": ((4, 9), 12), "C": ((4, 9), 1), "D": ((3, 7), 2)},
}
OPTIMUM = {Form.SOP: (19, 48), Form.POS: (18, 45)}
ESPRESSO = {
    Form.SOP: {"default": (20, 54), "exact": (19, 52), "signature": (19, 53), "qm": (19, 52), "so": (20, 49),
               "efast": (20, 52)},
    Form.POS: {"default": (18, 45), "exact": (18, 47), "signature": (18, 47), "qm": (18, 47), "so": (20, 49),
               "efast": (18, 45)},
}
FORMS = (Form.SOP, Form.POS)


def pair(res) -> tuple[int, int]:
    assert res.cost is not None
    return res.cost.gates, res.cost.inputs


@pytest.mark.parametrize("form", FORMS)
def test_qm_and_tison_prime_sets(conv: MultiFunction, form: Form) -> None:
    problem = make_problem(conv, form)
    for name, expected in PRIMES[form].items():
        t = problem.targets[name]
        qm, _ = qm_primes(5, t.on, t.dc)
        ti, _ = tison_primes(5, t.on, t.dc)
        assert len(qm) == expected
        assert {p.key for p in qm} == {p.key for p in ti}


@pytest.mark.parametrize("form", FORMS)
def test_petrick_per_function(conv: MultiFunction, form: Form) -> None:
    results = petrick_all(make_problem(conv, form))
    for name, (best, count) in PETRICK[form].items():
        assert results[name].best == best
        assert len(results[name].variants) == count


@pytest.mark.parametrize("form", FORMS)
def test_independent_and_sharing(conv: MultiFunction, form: Form) -> None:
    indep = independent_minimize(conv, form)
    assert indep.verified
    res, stats = best_sharing(conv, form)
    assert res.verified
    assert stats.combinations == (3 if form is Form.SOP else 24)
    assert stats.best == ((20, 49) if form is Form.SOP else (18, 45))
    assert pair(res) == stats.best
    assert stats.worst == ((20, 49) if form is Form.SOP else (21, 51))
    assert pair(indep) in stats.distribution


@pytest.mark.parametrize("form", FORMS)
def test_exact_multi_output(conv: MultiFunction, form: Form) -> None:
    assert len(multi_output_primes(make_problem(conv, form))) == (30 if form is Form.SOP else 37)
    res = exact_multi_output(conv, form)
    assert res.verified and res.proof is not None and res.proof.optimal
    assert res.proof.objective == (10 if form is Form.SOP else 9)
    assert pair(res) == OPTIMUM[form]


@pytest.mark.parametrize("form", FORMS)
def test_ilp_optimum(conv: MultiFunction, form: Form) -> None:
    res = ilp_minimize(conv, form)
    assert res.proof is not None and res.proof.status == "Optimal"
    assert res.verified and pair(res) == OPTIMUM[form]
    assert res.cost is not None and res.cost.inverters == 5


@pytest.mark.parametrize("form", FORMS)
def test_robustness(conv: MultiFunction, form: Form) -> None:
    rep = robustness(conv, form)
    assert rep.identical
    assert all((c.gates, c.inputs) == OPTIMUM[form] for c in rep.costs.values() if c)
    assert rep.min_negators == 5
    assert rep.negator_limits == {4: "Infeasible"}


def test_exact_methods_fast(conv: MultiFunction) -> None:
    start = time.perf_counter()
    for form in FORMS:
        ilp_minimize(conv, form)
        exact_multi_output(conv, form)
    assert time.perf_counter() - start < 30


def test_ilp_objectives_and_limits_api(conv: MultiFunction) -> None:
    res = ilp_minimize(conv, Form.SOP, CostModel(objective=Objective.INPUTS_GATES), max_negators=5)
    assert pair(res) == OPTIMUM[Form.SOP]


espresso_ready = pytest.mark.skipif(
    find_espresso() is None and not toolchain_available(), reason="espresso not built and no make/cc available"
)


@espresso_ready
@pytest.mark.parametrize("form", FORMS)
def test_espresso_modes(conv: MultiFunction, form: Form) -> None:
    for mode, expected in ESPRESSO[form].items():
        res = espresso_minimize(conv, form, mode)
        assert res.verified, (mode, res.notes)
        assert pair(res) == expected, mode
    so_both = espresso_minimize(conv, form, "so_both")
    assert so_both.cover is None and so_both.notes[0].startswith("unsupported")


@espresso_ready
def test_compare_table(conv: MultiFunction) -> None:
    comp = compare_methods(conv)
    assert comp.reference == {Form.SOP: (19, 48), Form.POS: (18, 45)}
    sop_agree = set(comp.agreeing_with_reference(Form.SOP))
    assert {"exact_mo", "ilp"} <= sop_agree
    assert all(row.verified for row in comp.rows)
    assert any("identical" in row.note for row in comp.rows if row.method == "tison+petrick")
