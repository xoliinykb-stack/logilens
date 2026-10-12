"""K-map layouts, cube rectangles and text rendering."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from logilens.core.logic_types import Cover, Form, MultiFunction
from logilens.kmap.groups import build_view, cube_rects, views_for_cover
from logilens.kmap.layout import layout_for
from logilens.kmap.render_text import render_plain, render_rich
from logilens.logic.cube import cube_from_str
from logilens.logic.truth_table import function_from_sets, mask_from_minterms


def test_five_var_layout() -> None:
    lay = layout_for(5)
    assert lay.row_codes == ("00", "01", "11", "10")
    assert lay.col_codes == ("000", "010", "110", "100", "101", "111", "011", "001")
    assert lay.row_vars == (0, 1) and lay.col_vars == (2, 3, 4)
    assert lay.minterm(0, 4) == 0b00101
    assert lay.cell_of(0b11001) == (2, 7)
    # bars: c=1 in columns 2..5, d=1 in 1,2,5,6, e=1 in the right half
    assert lay.col_bar(0) == (2, 3, 4, 5)
    assert lay.col_bar(1) == (1, 2, 5, 6)
    assert lay.col_bar(2) == (4, 5, 6, 7)


def test_small_and_six_var_layouts() -> None:
    assert layout_for(2).row_codes == ("0", "1") and layout_for(2).col_codes == ("0", "1")
    assert layout_for(3).col_codes == ("00", "01", "11", "10")
    assert layout_for(4).row_codes == ("00", "01", "11", "10")
    six = layout_for(6)
    assert six.row_codes == six.col_codes == ("000", "010", "110", "100", "101", "111", "011", "001")
    with pytest.raises(ValueError):
        layout_for(7)


def test_cube_rects_wraparound_and_mirror() -> None:
    lay4 = layout_for(4)
    # b'd' = corners: rows 00,10 (0 and 3), cols 00,10 (0 and 3) -> four 1x1 rectangles
    assert sorted(cube_rects(lay4, cube_from_str("-0-0"))) == [(0, 0, 0, 0), (0, 3, 0, 3), (3, 0, 3, 0), (3, 3, 3, 3)]
    lay5 = layout_for(5)
    # c=0, e=1 ('--0-1'): cde in {011, 001} = columns 6, 7 (one run)
    assert cube_rects(lay5, cube_from_str("--0-1")) == ((0, 6, 3, 7),)
    # d=1,e=0 -> columns 010,110 = 1,2
    assert cube_rects(lay5, cube_from_str("---10")) == ((0, 1, 3, 2),)


def test_views_share_colors_and_render() -> None:
    names = ("a", "b", "c")
    f = function_from_sets(3, mask_from_minterms([3, 7, 6]))
    g = function_from_sets(3, mask_from_minterms([3, 7, 1]), mask_from_minterms([5]))
    shared = cube_from_str("-11")
    cover = Cover(Form.SOP, names, {"F": (shared, cube_from_str("11-")), "G": (shared, cube_from_str("0-1"))})
    views = views_for_cover(MultiFunction(names, ("F", "G"), {"F": f, "G": g}), cover)
    color_f = {g_.cube.key: g_.color for g_ in views[0].groups}
    color_g = {g_.cube.key: g_.color for g_ in views[1].groups}
    assert color_f[shared.key] == color_g[shared.key]
    assert len(set(color_f.values()) | set(color_g.values())) == 3
    assert views[1].values[1][1] == "X"  # m5: row a=1, column bc=01
    text = render_plain(views[0])
    assert "a\\bc" in text and "00   01   11   10" in text
    console = Console(file=io.StringIO(), width=100)
    console.print(render_rich(views[0]))
    assert "F (SOP)" in console.file.getvalue()  # type: ignore[attr-defined]


def test_build_view_values() -> None:
    f = function_from_sets(4, mask_from_minterms([0, 15]), mask_from_minterms([5]))
    view = build_view(("a", "b", "c", "d"), "F", f)
    assert view.values[0][0] == "1" and view.values[2][2] == "1" and view.values[1][1] == "X"
    assert view.row_bars == {"a": (2, 3), "b": (1, 2)}
