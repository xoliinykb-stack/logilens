"""QM, Tison and Petrick on textbook functions."""

from __future__ import annotations

from logilens.logic.cube import cube_from_str
from logilens.logic.truth_table import mask_from_minterms
from logilens.minimize.petrick import essential_indices, petrick
from logilens.minimize.qm import qm_primes
from logilens.minimize.tison import tison_primes

# f(a,b,c,d) = Σm(0,1,2,5,6,7,8,9,10,14)
ON4 = mask_from_minterms([0, 1, 2, 5, 6, 7, 8, 9, 10, 14])
PRIMES4 = {"-00-", "-0-0", "--10", "0-01", "01-1", "011-"}


def test_qm_primes_textbook() -> None:
    primes, steps = qm_primes(4, ON4)
    assert {str(p) for p in primes} == PRIMES4
    kinds = [s.kind for s in steps]
    assert kinds[0] == "qm.group" and "qm.merge" in kinds and kinds[-1] == "qm.primes"
    assert any("0 ones: 0000 m(0)" in line for line in steps[0].lines)


def test_tison_equals_qm() -> None:
    primes, steps = tison_primes(4, ON4, 0, ("a", "b", "c", "d"))
    assert {str(p) for p in primes} == PRIMES4
    assert [s.kind for s in steps].count("tison.pass") == 4


def test_petrick_textbook_unique_minimum() -> None:
    primes, _ = qm_primes(4, ON4)
    res = petrick("f", primes, ON4)
    assert res.best == (3, 7)
    assert len(res.variants) == 1
    assert {str(c) for c in res.variants[0]} == {"-00-", "--10", "01-1"}
    assert {s.kind for s in res.steps} >= {"petrick.chart", "petrick.essential", "petrick.product"}


def test_petrick_cyclic_core_two_solutions() -> None:
    on = mask_from_minterms([0, 1, 2, 5, 6, 7])
    primes, _ = qm_primes(3, on)
    assert len(primes) == 6
    assert essential_indices(primes, on) == []
    res = petrick("f", primes, on)
    assert res.best == (3, 6)
    assert len(res.variants) == 2


def test_dont_care_only_primes_dropped() -> None:
    on = mask_from_minterms([0])
    dc = mask_from_minterms([3])
    primes, _ = qm_primes(2, on, dc)
    assert [str(p) for p in primes] == ["00"]
    all_primes, _ = qm_primes(2, on, dc, keep_dc_only=True)
    assert cube_from_str("11") in all_primes
