"""Cross-validation of the Python backend against Logisim.

Checks per circuit: same components (name, loc); identical port coordinates (Python spec vs Logisim
``getEnds()``); same pins (loc, direction, label); the same partition of ports into nets (Python geometry on the
raw XML wires vs Logisim's repaired wires); identical truth tables for every circuit with pins and few inputs.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from logilens.backends.java.backend import JavaBackend, java_ports
from logilens.backends.python_backend import PythonBackend
from logilens.core.errors import UnsupportedError
from logilens.core.geometry import Point
from logilens.core.netlist import CircuitNetlist, Component, ProjectNetlist
from logilens.parse.connectivity import connect, make_wires


@dataclass
class CircuitCrossval:
    name: str
    components: int = 0
    ports_compared: int = 0
    component_mismatches: list[str] = field(default_factory=list)
    port_mismatches: list[str] = field(default_factory=list)
    pin_mismatches: list[str] = field(default_factory=list)
    net_mismatches: list[str] = field(default_factory=list)
    table_rows: int | None = None
    table_mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.component_mismatches or self.port_mismatches or self.pin_mismatches
                    or self.net_mismatches or self.table_mismatches)


@dataclass
class CrossvalReport:
    path: str
    circuits: list[CircuitCrossval]
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.circuits)


def _java_circuit(py: CircuitNetlist, dump_circ: dict[str, Any]) -> CircuitNetlist:
    """The same circuit rebuilt from Logisim's own component ends and (repaired) wires."""
    comps: list[Component] = []
    templates = {(c.name, c.loc): c for c in py.components}
    for i, entry in enumerate(dump_circ["components"]):
        loc = Point(*entry["loc"])
        tpl = templates.get((entry["name"], loc))
        attrs: dict[str, Any] = dict(tpl.attrs) if tpl else {"label": entry["attrs"].get("label", "")}
        kind = tpl.kind if tpl else "other"
        ports = java_ports(entry, tpl.ports if tpl else [])
        comps.append(Component(i, entry["name"], tpl.lib if tpl else "?", loc, attrs, entry["attrs"], ports, kind))
    wires = make_wires((Point(w[0], w[1]), Point(w[2], w[3])) for w in dump_circ["wires"])
    return connect(CircuitNetlist(py.name, comps, wires))


def _port_keys(circ: CircuitNetlist) -> dict[int, frozenset[tuple[str, Point, int]]]:
    out: dict[int, set[tuple[str, Point, int]]] = {}
    for net in circ.nets:
        for cid, idx in net.ports:
            c = circ.components[cid]
            if c.kind != "text":
                out.setdefault(net.id, set()).add((c.name, c.loc, idx))
    return {k: frozenset(v) for k, v in out.items()}


def _compare_structure(res: CircuitCrossval, py: CircuitNetlist, jv: CircuitNetlist) -> None:
    pyc = Counter((c.name, c.loc) for c in py.components)
    jvc = Counter((c.name, c.loc) for c in jv.components)
    res.components = sum(jvc.values())
    for key in sorted(set(pyc) | set(jvc), key=str):
        if pyc[key] != jvc[key]:
            res.component_mismatches.append(f"{key[0]} {key[1]}: python {pyc[key]} vs logisim {jvc[key]}")
    by_key = {(c.name, c.loc): c for c in jv.components}
    for c in py.components:
        other = by_key.get((c.name, c.loc))
        if other is None:
            continue
        a = [p.loc for p in c.ports]
        b = [p.loc for p in other.ports]
        res.ports_compared += len(b)
        if a != b:
            res.port_mismatches.append(f"{c.describe()}: python {[str(p) for p in a]} vs logisim {[str(p) for p in b]}")
    pins = lambda n: sorted((p.loc, p.is_input, p.name, p.width) for p in n.inputs + n.outputs)
    if pins(py) != pins(jv):
        res.pin_mismatches.append(f"python {pins(py)} vs logisim {pins(jv)}")
    pn = set(_port_keys(py).values())
    jn = set(_port_keys(jv).values())
    for net in sorted(pn - jn, key=lambda s: sorted(map(str, s)))[:20]:
        res.net_mismatches.append("python-only net: " + ", ".join(sorted(f"{n} {p}#{i}" for n, p, i in net)))
    for net in sorted(jn - pn, key=lambda s: sorted(map(str, s)))[:20]:
        res.net_mismatches.append("logisim-only net: " + ", ".join(sorted(f"{n} {p}#{i}" for n, p, i in net)))


def _compare_tables(res: CircuitCrossval, project: ProjectNetlist, java: JavaBackend, max_bits: int) -> None:
    try:
        tp = PythonBackend().truth_table(project, res.name, max_bits)
    except UnsupportedError as exc:
        res.table_mismatches.append(f"skipped: {exc}")
        return
    tj = java.truth_table(project, res.name, max_bits)
    res.table_rows = len(tj["rows"])
    if [c["name"] for c in tp["inputs"]] != [c["name"] for c in tj["inputs"]]:
        res.table_mismatches.append("input columns differ")
    if [c["name"] for c in tp["outputs"]] != [c["name"] for c in tj["outputs"]]:
        res.table_mismatches.append("output columns differ")
    for a, b in zip(tp["rows"], tj["rows"]):
        if a["in"] != b["in"] or a["out"] != b["out"]:
            res.table_mismatches.append(f"in {' '.join(b['in'])}: python {a['out']} vs logisim {b['out']}")
            if len(res.table_mismatches) >= 20:
                break


def crossval(path: str | os.PathLike[str], jar: str | os.PathLike[str] | None = None, tables: bool = True,
             max_bits: int = 16) -> CrossvalReport:
    """Compare the Python backend with Logisim for one file. Requires Java + jar (raises BackendError)."""
    java = JavaBackend(jar)
    dump = java.bridge.dump(str(path))
    project = PythonBackend().load(str(path))
    report = CrossvalReport(str(path), [])
    by_name = {c["name"]: c for c in dump["circuits"]}
    for name, py in project.circuits.items():
        res = CircuitCrossval(name)
        report.circuits.append(res)
        if name not in by_name:
            res.component_mismatches.append("circuit missing in Logisim dump")
            continue
        _compare_structure(res, py, _java_circuit(py, by_name[name]))
        if tables and py.inputs + py.outputs and py.outputs:
            _compare_tables(res, project, java, max_bits)
    report.notes.extend(project.notes)
    return report
