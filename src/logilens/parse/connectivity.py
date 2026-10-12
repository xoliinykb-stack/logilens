"""Geometry -> nets, exactly as Logisim 2.7.1 does after loading.

Rules (see docs/logisim-2.7.1-components.md §4):

* Loading runs ``WireRepair``, which splits every wire at every wire endpoint / component port lying on it
  (``Wire.contains``: closed segment, ±2 px perpendicular tolerance). Net effect: a wire connects to every
  wire end and every port anywhere on its closed segment — T-joints connect, mere crossings do not.
* Ports at the same location connect without a wire.
* Tunnels with the same non-empty ``label.trim()`` in one circuit are one net.
* Splitters join individual bits of different nets (threads).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from logilens.core.geometry import Point, on_segment
from logilens.core.netlist import CircuitNetlist, Component, Net, PinInfo, PortRef, Wire

WIRE_TOLERANCE = 2  # Wire.contains perpendicular tolerance


class UnionFind:
    """Minimal union-find over hashable keys."""

    def __init__(self) -> None:
        self.parent: dict[object, object] = {}

    def add(self, key: object) -> None:
        self.parent.setdefault(key, key)

    def find(self, key: object) -> object:
        self.add(key)
        root = key
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[key] != root:
            self.parent[key], key = root, self.parent[key]
        return root

    def union(self, a: object, b: object) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def points_on_wire(wire: Wire, by_x: dict[int, list[Point]], by_y: dict[int, list[Point]],
                   tolerance: int = WIRE_TOLERANCE) -> Iterable[Point]:
    """All indexed points lying on the wire's closed segment."""
    if wire.vertical:
        for x in range(wire.a.x - tolerance, wire.a.x + tolerance + 1):
            for p in by_x.get(x, ()):
                if on_segment(p, wire.a, wire.b, tolerance):
                    yield p
    else:
        for y in range(wire.a.y - tolerance, wire.a.y + tolerance + 1):
            for p in by_y.get(y, ()):
                if on_segment(p, wire.a, wire.b, tolerance):
                    yield p


def index_points(points: Iterable[Point]) -> tuple[dict[int, list[Point]], dict[int, list[Point]]]:
    by_x: dict[int, list[Point]] = defaultdict(list)
    by_y: dict[int, list[Point]] = defaultdict(list)
    for p in set(points):
        by_x[p.x].append(p)
        by_y[p.y].append(p)
    return by_x, by_y


def make_wires(raw: Iterable[tuple[Point, Point]]) -> list[Wire]:
    """Normalise endpoints (e0 < e1), drop zero-length wires and exact duplicates (``Circuit.mutatorAdd``)."""
    seen: set[tuple[Point, Point]] = set()
    out: list[Wire] = []
    for a, b in raw:
        if a == b:
            continue
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        seen.add(key)
        out.append(Wire(len(out), key[0], key[1]))
    return out


def _union_geometry(circ: CircuitNetlist, uf: UnionFind) -> None:
    port_points = [p.loc for c in circ.components for p in c.ports]
    wire_points = [w.a for w in circ.wires] + [w.b for w in circ.wires]
    by_x, by_y = index_points(port_points + wire_points)
    for w in circ.wires:
        uf.add(("w", w.index))
        for p in points_on_wire(w, by_x, by_y):
            uf.union(("w", w.index), p)
    for c in circ.components:
        for port in c.ports:
            uf.add(port.loc)
    tunnels: dict[str, list[Point]] = defaultdict(list)
    for c in circ.components:
        if c.kind == "tunnel" and c.label.strip():
            tunnels[c.label.strip()].append(c.ports[0].loc)
    for locs in tunnels.values():
        for p in locs[1:]:
            uf.union(locs[0], p)


def _connected_ports(circ: CircuitNetlist) -> set[PortRef]:
    """Logisim ``isPortConnected``: another wire or another component's end at the exact port location."""
    by_loc: dict[Point, set[int]] = defaultdict(set)
    for c in circ.components:
        for p in c.ports:
            by_loc[p.loc].add(c.id)
    wire_pts = [p for c in circ.components for p in (q.loc for q in c.ports)]
    by_x, by_y = index_points(wire_pts)
    on_wire: set[Point] = set()
    for w in circ.wires:
        on_wire.update(points_on_wire(w, by_x, by_y))
    out: set[PortRef] = set()
    for c in circ.components:
        for p in c.ports:
            if p.loc in on_wire or len(by_loc[p.loc] - {c.id}) > 0:
                out.add((c.id, p.index))
    return out


