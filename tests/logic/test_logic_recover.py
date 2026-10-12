"""Recovery of implemented two-level covers and structural cost counting on the reference circuits."""

from __future__ import annotations

from pathlib import Path

import pytest

from logilens.analysis.tables import circuit_functions, table_view
from logilens.backends import load_project, truth_table
from logilens.core.logic_types import Form
from logilens.graph.classify import classify
from logilens.logic.cost import nandnor_cost
from logilens.logic.recover import RecoverStatus, recover_group, structural_cost

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _groups(name: str, tie: bool = False):
    project = load_project(FIXTURES / name, backend="python")
    circ = project.main_circuit
    cl = classify(circ)
    table = truth_table(project, tie_duplicate_labels=tie)
    view = table_view(table)
    alias = {n: kept for kept, names in table.get("tied", {}).items() for n in names}
    out = {}
    for outputs in cl.groups:
        var_of_pin = {p.comp_id: view.inputs.index(alias.get(p.name, p.name)) for p in circ.inputs}
        rec = recover_group(circ, cl.graph, outputs, view.inputs, var_of_pin,
                            circuit_functions(view, outputs, view.inputs))
        cost = structural_cost(circ, set().union(*(cl.cones[o] for o in outputs)))
        out[outputs[0]] = (rec, cost)
    return out


def test_converter_recovered_and_counted() -> None:
    groups = _groups("converter_nand_nor.circ")
    (nand, nand_cost), (nor, nor_cost) = groups["A_N"], groups["A_R"]
    assert nand.status is RecoverStatus.RECOVERED and nand.form is Form.SOP and nand.technology == "nand"
    assert nor.status is RecoverStatus.RECOVERED and nor.form is Form.POS and nor.technology == "nor"
    assert (nand_cost.gates, nand_cost.inputs) == (19, 48) and nand_cost.nandnor_short() == "19/48"
    assert (nor_cost.gates, nor_cost.inputs) == (18, 45) and nor_cost.nandnor_short() == "18/45"
    assert nandnor_cost(nand.cover).short() == "19/48" and nandnor_cost(nor.cover).short() == "18/45"
    assert nand.verified and nor.verified


def test_draft_structural_cost_convention() -> None:
    groups = _groups("converter_draft.circ", tie=True)
    (nand, nand_cost), (nor, nor_cost) = groups["x"], groups["v"]
    assert nand.ok and nor.ok
    # as drawn: NOT = 1 gate / 1 input, the loose 3rd input of the NOR at (480,750) is not counted
    assert nand_cost.short() == "22/52" and nand_cost.by_type == {"NAND": (17, 47), "NOT": (5, 5)}
    assert nor_cost.short() == "23/51" and nor_cost.by_type == {"NOR": (18, 46), "NOT": (5, 5)}
    assert nor_cost.unconnected_inputs == 1
    # NAND/NOR counting: NOT = NAND/NOR with tied inputs (2 inputs)
    assert (nand_cost.nandnor_short(), nor_cost.nandnor_short()) == ("22/57", "23/56")


def test_mixed_gates_xor_is_beyond_two_level_and_and_or_is_recovered() -> None:
    groups = _groups("mixed_gates.circ")
    x, _ = groups["x"]
    y, y_cost = groups["y"]
    assert x.status is RecoverStatus.BEYOND_TWO_LEVEL and x.cover is None and x.reasons
    assert y.ok and y.technology == "and-or" and y.form is Form.SOP
    assert y_cost.short() == "7/12" and y_cost.nandnor_short() == "7/15"


@pytest.mark.parametrize("name", ["sample_bcd_excess3.circ"])
def test_sample_groups_verify(name: str) -> None:
    for rec, cost in _groups(name).values():
        assert rec.ok and rec.verified
        assert nandnor_cost(rec.cover).gates <= cost.nandnor_gates
