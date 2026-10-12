"""Project assembly (components, subcircuit ports) and hierarchy flattening.

``build_project`` turns a :class:`RawProject` into a :class:`ProjectNetlist`. Subcircuit instance ports
follow ``SubcircuitFactory.computePorts`` (default or custom ``<appear>``). ``flatten`` expands the
instance tree into one bit-level graph for simulation.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from logilens.core.errors import ParseError
from logilens.core.geometry import Point, rotate
from logilens.core.netlist import (
    CircuitNetlist,
    Component,
    PinInfo,
    Port,
    ProjectNetlist,
    UnsupportedItem,
)
from logilens.parse.attrs import reference_namespace, resolve_attrs
from logilens.parse.circ_xml import RawCircuit, RawComp, RawProject, read_circ
from logilens.parse.component_specs import compute_ports, find_spec, kind_of, offset_bounds
from logilens.parse.connectivity import UnionFind, connect, make_wires

PortOverride = Callable[[str, Component], list[Port] | None]


# ------------------------------------------------------------------ appearance
def _java_round(v: float) -> int:
    return math.floor(v + 0.5)


def parse_appearance(raw: RawCircuit) -> dict[str, Any] | None:
    """Custom ``<appear>`` -> dict(anchor, anchor_facing, ports=[(pin_x, pin_y, px, py)])."""
    if raw.appear is None:
        return None
    anchor = None
    facing = "east"
    ports: list[tuple[int, int, int, int]] = []
    for elt in raw.appear:
        tag = elt.tag
        if tag in ("circ-anchor", "circ-origin", "circ-port"):
            x, y = float(elt.get("x", 0)), float(elt.get("y", 0))
            w, h = float(elt.get("width", 0)), float(elt.get("height", 0))
            center = (_java_round(x + w / 2), _java_round(y + h / 2))
            if tag == "circ-port":
                px, py = (int(s.strip()) for s in elt.get("pin", "0,0").split(","))
                ports.append((px, py, center[0], center[1]))
            else:
                anchor = center
                facing = elt.get("facing", "east")
    return {"anchor": anchor, "anchor_facing": facing, "ports": ports}


def subcircuit_ports(sub: CircuitNetlist, instance_facing: str | None, loc: Point) -> tuple[list[Port], list[int]]:
    """Instance ports of a subcircuit and, in the same order, the pin component ids they map to."""
    pins = [{"x": c.loc.x, "y": c.loc.y, "facing": c.attrs.get("facing", "east"), "output": bool(c.attrs.get("output")),
             "width": int(c.attrs.get("width") or 1), "label": c.label, "id": c.id}
            for c in sub.components if c.kind == "pin"]
    app = sub.appearance
    offs: list[tuple[dict[str, Any], int, int]] = []
    if app is None:
        anchor_facing, offs = reference_namespace()["default_appearance"](pins)
    else:
        anchor_facing = app["anchor_facing"]
        by_loc = {(p["x"], p["y"]): p for p in pins}
        for pin_x, pin_y, px, py in app["ports"]:
            p = by_loc.get((pin_x, pin_y))
            if p is None:
                continue
            if app["anchor"] is not None:
                px, py = px - app["anchor"][0], py - app["anchor"][1]
            offs.append((p, px, py))
    facing = instance_facing or anchor_facing
    placed = []
    for p, ox, oy in offs:
        if facing != anchor_facing:
            ox, oy = rotate(ox, oy, anchor_facing, facing)
        placed.append((ox, oy, p))
    placed.sort(key=lambda t: (t[0], t[1]))  # TreeMap<Location> order: x, then y
    ports = [Port(i, p["label"] or f"pin{Point(p['x'], p['y'])}", "output" if p["output"] else "input",
                  p["width"], loc.offset(ox, oy)) for i, (ox, oy, p) in enumerate(placed)]
    return ports, [p["id"] for _, _, p in placed]


# ------------------------------------------------------------------ building
@dataclass
class _Ctx:
    raw: RawProject
    unsupported: list[UnsupportedItem] = field(default_factory=list)


def _make_component(ctx: _Ctx, circ_name: str, rc: RawComp, idx: int) -> Component:
    kind = kind_of(rc.lib, rc.name)
    spec = find_spec(rc.lib, rc.name)
    if spec is None:
        if rc.lib is not None:
            reason = "unknown library" if rc.lib.startswith(("file#", "jar#", "?")) else "unknown component"
            ctx.unsupported.append(UnsupportedItem("component", rc.name, circ_name, rc.loc, f"{reason} {rc.lib}"))
        return Component(idx, rc.name, rc.lib, rc.loc, dict(rc.attrs), dict(rc.attrs), [], kind,
                         supported=rc.lib is None)
    attrs = resolve_attrs(spec.data, rc.attrs, ctx.raw.source)
    ports = compute_ports(spec, attrs, rc.loc)
    bounds = offset_bounds(rc.name, kind, attrs)
    return Component(idx, rc.name, rc.lib, rc.loc, attrs, dict(rc.attrs), ports, kind,
                     bounds.translate(rc.loc.x, rc.loc.y) if bounds else None)


def _subcircuit_order(raw: RawProject, path: str) -> list[str]:
    deps = {c.name: [k.name for k in c.comps if k.lib is None] for c in raw.circuits}
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(name: str, stack: tuple[str, ...]) -> None:
        if state.get(name) == 2:
            return
        if state.get(name) == 1:
            raise ParseError(f"recursive subcircuit reference: {' -> '.join(stack + (name,))}", path)
        state[name] = 1
        for d in deps.get(name, []):
            if d in deps:
                visit(d, stack + (name,))
        state[name] = 2
        order.append(name)

    for c in raw.circuits:
        visit(c.name, ())
    return order


def build_project(raw: RawProject, port_override: PortOverride | None = None) -> ProjectNetlist:
    """Assemble a :class:`ProjectNetlist`. ``port_override(circuit, comp)`` may replace computed ports."""
    ctx = _Ctx(raw)
    by_name = {c.name: c for c in raw.circuits}
    built: dict[str, CircuitNetlist] = {}
    for name in _subcircuit_order(raw, raw.path):
        rc = by_name[name]
        comps = [_make_component(ctx, name, k, i) for i, k in enumerate(rc.comps)]
        circ = CircuitNetlist(name, comps, make_wires(rc.wires), appearance=parse_appearance(rc))
        for comp in comps:
            if comp.kind == "subcircuit":
                sub = built.get(comp.name)
                if sub is None:
                    ctx.unsupported.append(UnsupportedItem("component", comp.name, name, comp.loc,
                                                           "subcircuit not found in this file"))
                    comp.supported = False
                    continue
                facing = comp.raw_attrs.get("facing")
                comp.ports, pin_ids = subcircuit_ports(sub, facing, comp.loc)
                comp.attrs["_pin_ids"] = pin_ids
            if port_override is not None:
                replaced = port_override(name, comp)
                if replaced is not None:
                    comp.ports = replaced
        built[name] = connect(circ)
    circuits = {c.name: built[c.name] for c in raw.circuits}
    if raw.main not in circuits:
        raise ParseError(f"main circuit {raw.main!r} not found", raw.path)
    proj = ProjectNetlist(raw.path, raw.source, raw.format, raw.main, circuits, dict(raw.options),
                          unsupported=ctx.unsupported)
    if raw.format == "logisim-evolution":
        proj.notes.append("Logisim-evolution file: parsed with 2.7.1 component specs (experimental)")
        proj.unsupported.append(UnsupportedItem("format", raw.source, None, None,
                                                "Logisim-evolution support is experimental"))
    return proj


def parse_project(path: str, port_override: PortOverride | None = None) -> ProjectNetlist:
    """Read and assemble a `.circ` file with the pure-Python parser."""
    return build_project(read_circ(path), port_override)


# ------------------------------------------------------------------ flattening
@dataclass
class FlatComponent:
    """A primitive component instance in the flattened design."""

    path: str  # "main" / "main/sub(200,40)"
    comp: Component
    threads: list[list[int]]  # per port: bit threads (LSB first)
    connected: list[bool]  # per port: Logisim isPortConnected


@dataclass
class FlatCircuit:
    """A whole instance tree as one bit-level graph."""

    top: str
    n_threads: int
    components: list[FlatComponent]
    inputs: list[tuple[PinInfo, list[int]]]
    outputs: list[tuple[PinInfo, list[int]]]
    pulls: dict[int, str] = field(default_factory=dict)  # thread -> pull value '0' | '1' | 'E'
    invalid: set[int] = field(default_factory=set)  # threads of width-conflict nets (always floating)


def flatten(project: ProjectNetlist, circuit: str | None = None) -> FlatCircuit:
    """Expand subcircuit instances; subcircuit pins become plain connections."""
    top = project.circuit(circuit)
    uf = UnionFind()
    comps: list[tuple[str, Component, list[list[tuple[int, int]]], list[bool]]] = []
    counter = [0]
    invalid_keys: list[tuple[int, int]] = []

    def expand(circ: CircuitNetlist, path: str, depth: int) -> tuple[int, CircuitNetlist]:
        if depth > 64:
            raise ParseError(f"subcircuit nesting too deep at {path}")
        base = counter[0]
        counter[0] += circ.n_threads
        invalid_keys.extend((0, base + t) for t in circ.invalid_threads)
        for c in circ.components:
            refs = [(c.id, p.index) for p in c.ports]
            th = [[(0, base + t) for t in circ.port_threads(r)] for r in refs]
            for bits in th:
                for key in bits:
                    uf.add(key)
            if c.kind == "subcircuit" and c.supported:
                sub = project.circuits[c.name]
                sub_base, _ = expand(sub, f"{path}/{c.name}{c.loc}", depth + 1)
                for port_idx, pin_id in enumerate(c.attrs.get("_pin_ids", [])):
                    inner = sub.port_threads((pin_id, 0))
                    for a, b in zip(th[port_idx], inner):
                        uf.union(a, (0, sub_base + b))
                continue
            if c.kind == "pin" and depth > 0:
                continue
            comps.append((path, c, th, [r in circ.connected for r in refs]))
        return base, circ

    expand(top, top.name, 0)
    roots: dict[object, int] = {}

    def tid(key: tuple[int, int]) -> int:
        r = uf.find(key)
        if r not in roots:
            roots[r] = len(roots)
        return roots[r]

    flat = [FlatComponent(p, c, [[tid(k) for k in bits] for bits in th], conn) for p, c, th, conn in comps]
    by_id = {fc.comp.id: fc for fc in flat if fc.path == top.name}
    inputs = [(pin, by_id[pin.comp_id].threads[0]) for pin in top.inputs]
    outputs = [(pin, by_id[pin.comp_id].threads[0]) for pin in top.outputs]
    result = FlatCircuit(top.name, 0, flat, inputs, outputs)
    result.invalid = {tid(k) for k in invalid_keys if k in uf.parent}
    result.n_threads = len(roots)
    for fc in flat:
        if fc.comp.kind == "pull":
            for t in fc.threads[0]:
                result.pulls[t] = str(fc.comp.attrs.get("pull", "0")).upper().replace("X", "E")
    return result