def _build_nets(circ: CircuitNetlist, uf: UnionFind) -> None:
    groups: dict[object, Net] = {}
    order: list[object] = []

    def net_for(key: object) -> Net:
        root = uf.find(key)
        if root not in groups:
            groups[root] = Net(id=-1, points=[], wires=[], ports=[])
            order.append(root)
        return groups[root]

    for w in circ.wires:
        net = net_for(("w", w.index))
        net.wires.append(w.index)
        net.points.extend((w.a, w.b))
    for c in circ.components:
        for p in c.ports:
            net = net_for(p.loc)
            net.ports.append((c.id, p.index))
            net.points.append(p.loc)
            if c.kind == "tunnel" and c.label.strip() and c.label.strip() not in net.tunnels:
                net.tunnels.append(c.label.strip())
    nets = sorted(groups.values(), key=lambda n: min(n.points))
    for i, net in enumerate(nets):
        net.id = i
        net.points = sorted(set(net.points))
        for ref in net.ports:
            circ.port_net[ref] = i
            width = circ.port(ref).width
            if width:
                net.widths.setdefault(width, []).append(ref)
        if net.widths:
            net.width = max(net.widths, key=lambda w: (len(net.widths[w]), -w))
    circ.nets = nets


def _build_threads(circ: CircuitNetlist) -> None:
    """Bit threads: (net, bit) keys united through splitters (``computeBundleMap``)."""
    uf = UnionFind()
    for net in circ.nets:
        bits = max(net.widths) if net.width_conflict else (net.width or 1)
        for b in range(bits):
            uf.add((net.id, b))
    invalid = {n.id for n in circ.nets if n.width_conflict}
    for c in circ.components:
        if c.kind != "splitter":
            continue
        bit_end = reference_bit_end(c)
        combined = circ.port_net[(c.id, 0)]
        if combined in invalid:
            continue
        rank: dict[int, int] = defaultdict(int)
        for i, end in enumerate(bit_end):
            if end <= 0:
                continue
            target = circ.port_net[(c.id, end)]
            if target not in invalid:
                uf.union((combined, i), (target, rank[end]))
            rank[end] += 1
    roots: dict[object, int] = {}
    for key in sorted(uf.parent, key=lambda k: k):  # deterministic numbering
        root = uf.find(key)
        if root not in roots:
            roots[root] = len(roots)
        circ.threads[key] = roots[root]  # type: ignore[index]
    circ.n_threads = len(roots)
    circ.invalid_threads = {t for (net, _), t in circ.threads.items() if net in invalid}


def reference_bit_end(comp: Component) -> list[int]:
    """Splitter ``bit_end`` table (0 = not routed, k = split end k, 1-based)."""
    from logilens.parse.attrs import reference_namespace

    return list(reference_namespace()["splitter_bit_end"](dict(comp.attrs)))


def to_valid_label(label: str | None) -> str | None:
    """``Analyze.toValidLabel``: keep identifier characters, title-case words after whitespace."""
    if label is None:
        return None
    ret: list[str] = []
    end: list[str] = []
    after_ws = False
    for ch in label:
        if ch.isidentifier() or ch == "$":
            if after_ws:
                ch = ch.title()
                after_ws = False
            ret.append(ch)
        elif ("a" + ch).isidentifier():
            (ret if ret else end).append(ch)
            after_ws = False
        elif ch.isspace():
            after_ws = True
    if end and ret:
        ret.extend(end)
    return "".join(ret) or None


def name_pins(circ: CircuitNetlist) -> None:
    """Fill ``inputs``/``outputs`` in Logisim order with ``Analyze.getPinLabels`` names."""
    pins = sorted((c for c in circ.components if c.kind == "pin"), key=lambda c: (c.loc.y, c.loc.x, c.id))
    names: dict[int, str] = {}
    taken: set[str] = set()
    for c in pins:
        label = to_valid_label(c.label)
        if label is None:
            continue
        if label in taken:
            i = 2
            while f"{label}{i}" in taken:
                i += 1
            label = f"{label}{i}"
        names[c.id] = label
        taken.add(label)
    for c in pins:
        if c.id in names:
            continue
        defaults = "x,y,z,u,v,w,s,t" if c.attrs.get("output") else "a,b,c,d,e,f,g,h"
        label = next((o for o in defaults.split(",") if o not in taken), None)
        if label is None:
            i = 1
            while True:
                i += 1
                label = f"x{i}"
                if label not in taken:
                    break
        taken.add(label)
        names[c.id] = label
    circ.inputs, circ.outputs = [], []
    for c in pins:
        info = PinInfo(c.id, c.label, names[c.id], not c.attrs.get("output"), int(c.attrs.get("width") or 1), c.loc)
        (circ.inputs if info.is_input else circ.outputs).append(info)


def connect(circ: CircuitNetlist) -> CircuitNetlist:
    """Compute nets, port connectivity, bit threads and pin names in place; returns ``circ``."""
    uf = UnionFind()
    _union_geometry(circ, uf)
    _build_nets(circ, uf)
    circ.connected = _connected_ports(circ)
    _build_threads(circ)
    name_pins(circ)
    return circ
