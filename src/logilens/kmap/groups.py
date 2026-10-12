"""Map cubes to K-map rectangles and build renderer-independent :class:`KMapView` objects.

A cube's cells are (rows matching its row literals) × (columns matching its column literals); both index
sets are split into contiguous runs, so wrap-around and mirror adjacency give several rectangles.
Colors/labels are assigned per distinct cube across *all* outputs, so a shared multi-output term has the
same color on every map.
"""

from __future__ import annotations

from collections.abc import Iterable

from logilens.core.logic_types import (
    BoolFunction,
    Cover,
    Cube,
    Form,
    KMapGroup,
    KMapView,
    MultiFunction,
)
from logilens.kmap.layout import KMapLayout, bars, layout_for, runs
from logilens.logic.truth_table import value_char

PALETTE = ("red", "green", "blue", "magenta", "cyan", "yellow", "bright_red", "bright_green", "bright_blue",
           "bright_magenta", "bright_cyan", "dark_orange", "purple", "spring_green3", "deep_pink3", "gold3")
LABELS = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _matches(code: str, positions: tuple[int, ...], cube: Cube) -> bool:
    text = cube.to_str()
    return all(text[v] in ("-", code[j]) for j, v in enumerate(positions))


def cube_cells(layout: KMapLayout, cube: Cube) -> tuple[list[int], list[int]]:
    """Row indices and column indices covered by the cube."""
    rows = [r for r, code in enumerate(layout.row_codes) if _matches(code, layout.row_vars, cube)]
    cols = [c for c, code in enumerate(layout.col_codes) if _matches(code, layout.col_vars, cube)]
    return rows, cols


def cube_rects(layout: KMapLayout, cube: Cube) -> tuple[tuple[int, int, int, int], ...]:
    """Rectangles ``(row0, col0, row1, col1)`` (inclusive) drawing the cube."""
    rows, cols = cube_cells(layout, cube)
    return tuple((r0, c0, r1, c1) for r0, r1 in runs(rows) for c0, c1 in runs(cols))


def assign_styles(covers: Iterable[Iterable[Cube]]) -> dict[tuple[int, int], tuple[str, str]]:
    """``cube.key -> (label, color)`` in first-appearance order over all outputs."""
    styles: dict[tuple[int, int], tuple[str, str]] = {}
    for cubes in covers:
        for c in cubes:
            if c.key not in styles:
                k = len(styles)
                styles[c.key] = (LABELS[k % len(LABELS)], PALETTE[k % len(PALETTE)])
    return styles


def build_view(
    names: tuple[str, ...],
    output: str,
    f: BoolFunction,
    cubes: Iterable[Cube] = (),
    form: Form = Form.SOP,
    styles: dict[tuple[int, int], tuple[str, str]] | None = None,
) -> KMapView:
    """K-map view of one function with its cover groups (SOP: groups of 1s, POS: groups of 0s)."""
    layout = layout_for(len(names))
    cubes = list(cubes)
    styles = styles or assign_styles([cubes])
    grid = [[layout.minterm(r, c) for c in range(len(layout.col_codes))] for r in range(len(layout.row_codes))]
    values = tuple(tuple(value_char(f, m) for m in row) for row in grid)
    groups = tuple(KMapGroup(c, *styles[c.key], cube_rects(layout, c)) for c in cubes)
    row_bars, col_bars = bars(layout, names)
    return KMapView(output, names, tuple(names[v] for v in layout.row_vars), tuple(names[v] for v in layout.col_vars),
                    layout.row_codes, layout.col_codes, values, tuple(tuple(r) for r in grid), row_bars, col_bars,
                    groups, form)


def views_for_cover(mf: MultiFunction, cover: Cover | None = None) -> list[KMapView]:
    """One view per output; colors consistent across outputs for shared cubes."""
    form = cover.form if cover else Form.SOP
    terms = cover.terms if cover else {}
    styles = assign_styles(terms.get(o, ()) for o in mf.outputs)
    return [build_view(mf.inputs, o, mf.functions[o], terms.get(o, ()), form, styles) for o in mf.outputs]


def cells_of_group(view: KMapView, group: KMapGroup) -> set[tuple[int, int]]:
    """All (row, col) cells inside a group's rectangles."""
    cells: set[tuple[int, int]] = set()
    for r0, c0, r1, c1 in group.rects:
        cells.update((r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1))
    return cells
