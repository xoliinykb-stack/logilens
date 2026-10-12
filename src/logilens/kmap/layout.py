"""Karnaugh-map layouts (2–6 variables) in the textbook convention.

* 2 vars: rows ``a``, columns ``b``; 3 vars: rows ``a``, columns ``bc`` Gray (00, 01, 11, 10);
* 4 vars: rows ``ab``, columns ``cd`` Gray;
* 5 vars: rows ``ab`` Gray, columns ``cde = 000, 010, 110, 100, 101, 111, 011, 001`` (two mirrored 4-column
  halves, e = 0 left, e = 1 right; mirror-image columns are adjacent);
* 6 vars: rows ``abc`` and columns ``def`` both mirrored like the 5-variable columns.
"""

from __future__ import annotations

from dataclasses import dataclass

GRAY1 = ("0", "1")
GRAY2 = ("00", "01", "11", "10")
MIRROR3 = ("000", "010", "110", "100", "101", "111", "011", "001")
_SPLIT = {2: (1, 1), 3: (1, 2), 4: (2, 2), 5: (2, 3), 6: (3, 3)}


def axis_codes(k: int) -> tuple[str, ...]:
    """Axis code order for ``k`` variables on one axis."""
    return {1: GRAY1, 2: GRAY2, 3: MIRROR3}[k]


@dataclass(frozen=True)
class KMapLayout:
    """Geometry of a map: input indices on each axis (MSB-first) and their code order."""

    n: int
    row_vars: tuple[int, ...]
    col_vars: tuple[int, ...]
    row_codes: tuple[str, ...]
    col_codes: tuple[str, ...]

    def minterm(self, r: int, c: int) -> int:
        """Minterm in cell (r, c) (row variables are the leading inputs)."""
        return int(self.row_codes[r] + self.col_codes[c], 2)

    def cell_of(self, m: int) -> tuple[int, int]:
        """Cell (r, c) of minterm ``m``."""
        bits = format(m, f"0{self.n}b")
        k = len(self.row_vars)
        return self.row_codes.index(bits[:k]), self.col_codes.index(bits[k:])

    def row_bar(self, j: int) -> tuple[int, ...]:
        """Row indices where the ``j``-th row variable equals 1."""
        return tuple(r for r, code in enumerate(self.row_codes) if code[j] == "1")

    def col_bar(self, j: int) -> tuple[int, ...]:
        """Column indices where the ``j``-th column variable equals 1."""
        return tuple(c for c, code in enumerate(self.col_codes) if code[j] == "1")


def layout_for(n: int) -> KMapLayout:
    """Textbook layout for ``n`` in 2..6 variables."""
    if n not in _SPLIT:
        raise ValueError(f"K-maps are supported for 2..6 variables, not {n}")
    rk, ck = _SPLIT[n]
    return KMapLayout(n, tuple(range(rk)), tuple(range(rk, n)), axis_codes(rk), axis_codes(ck))


def runs(indices: tuple[int, ...] | list[int]) -> list[tuple[int, int]]:
    """Contiguous runs of sorted indices as inclusive ``(start, end)`` spans."""
    out: list[tuple[int, int]] = []
    for i in sorted(indices):
        if out and i == out[-1][1] + 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def bars(layout: KMapLayout, names: tuple[str, ...]) -> tuple[dict[str, tuple[int, ...]], dict[str, tuple[int, ...]]]:
    """``(row_bars, col_bars)``: for each variable the row/column indices where it equals 1."""
    row = {names[v]: layout.row_bar(j) for j, v in enumerate(layout.row_vars)}
    col = {names[v]: layout.col_bar(j) for j, v in enumerate(layout.col_vars)}
    return row, col
