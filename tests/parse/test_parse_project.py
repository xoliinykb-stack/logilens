"""Parser: XML reading, attribute defaults, port geometry, connectivity semantics, pin naming."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from logilens.core.errors import ParseError
from logilens.core.geometry import Point
from logilens.parse import parse_project
from logilens.parse.circ_xml import read_circ
from logilens.parse.connectivity import to_valid_label
from logilens.parse.hierarchy import build_project

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ALL = sorted(FIXTURES.glob("*.circ")) + sorted((FIXTURES / "gen").glob("*.circ"))


def _project_from_xml(tmp_path: Path, body: str, source: str = "2.7.1", options: str = ""):
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><project source="{source}" version="1.0">'
           '<lib desc="#Wiring" name="0"/><lib desc="#Gates" name="1"/><lib desc="#Plexers" name="2"/>'
           f'<main name="main"/><options>{options}</options><circuit name="main">{body}</circuit></project>')
    path = tmp_path / "t.circ"
    path.write_text(xml)
    return parse_project(str(path))


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_every_fixture_parses(path: Path) -> None:
    project = parse_project(str(path))
    assert project.main in project.circuits
    assert project.format == "logisim-2.7.1"
    for circ in project.circuits.values():
        for c in circ.components:
            for p in c.ports:
                assert (c.id, p.index) in circ.port_net


def test_converter_inventory() -> None:
    circ = parse_project(str(FIXTURES / "converter_nand_nor.circ")).main_circuit
    counts = Counter(c.name for c in circ.components)
    assert counts["NAND Gate"] == 19 and counts["NOR Gate"] == 18
    assert [p.name for p in circ.inputs] == list("abcde")
    assert [p.name for p in circ.outputs] == ["A_N", "B_N", "C_N", "D_N", "A_R", "B_R", "C_R", "D_R"]


def test_draft_duplicate_inputs_and_unlabeled_outputs() -> None:
    circ = parse_project(str(FIXTURES / "converter_draft.circ")).main_circuit
    assert Counter(c.name for c in circ.components)["NOT Gate"] == 10
    # Logisim's Analyze.getPinLabels renames duplicates and names unlabeled pins
    assert [p.name for p in circ.inputs] == ["a", "b", "c", "d", "e", "a2", "b2", "c2", "d2", "e2"]
    assert [p.label for p in circ.inputs] == list("abcde") * 2
    assert [p.name for p in circ.outputs] == ["x", "y", "z", "u", "v", "w", "s", "t"]


def test_draft_unconnected_nor_input() -> None:
    circ = parse_project(str(FIXTURES / "converter_draft.circ")).main_circuit
    loose = [(c.describe(), p.loc) for c in circ.components if c.kind == "gate"
             for p in c.ports[1:] if (c.id, p.index) not in circ.connected]
    assert loose == [("NOR (480,750)", Point(420, 770))]
    nor = next(c for c in circ.components if c.loc == Point(480, 750))
    assert nor.attrs["inputs"] == 3


def test_sample_four_loose_inputs() -> None:
    circ = parse_project(str(FIXTURES / "sample_bcd_excess3.circ")).main_circuit
    loose = sorted(p.loc for c in circ.components if c.kind == "gate"
                   for p in c.ports[1:] if (c.id, p.index) not in circ.connected)
    assert loose == [Point(240, 330), Point(240, 610), Point(410, 680), Point(570, 1170)]
    wire_ends = {pt for w in circ.wires for pt in (w.a, w.b)}
    # the stale wires end 10 px (one grid step) short of each of them
    assert {Point(230, 330), Point(230, 610), Point(400, 680), Point(560, 1170)} <= wire_ends


def test_defaults_when_attributes_missing(tmp_path: Path) -> None:
    proj = _project_from_xml(tmp_path, '<comp lib="1" loc="(200,100)" name="NAND Gate"/>'
                                       '<comp lib="1" loc="(200,300)" name="NOR Gate"><a name="inputs" val="2"/>'
                                       '<a name="negate0" val="true"/></comp>')
    nand, nor = proj.main_circuit.components
    assert nand.attrs["inputs"] == 5 and nand.attrs["size"] == "50"
    assert [p.loc for p in nand.ports[1:]] == [Point(140, 80 + 10 * i) for i in range(5)]
    assert nor.ports[1].loc == Point(130, 280)  # negated input moves one bubble further out
    assert nor.ports[2].loc == Point(140, 320)


def test_version_dependent_defaults(tmp_path: Path) -> None:
    old = _project_from_xml(tmp_path, '<comp lib="2" loc="(200,100)" name="Multiplexer"/>', source="2.6.0")
    new = _project_from_xml(tmp_path, '<comp lib="2" loc="(200,100)" name="Multiplexer"/>', source="2.7.1")
    assert old.main_circuit.components[0].attrs["enable"] is False
    assert new.main_circuit.components[0].attrs["enable"] is True
    assert len(new.main_circuit.components[0].ports) == len(old.main_circuit.components[0].ports) + 1


def test_t_junction_connects_but_crossing_does_not(tmp_path: Path) -> None:
    body = ('<wire from="(100,100)" to="(300,100)"/>'      # horizontal
            '<wire from="(200,100)" to="(200,200)"/>'      # T: end on the middle of the first wire
            '<wire from="(250,50)" to="(250,150)"/>')      # crosses the first wire: no connection
    circ = _project_from_xml(tmp_path, body).main_circuit
    nets = {frozenset(n.wires) for n in circ.nets}
    assert frozenset({0, 1}) in nets and frozenset({2}) in nets


def test_coincident_ports_and_tunnels_connect(tmp_path: Path) -> None:
    body = ('<comp lib="0" loc="(100,100)" name="Pin"><a name="label" val="a"/></comp>'
            '<comp lib="1" loc="(130,100)" name="NOT Gate"/>'          # input (100,100) == pin port
            '<comp lib="0" loc="(130,100)" name="Tunnel"><a name="label" val="t"/></comp>'
            '<comp lib="0" loc="(400,100)" name="Tunnel"><a name="label" val=" t "/></comp>'
            '<comp lib="0" loc="(400,100)" name="Pin"><a name="output" val="true"/>'
            '<a name="label" val="y"/></comp>')
    circ = _project_from_xml(tmp_path, body).main_circuit
    pin_a, not_g, _, _, pin_y = circ.components
    assert circ.port_net[(pin_a.id, 0)] == circ.port_net[(not_g.id, 1)]
    assert (not_g.id, 1) in circ.connected
    assert circ.port_net[(not_g.id, 0)] == circ.port_net[(pin_y.id, 0)]


def test_zero_length_and_duplicate_wires_dropped(tmp_path: Path) -> None:
    circ = _project_from_xml(tmp_path, '<wire from="(10,10)" to="(10,10)"/><wire from="(10,10)" to="(50,10)"/>'
                                       '<wire from="(50,10)" to="(10,10)"/>').main_circuit
    assert len(circ.wires) == 1


def test_unknown_component_reported(tmp_path: Path) -> None:
    proj = _project_from_xml(tmp_path, '<comp lib="1" loc="(10,10)" name="Quantum Gate"/>')
    assert [u.name for u in proj.unsupported] == ["Quantum Gate"]
    assert proj.unsupported[0].loc == Point(10, 10)


def test_bad_xml_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.circ"
    path.write_text("<project><circuit")
    with pytest.raises(ParseError):
        read_circ(path)


def test_recursive_subcircuit_rejected(tmp_path: Path) -> None:
    xml = ('<project source="2.7.1" version="1.0"><main name="a"/>'
           '<circuit name="a"><comp loc="(10,10)" name="b"/></circuit>'
           '<circuit name="b"><comp loc="(10,10)" name="a"/></circuit></project>')
    path = tmp_path / "r.circ"
    path.write_text(xml)
    with pytest.raises(ParseError):
        build_project(read_circ(path))


def test_subcircuit_ports_default_appearance() -> None:
    proj = parse_project(str(FIXTURES / "gen" / "subcircuit.circ"))
    main = proj.main_circuit
    east = next(c for c in main.components if c.name == "half" and c.loc == Point(400, 200))
    west = next(c for c in main.components if c.name == "half" and c.loc == Point(700, 400))
    assert sorted(p.loc for p in east.ports) == [Point(370, 200), Point(370, 210), Point(400, 200), Point(400, 210)]
    assert sorted(p.loc for p in west.ports) == [Point(700, 390), Point(700, 400), Point(730, 390), Point(730, 400)]


def test_splitter_threads() -> None:
    circ = parse_project(str(FIXTURES / "gen" / "misc_parts.circ")).main_circuit
    sp = next(c for c in circ.components if c.kind == "splitter")
    combined = circ.port_threads((sp.id, 0))
    assert len(combined) == 2
    assert circ.port_threads((sp.id, 1)) == combined[:1]
    assert circ.port_threads((sp.id, 2)) == combined[1:]


@pytest.mark.parametrize(("raw", "valid"), [("A_D", "A_D"), ("a b", "aB"), ("1x", "x1"), ("  ", None), ("č", "č")])
def test_to_valid_label(raw: str, valid: str | None) -> None:
    assert to_valid_label(raw) == valid
