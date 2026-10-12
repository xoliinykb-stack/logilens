"""Planar geometry with Logisim 2.7.1 conventions.

x grows east (right), y grows south (down). Directions are the lowercase strings
used in `.circ` files: ``east``, ``west``, ``north``, ``south``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

DIRECTIONS = ("east", "north", "west", "south")
_DEG = {"east": 0, "north": 90, "west": 180, "south": 270}


class Point(NamedTuple):
    """An integer canvas location."""

    x: int
    y: int

    def __str__(self) -> str:
        return f"({self.x},{self.y})"

    def offset(self, dx: int, dy: int) -> Point:
        """Return this point translated by ``(dx, dy)``."""
        return Point(self.x + dx, self.y + dy)


def parse_point(text: str) -> Point:
    """Parse ``"(x,y)"``, ``"x,y"`` or ``"x y"`` like ``Location.parse``."""
    s = text.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    if "," in s:
        xs, ys = s.split(",", 1)
    else:
        xs, ys = s.split(None, 1)
    return Point(int(xs.strip()), int(ys.strip()))


def reverse(direction: str) -> str:
    """Opposite direction."""
    return {"east": "west", "west": "east", "north": "south", "south": "north"}[direction]


def translate(x: int, y: int, direction: str, dist: int, right: int = 0) -> tuple[int, int]:
    """``Location.translate(Direction, dist, right)``."""
    if direction == "west":
        return (x - dist, y - right)
    if direction == "south":
        return (x - right, y + dist)
    if direction == "north":
        return (x + right, y - dist)
    return (x + dist, y + right)


def rotate(x: int, y: int, frm: str, to: str) -> tuple[int, int]:
    """``Location.rotate(from, to, 0, 0)``: rotate an offset counter-clockwise by deg(to)-deg(from)."""
    deg = (_DEG[to] - _DEG[frm]) % 360
    if deg == 90:
        return (y, -x)
    if deg == 180:
        return (-x, -y)
    if deg == 270:
        return (-y, x)
    return (x, y)


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned rectangle ``(x, y, width, height)`` (``data/Bounds``)."""

    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    def translate(self, dx: int, dy: int) -> Bounds:
        return Bounds(self.x + dx, self.y + dy, self.width, self.height)

    def rotate_east_to(self, facing: str) -> Bounds:
        """``Bounds.rotate(EAST, facing, 0, 0)`` for offset bounds defined for an east-facing part."""
        if facing == "east":
            return self
        corners = [rotate(px, py, "east", facing) for px, py in
                   ((self.x, self.y), (self.x2, self.y2))]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        return Bounds(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def contains_strict(self, p: Point) -> bool:
        """True when ``p`` lies strictly inside (not on the border)."""
        return self.x < p.x < self.x2 and self.y < p.y < self.y2

    def segment_crosses_interior(self, a: Point, b: Point) -> bool:
        """True when the axis-parallel segment ``a-b`` has a point strictly inside the rectangle."""
        if a.y == b.y:
            if not self.y < a.y < self.y2:
                return False
            lo, hi = sorted((a.x, b.x))
            return lo < self.x2 and hi > self.x
        if a.x == b.x:
            if not self.x < a.x < self.x2:
                return False
            lo, hi = sorted((a.y, b.y))
            return lo < self.y2 and hi > self.y
        return False


def on_segment(p: Point, a: Point, b: Point, tolerance: int = 0) -> bool:
    """``Wire.contains``: p on the closed axis-parallel segment a-b (perpendicular tolerance)."""
    if a.x == b.x:
        lo, hi = sorted((a.y, b.y))
        return abs(p.x - a.x) <= tolerance and lo <= p.y <= hi
    lo, hi = sorted((a.x, b.x))
    return abs(p.y - a.y) <= tolerance and lo <= p.x <= hi


def strictly_inside_segment(p: Point, a: Point, b: Point) -> bool:
    """p lies on segment a-b but is neither of its endpoints."""
    return p != a and p != b and on_segment(p, a, b)
