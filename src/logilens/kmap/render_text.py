"""Text renderings of a :class:`KMapView`: plain text and a ``rich`` renderable.

Cells show the value (0/1/X) followed by the labels of the groups covering the cell. Variable "bars" (the
textbook bars over the rows/columns where a variable is 1) are drawn as ``━`` above the columns and ``┃``
left of the rows.
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from logilens.core.logic_types import KMapView
from logilens.kmap.groups import cells_of_group
from logilens.logic.expr import cube_to_expr, to_text


def _cell_labels(view: KMapView) -> dict[tuple[int, int], list[tuple[str, str]]]:
    out: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for g in view.groups:
        for cell in sorted(cells_of_group(view, g)):
            out.setdefault(cell, []).append((g.label, g.color))
    return out


def _cell_text(view: KMapView, labels: dict[tuple[int, int], list[tuple[str, str]]], r: int, c: int) -> str:
    marks = "".join(lab for lab, _ in labels.get((r, c), []))
    return view.values[r][c] + (" " + marks if marks else "")


def legend_lines(view: KMapView, style: str = "ascii") -> list[str]:
    """``'1: --101  cd'e'`` style lines for each group."""
    return [f"{g.label}: {g.cube}  {to_text(cube_to_expr(g.cube, view.variables, view.form), style)}"
            for g in view.groups]


def render_plain(view: KMapView) -> str:
    """Plain-text map with bars, codes, values, group labels and a legend."""
    labels = _cell_labels(view)
    nrows, ncols = len(view.row_codes), len(view.col_codes)
    cells = [[_cell_text(view, labels, r, c) for c in range(ncols)] for r in range(nrows)]
    width = max([len(code) for code in view.col_codes] + [len(t) for row in cells for t in row]) + 1
    corner = "".join(view.row_vars) + "\\" + "".join(view.col_vars)
    left = len(view.row_vars) * 2 + max(len(corner), len(view.row_codes[0])) + 1
    lines = [f"{view.output} ({view.form.value})"]
    for var, idx in view.col_bars.items():
        bar = "".join(("━" * (width - 1) + " ") if c in idx else " " * width for c in range(ncols))
        lines.append(f"{var:>{left}} " + bar.rstrip())
    lines.append(" " * (len(view.row_vars) * 2) + corner.ljust(left - len(view.row_vars) * 2) + " "
                 + "".join(code.ljust(width) for code in view.col_codes).rstrip())
    for r in range(nrows):
        marks = "".join(("┃" if r in idx else " ") + " " for idx in view.row_bars.values())
        body = "".join(t.ljust(width) for t in cells[r]).rstrip()
        lines.append(marks + view.row_codes[r].ljust(left - len(marks)) + " " + body)
    lines.append("bars: " + " ".join(view.row_bars) + " = ┃ columns left of the rows (left to right); "
                 + " ".join(view.col_bars) + " = ━ lines above")
    lines += legend_lines(view)
    return "\n".join(lines)


def render_rich(view: KMapView) -> Table:
    """``rich`` table: header = column codes with bars, first column = row codes, colored group labels."""
    labels = _cell_labels(view)
    table = Table(title=f"{view.output} ({view.form.value})", show_lines=True)
    table.add_column("".join(view.row_vars) + "\\" + "".join(view.col_vars), justify="right")
    for c, code in enumerate(view.col_codes):
        bar = " ".join(v for v, idx in view.col_bars.items() if c in idx)
        table.add_column(f"{bar}\n{code}" if bar else f"\n{code}", justify="center")
    for r, code in enumerate(view.row_codes):
        bar = " ".join(v for v, idx in view.row_bars.items() if r in idx)
        row = [Text(f"{bar} {code}".strip())]
        for c in range(len(view.col_codes)):
            cell = Text(view.values[r][c], style="bold")
            for lab, color in labels.get((r, c), []):
                cell.append(lab, style=color)
            row.append(cell)
        table.add_row(*row)
    table.caption = "\n".join(legend_lines(view, "unicode"))
    return table
