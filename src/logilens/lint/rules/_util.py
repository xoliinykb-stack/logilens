"""Helpers shared by several rules."""

from __future__ import annotations

from logilens.core.geometry import Point
from logilens.core.netlist import CircuitNetlist
from logilens.parse.connectivity import index_points, points_on_wire


def wire_point_index(circ: CircuitNetlist) -> tuple[dict[int, list[Point]], dict[int, list[Point]]]:
    """Index of every wire endpoint and port location (for exact on-wire queries)."""
    pts = [w.a for w in circ.wires] + [w.b for w in circ.wires] + [p.loc for c in circ.components for p in c.ports]
    return index_points(pts)


def points_on_wires(circ: CircuitNetlist) -> dict[int, list[Point]]:
    """wire index -> interesting points exactly on its closed segment (no tolerance)."""
    by_x, by_y = wire_point_index(circ)
    return {w.index: list(points_on_wire(w, by_x, by_y, tolerance=0)) for w in circ.wires}
