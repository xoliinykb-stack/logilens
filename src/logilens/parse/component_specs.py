"""Component spec lookup: (library, name) + attributes -> ports, kind and body bounds.

Port positions come from the executable reference routines embedded in ``components_271.json``
(a direct port of the Logisim 2.7.1 Java code, validated against Logisim's own ``getEnds()``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from logilens.core.geometry import Bounds, Point
from logilens.core.netlist import GATE_NAMES, Port
from logilens.parse.attrs import load_spec, reference_namespace

_KIND = {
    "NOT Gate": "not", "Buffer": "buffer",
    "Controlled Buffer": "controlled", "Controlled Inverter": "controlled",
    "Pin": "pin", "Probe": "probe", "Tunnel": "tunnel", "Splitter": "splitter",
    "Pull Resistor": "pull", "Clock": "clock", "Constant": "constant", "Power": "constant",
    "Ground": "constant", "Transistor": "switch", "Transmission Gate": "switch", "Bit Extender": "wiring_logic",
    "Multiplexer": "plexer", "Demultiplexer": "plexer", "Decoder": "plexer", "Priority Encoder": "plexer",
    "BitSelector": "plexer",
    "D Flip-Flop": "flipflop", "T Flip-Flop": "flipflop", "J-K Flip-Flop": "flipflop", "S-R Flip-Flop": "flipflop",
    "Register": "register", "Counter": "register", "Shift Register": "register", "Random": "register",
    "RAM": "memory", "ROM": "memory", "Text": "text",
}
_LIB_KIND = {"#Arithmetic": "arith", "#I/O": "io"}

STATE_KINDS = frozenset({"flipflop", "register", "memory"})
"""Kinds that hold state (cut points for combinational analysis)."""


@dataclass(frozen=True)
class ComponentSpec:
    library: str
    name: str
    data: Mapping[str, Any]


@lru_cache(maxsize=1)
def _index() -> dict[tuple[str, str], ComponentSpec]:
    return {(c["library"], c["name"]): ComponentSpec(c["library"], c["name"], c) for c in load_spec()["components"]}


def find_spec(lib: str | None, name: str) -> ComponentSpec | None:
    """Spec of a built-in component, ``None`` when unknown (or a subcircuit)."""
    if lib is None:
        return None
    return _index().get((lib, name))


def kind_of(lib: str | None, name: str) -> str:
    """Coarse category used by simulator, graph and lint."""
    if lib is None:
        return "subcircuit"
    if name in GATE_NAMES:
        return "gate"
    if name in _KIND:
        return _KIND[name]
    if (lib, name) in _index():
        return _LIB_KIND.get(lib, "other")
    return "unknown"


def compute_ports(spec: ComponentSpec, attrs: Mapping[str, Any], loc: Point) -> list[Port]:
    """Absolute ports in Logisim port-index order."""
    algo = spec.data["ports_algorithm"]
    fn = reference_namespace()[algo["function"]]
    raw = fn(dict(attrs), **algo.get("kwargs", {}))
    return [Port(i, p["name"], p["dir"], p["width"], loc.offset(p["dx"], p["dy"])) for i, p in enumerate(raw)]


def _gate_bounds(name: str, a: Mapping[str, Any]) -> Bounds:
    bonus = 10 if name in ("XOR Gate", "XNOR Gate") else 0
    neg_out = name in ("NAND Gate", "NOR Gate", "XNOR Gate")
    inputs = int(a["inputs"])
    if inputs % 2 == 0:
        inputs += 1
    size = int(a["size"])
    width = size + bonus + (10 if neg_out else 0)
    if any(a.get(f"negate{i}") for i in range(int(a["inputs"]))):
        width += 10
    height = max(10 * inputs, size)
    facing = a["facing"]
    half = int(height / 2)
    if facing == "south":
        return Bounds(-half, -width, height, width)
    if facing == "north":
        return Bounds(-half, 0, height, width)
    if facing == "west":
        return Bounds(0, -half, width, height)
    return Bounds(-width, -half, width, height)


def _small_bounds(length: int, facing: str, half: int = 9) -> Bounds:
    """East-facing body (-length, -half, length, 2*half) rotated like the Java per-facing tables."""
    if facing == "south":
        return Bounds(-half, -length, 2 * half, length)
    if facing == "north":
        return Bounds(-half, 0, 2 * half, length)
    if facing == "west":
        return Bounds(0, -half, length, 2 * half)
    return Bounds(-length, -half, length, 2 * half)


def offset_bounds(name: str, kind: str, a: Mapping[str, Any]) -> Bounds | None:
    """Body rectangle relative to ``loc`` (``getOffsetBounds``) for parts where a wire crossing it is suspect."""
    if kind == "gate":
        return _gate_bounds(name, a)
    if name == "NOT Gate":
        return _small_bounds(20 if a.get("size") == "20" else 30, a["facing"])
    if name == "Buffer":
        return _small_bounds(20, a["facing"])
    if kind == "controlled":
        w = 30 if name == "Controlled Inverter" and a.get("size") != "20" else 20
        return _small_bounds(w, a["facing"], half=10)
    if kind == "flipflop":
        return Bounds(-40, -10, 40, 40)
    if name in ("Register", "Counter"):
        return Bounds(-30, -20, 30, 40)
    if kind == "arith" and name not in ("BitAdder", "BitFinder", "Negator"):
        return Bounds(-40, -20, 40, 40)
    return None
