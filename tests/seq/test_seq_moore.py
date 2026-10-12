"""moore_fsm fixture: states z1z2 S0=10, S1=00, S2=01, S3=11; x=0 stay, x=1 next; y=0 only in S0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from logilens.backends import load_project
from logilens.seq import analyze_sequential, extract_fsm
from logilens.seq.dot import edges, to_svg
from logilens.seq.state_min import minimize_states

GEN = Path(__file__).resolve().parents[1] / "fixtures" / "gen"
NAMES = {"10": "S0", "00": "S1", "01": "S2", "11": "S3"}


@pytest.fixture(scope="module")
def project():  # type: ignore[no-untyped-def]
    return load_project(GEN / "moore_fsm.circ", backend="python")


@pytest.fixture(scope="module")
def result(project):  # type: ignore[no-untyped-def]
    return analyze_sequential(project, input_sequence="0110100", state_names=NAMES)


def test_structure(result) -> None:  # type: ignore[no-untyped-def]
    fsm = result.fsm
    assert result.applicable
    assert fsm.state_vars == ["z1", "z2"] and fsm.ff_kinds == ["D", "D"]
    assert fsm.inputs == ["x"]  # rst only drives asynchronous preset/reset
    assert fsm.async_inputs == ["rst"] and fsm.clock_sources == ["clk"]
    assert fsm.outputs == ["z1", "z2", "y"]
    assert any("asynchronous set/reset" in w for w in result.warnings)


def test_moore_delta_and_outputs(result) -> None:  # type: ignore[no-untyped-def]
    fsm = result.fsm
    assert fsm.kind == "moore"
    assert len(fsm.states) == 4
    n = {v: k for k, v in NAMES.items()}
    expected = {("S0", "0"): "S0", ("S0", "1"): "S1", ("S1", "0"): "S1", ("S1", "1"): "S2",
                ("S2", "0"): "S2", ("S2", "1"): "S3", ("S3", "0"): "S3", ("S3", "1"): "S0"}
    got = {(fsm.name(s), x): fsm.name(t) for (s, x), t in fsm.delta.items()}
    assert got == expected
    y = fsm.outputs.index("y")
    assert {fsm.name(s): fsm.lam[(s, "0")][y] for s in fsm.states} == {"S0": "0", "S1": "1", "S2": "1", "S3": "1"}
    for s in fsm.states:  # z1 z2 outputs show the state code
        assert "".join(fsm.lam[(s, "1")][:2]) == s
    assert n["S0"] == "10"


def test_initial_state_is_power_on_zero(result) -> None:  # type: ignore[no-untyped-def]
    fsm, an = result.fsm, result.analysis
    assert fsm.initial == "00" and fsm.name(fsm.initial) == "S1"
    assert fsm.reset_state == "10"  # rst=1 presets z1 and resets z2 -> S0
    assert any("power on at 0" in note for note in an.notes)
    assert any("forces state S0" in note for note in an.notes)


def test_reachability_and_graph_properties(result) -> None:  # type: ignore[no-untyped-def]
    an = result.analysis
    assert sorted(result.fsm.name(s) for s in an.reachable) == ["S0", "S1", "S2", "S3"]
    assert an.unreachable == [] and an.dead_ends == [] and an.traps == []
    assert an.strongly_connected
    assert sorted((result.fsm.name(s), x) for s, x in an.self_loops) == [
        ("S0", "0"), ("S1", "0"), ("S2", "0"), ("S3", "0")]


def test_transition_table(result) -> None:  # type: ignore[no-untyped-def]
    an = result.analysis
    rows = {r.name: (r.next, r.outputs) for r in an.rows}
    assert an.columns == ["0", "1"]
    assert rows["S0"] == (["S0", "S1"], ["100"])
    assert rows["S3"] == (["S3", "S0"], ["111"])
    text = result.table_text
    assert "x=0" in text and "→S1" in text


def test_minimal(result, project) -> None:  # type: ignore[no-untyped-def]
    mini = result.minimization
    assert mini.minimal_count == 4 and mini.is_minimal
    only_y = minimize_states(result.fsm, outputs=["y"])  # still 4 classes: distance to S0 differs
    assert only_y.minimal_count == 4
    assert len(only_y.rounds) >= 2


def test_timing_trace_matches_manual(result) -> None:  # type: ignore[no-untyped-def]
    t = result.timing
    # x = 0 1 1 0 1 0 0 from S1: S1 -x0-> S1 -x1-> S2 -x1-> S3 -x0-> S3 -x1-> S0 -x0-> S0 -x0-> S0
    assert t.trace == "S1 S1 S2 S3 S3 S0 S0 S0"
    assert [o[2] for o in t.outputs] == list("11111000")
    assert t.mismatches == []
    text = t.text()
    assert "clk" in text and "state" in text and "trace" in text
    assert "╱" in text and "▔" in text
    ascii_text = t.text(ascii_only=True)
    assert ascii_text.isascii()
    from rich.console import Console

    console = Console(record=True, width=120)
    console.print(t.rich())
    assert "S3" in console.export_text()


def test_dot_edges(result) -> None:  # type: ignore[no-untyped-def]
    dot = result.dot
    assert dot.startswith('digraph "main"')
    for line in ('"S0" [label="S0/100"', '"S0" -> "S1" [label="1"];', '"S1" -> "S2" [label="1"];',
                 '"S2" -> "S3" [label="1"];', '"S3" -> "S0" [label="1"];', '"S0" -> "S0" [label="0"];',
                 '__start -> "S1";'):
        assert line in dot, line
    assert len(edges(result.fsm)) == 8
    graph = result.graph_text()
    assert "S1/001" in graph and "──1──▶ S2" in graph
    svg = to_svg(dot)
    assert svg is None or "<svg" in svg


def test_encodings(result) -> None:  # type: ignore[no-untyped-def]
    encs = {e.name: e for e in result.encodings}
    assert set(encs) == {"current", "binary", "gray", "one-hot"}
    assert encs["one-hot"].flip_flops == 4 and encs["binary"].flip_flops == 2
    assert encs["binary"].codes["00"] == "00"  # initial state gets the power-on code
    for e in encs.values():
        assert e.skipped == ""
        for c in e.costs:
            assert c.gates is not None and c.gates > 0
    d = next(c for c in encs["current"].costs if c.ff == "D")
    assert set(d.equations) >= {"D_z1", "D_z2", "y"}


def test_to_dict_is_json(result) -> None:  # type: ignore[no-untyped-def]
    data = json.loads(json.dumps(result.to_dict()))
    assert data["fsm"]["kind"] == "moore" and data["fsm"]["initial_name"] == "S1"
    assert data["minimization"]["minimal_count"] == 4
    assert data["timing"]["trace"] == "S1 S1 S2 S3 S3 S0 S0 S0"


def test_default_names_are_codes(project) -> None:  # type: ignore[no-untyped-def]
    fsm = extract_fsm(project)
    assert fsm.name("10") == "10"
    assert extract_fsm(project, naming="index").name("10") == "S2"


def test_too_large(project) -> None:  # type: ignore[no-untyped-def]
    res = analyze_sequential(project, max_state_bits=1)
    assert not res.applicable and "too large" in res.reason


def test_combinational_not_applicable() -> None:
    res = analyze_sequential(load_project(GEN / "misc_parts.circ", backend="python"))
    assert not res.applicable and "no flip-flops" in res.reason
    assert res.to_dict()["fsm"] is None


def test_gate_latch_not_applicable() -> None:
    res = analyze_sequential(load_project(GEN / "comb_loop.circ", backend="python"))
    assert not res.applicable and "asynchronous feedback" in res.reason
