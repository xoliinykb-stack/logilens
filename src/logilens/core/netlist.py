"""Netlist data model shared by the parser, both backends, the simulator, graph analysis and lint.

Plain dataclasses, no algorithms beyond trivial accessors. A *net* is what Logisim calls a wire bundle:
all wires / ports / tunnels that are electrically one multi-bit node. A *thread* is a single bit of a
net after splitters have been taken into account (``CircuitWires.computeBundleMap``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logilens.core.errors import NotFoundError
from logilens.core.geometry import Bounds, Point

__all__ = [
    "GATE_NAMES",
    "CircuitNetlist",
    "Component",
    "Net",
    "PinInfo",
    "Point",
    "Port",
    "PortRef",
    "ProjectNetlist",
    "UnsupportedItem",
    "Wire",
    "short_name",
]

PortRef = tuple[int, int]
"""(component id, port index) — identifies one port within a circuit."""

GATE_NAMES = frozenset({
    "AND Gate", "OR Gate", "NAND Gate", "NOR Gate", "XOR Gate", "XNOR Gate", "Odd Parity", "Even Parity",
})
"""Multi-input gates built on ``AbstractGate`` (unconnected inputs are skipped)."""


def short_name(name: str) -> str:
    """``"NOR Gate"`` -> ``"NOR"``; other names unchanged."""
    return name.removesuffix(" Gate")


@dataclass(frozen=True)
class Port:
    """One component end (``EndData``). ``direction`` is from the component's point of view."""

    index: int
    name: str
    direction: str  # "input" | "output" | "inout"
    width: int | None  # None = adapts to the attached net
    loc: Point


@dataclass
class Component:
    """A placed component (anything that is not a wire)."""

    id: int
    name: str  # factory name ("NAND Gate", "Pin", ...) or the subcircuit name
    lib: str | None  # library descriptor ("#Gates", ...); None = subcircuit of this file
    loc: Point
    attrs: dict[str, Any]
    raw_attrs: dict[str, str]
    ports: list[Port]
    kind: str = "other"
    bounds: Bounds | None = None
    supported: bool = True  # False = unknown component (no port spec)

    @property
    def label(self) -> str:
        """The ``label`` attribute ('' when absent)."""
        value = self.attrs.get("label", self.raw_attrs.get("label", ""))
        return value if isinstance(value, str) else ""

    @property
    def short(self) -> str:
        return short_name(self.name)

    def describe(self) -> str:
        """Human description like ``"NOR (1170,300)"``."""
        return f"{self.short} {self.loc}"


@dataclass(frozen=True)
class Wire:
    """A wire segment exactly as stored in the file (endpoints normalized so that ``a <= b``)."""

    index: int
    a: Point
    b: Point

    @property
    def vertical(self) -> bool:
        return self.a.x == self.b.x

    @property
    def length(self) -> int:
        return abs(self.b.x - self.a.x) + abs(self.b.y - self.a.y)


@dataclass
class Net:
    """One electrical node (Logisim ``WireBundle``)."""

    id: int
    points: list[Point]
    wires: list[int]
    ports: list[PortRef]
    width: int | None = None
    widths: dict[int, list[PortRef]] = field(default_factory=dict)  # width -> ports declaring it
    tunnels: list[str] = field(default_factory=list)  # tunnel labels merged into this net

    @property
    def width_conflict(self) -> bool:
        return len(self.widths) > 1


@dataclass(frozen=True)
class PinInfo:
    """A circuit I/O pin. ``name`` is the unique analysis name Logisim's ``Analyze.getPinLabels`` assigns."""

    comp_id: int
    label: str
    name: str
    is_input: bool
    width: int
    loc: Point


@dataclass(frozen=True)
class UnsupportedItem:
    """Something the tool cannot fully handle; reported, never silently ignored."""

    kind: str  # "component" | "library" | "simulation" | "appearance" | "format"
    name: str
    circuit: str | None
    loc: Point | None
    reason: str


@dataclass
class CircuitNetlist:
    """Connectivity of one circuit."""

    name: str
    components: list[Component]
    wires: list[Wire]
    nets: list[Net] = field(default_factory=list)
    port_net: dict[PortRef, int] = field(default_factory=dict)
    connected: set[PortRef] = field(default_factory=set)  # Logisim isPortConnected
    threads: dict[tuple[int, int], int] = field(default_factory=dict)  # (net id, bit) -> thread id
    n_threads: int = 0
    invalid_threads: set[int] = field(default_factory=set)  # threads of nets with a width conflict
    inputs: list[PinInfo] = field(default_factory=list)  # Logisim table order: by (y, x)
    outputs: list[PinInfo] = field(default_factory=list)
    appearance: dict[str, Any] | None = None  # custom <appear> data, if any

    def component(self, comp_id: int) -> Component:
        return self.components[comp_id]

    def port(self, ref: PortRef) -> Port:
        return self.components[ref[0]].ports[ref[1]]

    def net_of(self, ref: PortRef) -> Net:
        return self.nets[self.port_net[ref]]

    def port_threads(self, ref: PortRef) -> list[int]:
        """Bit threads of a port, LSB first (width taken from the port, else from its net, else 1)."""
        net = self.net_of(ref)
        width = self.port(ref).width or net.width or 1
        return [self.threads[(net.id, b)] for b in range(width) if (net.id, b) in self.threads]

    def is_connected(self, ref: PortRef) -> bool:
        return ref in self.connected

    def by_kind(self, *kinds: str) -> list[Component]:
        return [c for c in self.components if c.kind in kinds]


@dataclass
class ProjectNetlist:
    """A whole `.circ` project."""

    path: str
    source_version: str
    format: str  # "logisim-2.7.1" | "logisim-evolution"
    main: str
    circuits: dict[str, CircuitNetlist]
    options: dict[str, str] = field(default_factory=dict)
    backend: str = "python"
    unsupported: list[UnsupportedItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def main_circuit(self) -> CircuitNetlist:
        return self.circuits[self.main]

    def circuit(self, name: str | None = None) -> CircuitNetlist:
        """Circuit by name (``None`` = main)."""
        if name is None or name in ("", "-"):
            return self.main_circuit
        if name not in self.circuits:
            raise NotFoundError(name)
        return self.circuits[name]

    @property
    def gate_undefined_error(self) -> bool:
        return self.options.get("gateUndefined", "ignore") == "error"
