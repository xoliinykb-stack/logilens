"""Transition graph: Graphviz DOT (+ SVG when ``dot`` is installed) and a terminal adjacency listing.

Moore: nodes ``S/y``, edges labelled with the input combinations. Mealy: nodes ``S``, edges ``x/y``.
Parallel edges between the same pair of states are merged into one edge with a comma-separated label.
"""

from __future__ import annotations

import shutil
import subprocess

from logilens.seq.fsm import FSM


def _q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def node_label(fsm: FSM, s: str) -> str:
    return f"{fsm.name(s)}/{fsm.out_str(s)}" if fsm.kind == "moore" else fsm.name(s)


def edges(fsm: FSM, states: list[str] | None = None) -> list[tuple[str, str, list[str]]]:
    """(from, to, labels) with parallel edges merged; labels are ``x`` (Moore) or ``x/y`` (Mealy)."""
    states = states if states is not None else fsm.states
    out: dict[tuple[str, str], list[str]] = {}
    for s in states:
        for x in fsm.input_codes:
            t = fsm.delta[(s, x)]
            lab = x or "-"
            if fsm.kind == "mealy":
                lab = f"{lab}/{''.join(fsm.lam[(s, x)])}"
            out.setdefault((s, t), []).append(lab)
    return [(s, t, labs) for (s, t), labs in out.items()]


def to_dot(fsm: FSM, states: list[str] | None = None, unreachable: set[str] | None = None) -> str:
    states = states if states is not None else fsm.states
    unreachable = unreachable or set()
    lines = [f"digraph {_q(fsm.circuit or 'fsm')} {{", "  rankdir=LR;",
             '  node [shape=circle, fontname="Helvetica"];', '  edge [fontname="Helvetica"];',
             '  __start [shape=point, label=""];']
    for s in states:
        attrs = [f"label={_q(node_label(fsm, s))}"]
        if s == fsm.initial:
            attrs.append("shape=doublecircle")
        if s in unreachable:
            attrs.append("style=dashed")
        lines.append(f"  {_q(fsm.name(s))} [{', '.join(attrs)}];")
    lines.append(f"  __start -> {_q(fsm.name(fsm.initial))};")
    for s, t, labs in edges(fsm, states):
        lines.append(f"  {_q(fsm.name(s))} -> {_q(fsm.name(t))} [label={_q(','.join(labs))}];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_svg(dot_text: str, timeout: float = 30.0) -> str | None:
    """SVG via the Graphviz ``dot`` binary, or None when it is not installed / fails."""
    exe = shutil.which("dot")
    if exe is None:
        return None
    try:
        res = subprocess.run([exe, "-Tsvg"], input=dot_text, capture_output=True, text=True, timeout=timeout,
                             check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout if res.returncode == 0 else None


def to_text(fsm: FSM, states: list[str] | None = None, ascii_only: bool = False) -> str:
    """Adjacency listing, e.g. ``→ 10/100 ──1──▶ 00``."""
    arrow_l, arrow_r, start = ("--", "-->", "->") if ascii_only else ("──", "──▶", "→")
    states = states if states is not None else fsm.states
    labels = {s: node_label(fsm, s) for s in states}
    width = max(len(v) for v in labels.values())
    by_src: dict[str, list[tuple[str, list[str]]]] = {}
    for s, t, labs in edges(fsm, states):
        by_src.setdefault(s, []).append((t, labs))
    lines = []
    for s in states:
        mark = start if s == fsm.initial else " " * len(start)
        for j, (t, labs) in enumerate(by_src.get(s, [])):
            head = f"{mark} {labels[s].ljust(width)}" if j == 0 else " " * (len(mark) + 1 + width)
            loop = " (self-loop)" if t == s else ""
            lines.append(f"{head} {arrow_l}{','.join(labs)}{arrow_r} {fsm.name(t)}{loop}")
    return "\n".join(lines)
