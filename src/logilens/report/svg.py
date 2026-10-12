"""Inline SVG pictures for the HTML report: Karnaugh maps and timing diagrams.

Colors come from CSS custom properties (``--fg``, ``--muted``, ``--line``, ``--card``) so the
pictures follow the page's light/dark theme; group colors are fixed hues that read on both.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from typing import Any

from logilens.core.logic_types import KMapView
from logilens.kmap.render_text import legend_lines

GROUP_COLORS = {  # muted, print-friendly hues (Tableau 10 family) that stay apart on light and dark paper
    "red": "#d62728", "green": "#2ca02c", "blue": "#1f77b4", "magenta": "#c2459b", "cyan": "#17a2b8",
    "yellow": "#bcbd22", "bright_red": "#e45756", "bright_green": "#54a24b", "bright_blue": "#4c78a8",
    "bright_magenta": "#b279a2", "bright_cyan": "#72b7b2", "dark_orange": "#ff7f0e", "purple": "#9467bd",
    "spring_green3": "#2f9e8f", "deep_pink3": "#d6336c", "gold3": "#b8860b",
}
FALLBACK_COLOR = "#8c564b"
FONT = 'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"'


def group_color(name: str) -> str:
    return GROUP_COLORS.get(name, FALLBACK_COLOR)


def _runs(indices: Sequence[int]) -> list[tuple[int, int]]:
    """Contiguous runs of sorted indices: (first, last)."""
    out: list[tuple[int, int]] = []
    for i in sorted(indices):
        if out and i == out[-1][1] + 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def kmap_svg(view: KMapView, cell: int = 46) -> str:
    """One K-map: Gray-coded axes, variable bars, minterm numbers, rounded group outlines, legend below."""
    nrows, ncols = len(view.row_codes), len(view.col_codes)
    bar_gap = 14
    left = 34 + bar_gap * len(view.row_bars) + 8 * len(view.row_vars)
    top = 40 + bar_gap * len(view.col_bars)
    width, height = left + ncols * cell + 12, top + nrows * cell + 22
    e: list[str] = []
    title = f"{view.output}"
    e.append(f'<text x="2" y="16" font-weight="700" font-size="15" fill="var(--fg)">{escape(title)}</text>')

    # axis label in the corner: rows \ columns
    corner = "".join(view.row_vars) + "\\" + "".join(view.col_vars)
    e.append(f'<text x="{left - 6}" y="{top - 8}" text-anchor="end" font-size="11" fill="var(--muted)" {FONT}>'
             f"{escape(corner)}</text>")
    # column codes and bars
    for c, code in enumerate(view.col_codes):
        x = left + c * cell + cell / 2
        e.append(f'<text x="{x}" y="{top - 8}" text-anchor="middle" font-size="11" fill="var(--muted)" {FONT}>'
                 f"{escape(code)}</text>")
    for k, (var, idx) in enumerate(view.col_bars.items()):
        y = top - 26 - k * bar_gap
        for a, b in _runs(idx):
            x0, x1 = left + a * cell + 4, left + (b + 1) * cell - 4
            e.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="var(--ink)" stroke-width="2" '
                     'stroke-linecap="round"/>')
        x_label = left + _runs(idx)[0][0] * cell - 2 if idx else left - 6
        e.append(f'<text x="{x_label}" y="{y + 4}" text-anchor="end" font-size="12" font-style="italic" '
                 f'fill="var(--ink)">{escape(var)}</text>')
    # row codes and bars
    for r, code in enumerate(view.row_codes):
        y = top + r * cell + cell / 2 + 4
        e.append(f'<text x="{left - 6}" y="{y}" text-anchor="end" font-size="11" fill="var(--muted)" {FONT}>'
                 f"{escape(code)}</text>")
    for k, (var, idx) in enumerate(view.row_bars.items()):
        x = left - 34 - 8 * len(view.row_vars) + 8 - k * bar_gap
        for a, b in _runs(idx):
            y0, y1 = top + a * cell + 4, top + (b + 1) * cell - 4
            e.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1}" stroke="var(--ink)" stroke-width="2" '
                     'stroke-linecap="round"/>')
        y_label = top + (_runs(idx)[-1][1] + 1) * cell + 14 if idx else top + nrows * cell + 14
        e.append(f'<text x="{x}" y="{y_label}" text-anchor="middle" font-size="12" font-style="italic" '
                 f'fill="var(--ink)">{escape(var)}</text>')

    # group fills under the grid, outlines over it
    fills, outlines = [], []
    for gi, g in enumerate(view.groups):
        color = group_color(g.color)
        inset = 3 + 3 * (gi % 4)
        for r0, c0, r1, c1 in g.rects:
            x, y = left + c0 * cell + inset, top + r0 * cell + inset
            w, h = (c1 - c0 + 1) * cell - 2 * inset, (r1 - r0 + 1) * cell - 2 * inset
            fills.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{color}" fill-opacity=".07"/>')
            outlines.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="none" stroke="{color}" '
                            'stroke-width="2.2"/>')
    e += fills
    e.append(f'<rect x="{left}" y="{top}" width="{ncols * cell}" height="{nrows * cell}" fill="none" '
             'stroke="var(--fg)" stroke-opacity=".55" stroke-width="1.4"/>')
    for c in range(1, ncols):
        x = left + c * cell
        e.append(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{top + nrows * cell}" stroke="var(--line)"/>')
    for r in range(1, nrows):
        y = top + r * cell
        e.append(f'<line x1="{left}" y1="{y}" x2="{left + ncols * cell}" y2="{y}" stroke="var(--line)"/>')
    for r in range(nrows):
        for c in range(ncols):
            value = view.values[r][c]
            x, y = left + c * cell, top + r * cell
            style = {"1": 'font-weight="700" fill="var(--fg)"', "0": 'fill="var(--muted)" fill-opacity=".7"'}.get(
                value, 'fill="var(--muted)" font-style="italic"')
            e.append(f'<text x="{x + cell / 2}" y="{y + cell / 2 + 6}" text-anchor="middle" font-size="16" '
                     f"{style} {FONT}>{escape(value)}</text>")
            m = view.minterms[r][c]
            e.append(f'<text x="{x + 4}" y="{y + 11}" font-size="8.5" fill="var(--muted)" fill-opacity=".8" {FONT}>'
                     f"{m}</text>")
    e += outlines

    legend = "".join(
        f'<li><span style="color:{group_color(g.color)}"></span>{escape(line)}</li>'
        for g, line in zip(view.groups, legend_lines(view, "ascii")))
    svg = (f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
           f'aria-label="Karnaugh map of {escape(view.output)}">{"".join(e)}</svg>')
    return f'<figure class="kmap">{svg}{f"<ul class=legend>{legend}</ul>" if legend else ""}</figure>'


def timing_svg(timing: dict[str, Any], inputs: Sequence[str], outputs: Sequence[str],
               state_label: str = "state") -> str:
    """Clock, input bits, state bus and output bits over the simulated steps."""
    states: list[str] = list(timing.get("names") or timing.get("states") or [])
    if not states:
        return ""
    steps = len(states)
    in_steps: list[str] = [str(s) for s in timing.get("inputs") or []]
    out_steps: list[list[str]] = [[str(b) for b in o] for o in timing.get("outputs") or []]
    step_w, row_h, amp = 64, 34, 18
    label_w = 18 + 9 * max([len(n) for n in (*inputs, *outputs, state_label, "clk")] or [3])
    width = label_w + steps * step_w + 10

    def level_row(bits: list[str]) -> str:
        pts: list[str] = []
        for k, b in enumerate(bits):
            y = 0 if b == "1" else amp
            pts += [f"{k * step_w},{y}", f"{(k + 1) * step_w},{y}"]
        return f'<polyline points="{" ".join(pts)}" fill="none" stroke="var(--fg)" stroke-width="1.8"/>'

    rows: list[tuple[str, str]] = []
    clk = []
    for k in range(steps):
        x = k * step_w
        clk.append(f"{x},{amp} {x + step_w / 2},{amp} {x + step_w / 2},0 {x + step_w},0 {x + step_w},{amp}")
    clk_line = f'<polyline points="{" ".join(clk)}" fill="none" stroke="var(--accent)" stroke-width="1.6"/>'
    rows.append(("clk", clk_line))
    for i, name in enumerate(inputs):
        bits = [(s[i] if i < len(s) else "0") for s in in_steps]
        bits += [bits[-1] if bits else "0"] * (steps - len(bits))
        rows.append((name, level_row(bits)))
    bus = []
    for k, s in enumerate(states):
        x0 = k * step_w
        if k == 0 or states[k - 1] != s:
            bus.append(f'<path d="M{x0 + 4},0 L{x0},{amp / 2} L{x0 + 4},{amp}" fill="none" stroke="var(--fg)" '
                       'stroke-width="1.4"/>')
            end = next((j for j in range(k + 1, steps) if states[j] != s), steps)
            xe = end * step_w
            bus.append(f'<path d="M{x0 + 4},0 L{xe - 4},0 M{x0 + 4},{amp} L{xe - 4},{amp}" stroke="var(--fg)" '
                       'stroke-width="1.4"/>')
            if end < steps:
                bus.append(f'<path d="M{xe - 4},0 L{xe},{amp / 2} L{xe - 4},{amp}" fill="none" stroke="var(--fg)" '
                           'stroke-width="1.4"/>')
            bus.append(f'<text x="{(x0 + xe) / 2}" y="{amp / 2 + 4}" text-anchor="middle" font-size="12" '
                       f'fill="var(--fg)" {FONT}>{escape(s)}</text>')
    rows.append((state_label, "".join(bus)))
    for i, name in enumerate(outputs):
        bits = [(o[i] if i < len(o) else "0") for o in out_steps]
        bits += [bits[-1] if bits else "0"] * (steps - len(bits))
        rows.append((name, level_row(bits)))

    top = 22
    height = top + len(rows) * row_h + 6
    e = []
    for k in range(steps + 1):
        x = label_w + k * step_w
        e.append(f'<line x1="{x}" y1="{top - 6}" x2="{x}" y2="{height - 4}" stroke="var(--line)" '
                 'stroke-dasharray="3 4"/>')
        if k < steps:
            e.append(f'<text x="{x + step_w / 2}" y="{top - 9}" text-anchor="middle" font-size="10.5" '
                     f'fill="var(--muted)" {FONT}>t{k}</text>')
    for r, (name, body) in enumerate(rows):
        y = top + r * row_h + (row_h - amp) / 2
        e.append(f'<text x="{label_w - 10}" y="{y + amp / 2 + 4}" text-anchor="end" font-size="12.5" '
                 f'fill="var(--muted)" {FONT}>{escape(name)}</text>')
        e.append(f'<g transform="translate({label_w},{y})">{body}</g>')
    return (f'<svg class="timing" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
            f'aria-label="timing diagram">{"".join(e)}</svg>')


def state_graph_svg(fsm: dict[str, Any]) -> str:
    """State graph on a circle: Moore outputs inside the nodes, Mealy outputs on the edges."""
    import math

    states = [s.get("code", "") for s in fsm.get("states") or []]
    names = {s.get("code", ""): s.get("name") or s.get("code", "") for s in fsm.get("states") or []}
    transitions = fsm.get("transitions") or []
    if not states or not transitions:
        return ""
    moore = fsm.get("kind") == "moore"
    node_out: dict[str, str] = {}
    edges: dict[tuple[str, str], list[str]] = {}
    for tr in transitions:
        out = "".join(map(str, tr.get("outputs") or []))
        if moore:
            node_out.setdefault(tr["state"], out)
            label = str(tr.get("input", ""))
        else:
            label = f"{tr.get('input', '')}/{out}"
        edges.setdefault((tr["state"], tr["next"]), []).append(label)

    # walk the graph from the initial state so that chains of transitions run around the circle
    order: list[str] = []
    stack = [fsm.get("initial")] if fsm.get("initial") in states else []
    while stack:
        cur = stack.pop()
        if cur in order:
            continue
        order.append(cur)
        stack += sorted({b for (a, b) in edges if a == cur and b not in order}, reverse=True)
    states = order + [s for s in states if s not in order]
    n, r_node = len(states), 30
    radius = max(95.0, n * (2 * r_node + 46) / (2 * math.pi))
    pad = r_node + 70
    size = 2 * (radius + pad)
    cx = cy = size / 2
    pos = {}
    for k, s in enumerate(states):
        angle = -math.pi / 2 + 2 * math.pi * k / n
        pos[s] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))

    arrow = ('<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
             'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--muted)"/></marker></defs>')
    e = [arrow]
    for (a, b), labels in edges.items():
        text = escape(",".join(labels))
        ax, ay = pos[a]
        if a == b:
            ux, uy = (ax - cx), (ay - cy)
            norm = math.hypot(ux, uy) or 1.0
            ux, uy = ux / norm, uy / norm
            px, py = -uy, ux
            sx, sy = ax + ux * r_node * .7 + px * r_node * .7, ay + uy * r_node * .7 + py * r_node * .7
            ex, ey = ax + ux * r_node * .7 - px * r_node * .7, ay + uy * r_node * .7 - py * r_node * .7
            c1 = (sx + ux * 55 + px * 22, sy + uy * 55 + py * 22)
            c2 = (ex + ux * 55 - px * 22, ey + uy * 55 - py * 22)
            e.append(f'<path d="M{sx:.1f},{sy:.1f} C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {ex:.1f},{ey:.1f}" '
                     'fill="none" stroke="var(--muted)" stroke-width="1.5" marker-end="url(#arrow)"/>')
            lx, ly = ax + ux * (r_node + 52), ay + uy * (r_node + 52)
        else:
            bx, by = pos[b]
            dx, dy = bx - ax, by - ay
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist
            px, py = uy, -ux  # bend to one side so a↔b pairs do not overlap
            bend = 26.0
            mx, my = (ax + bx) / 2 + px * bend, (ay + by) / 2 + py * bend
            sx, sy = ax + ux * r_node, ay + uy * r_node
            ex, ey = bx - ux * (r_node + 2), by - uy * (r_node + 2)
            e.append(f'<path d="M{sx:.1f},{sy:.1f} Q{mx:.1f},{my:.1f} {ex:.1f},{ey:.1f}" fill="none" '
                     'stroke="var(--muted)" stroke-width="1.5" marker-end="url(#arrow)"/>')
            lx, ly = 0.25 * sx + 0.5 * mx + 0.25 * ex + px * 10, 0.25 * sy + 0.5 * my + 0.25 * ey + py * 10
        e.append(f'<text x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="middle" font-size="12" fill="var(--fg)" '
                 f'paint-order="stroke" stroke="var(--card)" stroke-width="4" {FONT}>{text}</text>')
    initial = fsm.get("initial")
    for s in states:
        x, y = pos[s]
        ring = (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r_node + 4}" fill="none" stroke="var(--accent)" '
                'stroke-width="1.5"/>') if s == initial else ""
        label = escape(names[s])
        sub = f'<tspan x="{x:.1f}" dy="15" font-size="10.5" fill="var(--muted)">{escape(node_out[s])}</tspan>' \
            if moore and s in node_out else ""
        dy = -3 if sub else 4
        e.append(f'{ring}<circle cx="{x:.1f}" cy="{y:.1f}" r="{r_node}" fill="var(--card)" stroke="var(--accent)" '
                 f'stroke-width="2"/><text x="{x:.1f}" y="{y + dy:.1f}" text-anchor="middle" font-size="13" '
                 f'font-weight="700" fill="var(--fg)" {FONT}>{label}{sub}</text>')
    return (f'<svg viewBox="0 0 {size:.0f} {size:.0f}" width="{size:.0f}" height="{size:.0f}" role="img" '
            f'aria-label="state graph">{"".join(e)}</svg>')
