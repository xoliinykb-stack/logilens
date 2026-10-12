"""NAND/NOR cost model: hand cases and the reference covers."""

from __future__ import annotations

from logilens.core.logic_types import CostModel, Cover, Form
from logilens.logic.cost import nandnor_cost
from logilens.logic.cube import cube_from_str

NAMES = ("a", "b", "c", "d", "e")

REF_SOP = {
    "A": ["--101", "-10-1", "0--10", "1--1-"],
    "B": ["-1-00", "01---", "10---"],
    "C": ["--01-", "--101", "-1-00", "001--"],
    "D": ["--001", "--100", "-10-1", "0--10", "001--", "10--0", "11-11"],
}
REF_POS = {
    "A": ["---00", "00---", "01111"],
    "B": ["00---", "1--10", "11--1"],
    "C": ["-0-0-", "-111-", "10--1"],
    "D": ["--101", "-001-", "-10-0", "0--00", "01111", "1--10", "10--1"],
}


def cover(form: Form, terms: dict[str, list[str]], names: tuple[str, ...] = NAMES) -> Cover:
    return Cover(form, names, {o: tuple(cube_from_str(s) for s in cs) for o, cs in terms.items()})


def cost_of(form: Form, terms: dict[str, list[str]], names: tuple[str, ...] = NAMES) -> tuple[int, int]:
    c = nandnor_cost(cover(form, terms, names))
    return c.gates, c.inputs


def test_single_positive_literal_is_free() -> None:
    assert cost_of(Form.SOP, {"F": ["1--"]}, ("a", "b", "c")) == (0, 0)


def test_not_is_one_gate_two_inputs() -> None:
    assert cost_of(Form.SOP, {"F": ["0--"]}, ("a", "b", "c")) == (1, 2)
    # POS: cube '1' is the complemented literal a'
    assert cost_of(Form.POS, {"F": ["1--"]}, ("a", "b", "c")) == (1, 2)
    assert cost_of(Form.POS, {"F": ["0--"]}, ("a", "b", "c")) == (0, 0)


def test_single_multi_literal_term_needs_output_inverter() -> None:
    # F = ab: NAND(a,b) + inverter = 2 gates, 2 + 2 inputs
    assert cost_of(Form.SOP, {"F": ["11-"]}, ("a", "b", "c")) == (2, 4)
    # F = ab': + negator of b
    c = nandnor_cost(cover(Form.SOP, {"F": ["10-"]}, ("a", "b", "c")))
    assert (c.gates, c.inputs, c.inverters) == (3, 6, 1)
    assert c.breakdown["output_inverters"] == 1


def test_single_literals_inside_multi_cube_cover() -> None:
    # F = a + b'c : output NAND(a', NAND(b', c)) -> negators a and b
    c = nandnor_cost(cover(Form.SOP, {"F": ["1--", "-01"]}, ("a", "b", "c")))
    assert c.breakdown["negated_vars"] == ("a", "b")
    assert (c.gates, c.inputs) == (1 + 1 + 2, 2 + 2 + 4)
    # F = a' + bc : a' enters the output gate as a -> no negator
    assert cost_of(Form.SOP, {"F": ["0--", "-11"]}, ("a", "b", "c")) == (2, 4)


def test_shared_terms_counted_once() -> None:
    g, i = cost_of(Form.SOP, {"F": ["11-", "--1"], "G": ["11-", "0-0"]}, ("a", "b", "c"))
    # terms: 11- (2 in), 0-0 (2 in); outputs 2 gates (2+2 in); negators: a, c (F: '--1' positive single
    # literal -> c'; G term 0-0 -> a', c')
    assert (g, i) == (2 + 2 + 2, 4 + 4 + 4)


def test_constant_outputs_cost_nothing() -> None:
    assert cost_of(Form.SOP, {"F": [], "G": ["---"]}, ("a", "b", "c")) == (0, 0)


def test_model_variants() -> None:
    cv = cover(Form.SOP, {"F": ["10-"]}, ("a", "b", "c"))
    free = nandnor_cost(cv, CostModel(complemented_inputs_available=True))
    assert (free.gates, free.inputs) == (2, 4)
    single_in = nandnor_cost(cv, CostModel(not_as_tied_gate=False))
    assert (single_in.gates, single_in.inputs) == (3, 4)


def test_reference_sop_cover_cost() -> None:
    c = nandnor_cost(cover(Form.SOP, REF_SOP))
    assert (c.gates, c.inputs) == (22, 64)
    assert c.inverters == 5
    assert c.breakdown["terms"] == 13


def test_reference_pos_cover_cost() -> None:
    c = nandnor_cost(cover(Form.POS, REF_POS))
    assert (c.gates, c.inputs) == (21, 61)
    assert c.inverters == 5
    assert c.breakdown["terms"] == 12
