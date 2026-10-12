"""Randomized cross-checks of the exact methods on small functions (fixed seed)."""

from __future__ import annotations

import random

import pytest

from logilens.core.logic_types import Form, MultiFunction
from logilens.logic.truth_table import function_from_sets
from logilens.minimize.exact_mo import exact_multi_output
from logilens.minimize.ilp import ilp_minimize
from logilens.minimize.shared_terms import best_sharing


def random_function(rng: random.Random, n: int, outputs: int) -> MultiFunction:
    names = tuple("abcdef"[:n])
    funcs = {}
    for k in range(outputs):
        on = dc = 0
        for m in range(1 << n):
            r = rng.random()
            if r < 0.4:
                on |= 1 << m
            elif r < 0.55:
                dc |= 1 << m
        funcs["FGHI"[k]] = function_from_sets(n, on, dc)
    return MultiFunction(names, tuple(funcs), funcs)


@pytest.mark.parametrize("seed", range(12))
def test_ilp_is_never_worse_and_consistent(seed: int) -> None:
    rng = random.Random(seed)
    mf = random_function(rng, rng.choice((2, 3, 4)), rng.choice((1, 2, 3)))
    for form in (Form.SOP, Form.POS):
        ilp = ilp_minimize(mf, form)
        assert ilp.proof is not None and ilp.proof.optimal
        assert ilp.verified and ilp.cost is not None
        assert not any("differs" in n for n in ilp.notes), ilp.notes
        for other in (exact_multi_output(mf, form), best_sharing(mf, form)[0]):
            assert other.verified and other.cost is not None
            assert (ilp.cost.gates, ilp.cost.inputs) <= (other.cost.gates, other.cost.inputs)


def test_constant_and_literal_outputs() -> None:
    n = 3
    full = (1 << 8) - 1
    a_mask = 0b11110000  # a = 1 for minterms 4..7
    funcs = {
        "Z": function_from_sets(n, 0),
        "O": function_from_sets(n, full),
        "A": function_from_sets(n, a_mask),
        "NA": function_from_sets(n, full & ~a_mask),
    }
    mf = MultiFunction(("a", "b", "c"), tuple(funcs), funcs)
    sop = ilp_minimize(mf, Form.SOP)
    assert sop.verified and sop.cost is not None
    # only NA = a' costs anything: one negator (1 gate / 2 inputs)
    assert (sop.cost.gates, sop.cost.inputs) == (1, 2)
    pos = ilp_minimize(mf, Form.POS)
    assert pos.cost is not None and (pos.cost.gates, pos.cost.inputs) == (1, 2)
