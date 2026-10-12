"""Graph properties of an FSM and its transition table (prechodová tabuľka).

* reachable / unreachable states (from the power-on state; also from the async-reset state when present);
* dead ends: absorbing states (every input leads back to the state itself — no exit);
* traps: closed groups of states (bottom strongly connected components) that cannot be left, other than the
  whole reachable machine;
* self-loops: (state, input) pairs with δ(s, x) = s.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from logilens.graph.topo import tarjan_scc
from logilens.seq.fsm import FSM


@dataclass
class TableRow:
    state: str
    name: str
    next: list[str]  # per input code (display names)
    outputs: list[str]  # Moore: one entry; Mealy: per input code
    reachable: bool = True


@dataclass
class Analysis:
    initial: str
    reachable: list[str]
    unreachable: list[str]
    dead_ends: list[str]
    traps: list[list[str]]
    self_loops: list[tuple[str, str]]
    strongly_connected: bool
    rows: list[TableRow] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)  # input codes
    kind: str = "moore"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial": self.initial,
            "reachable": list(self.reachable),
            "unreachable": list(self.unreachable),
            "dead_ends": list(self.dead_ends),
            "traps": [list(t) for t in self.traps],
            "self_loops": [{"state": s, "input": x} for s, x in self.self_loops],
            "strongly_connected": self.strongly_connected,
            "table": {
                "columns": list(self.columns),
                "rows": [{"state": r.state, "name": r.name, "next": list(r.next), "outputs": list(r.outputs),
                          "reachable": r.reachable} for r in self.rows],
            },
            "notes": list(self.notes),
        }


def reachable_from(fsm: FSM, start: str) -> list[str]:
    """States reachable from ``start`` in BFS order."""
    seen, order, queue = {start}, [start], deque([start])
    while queue:
        s = queue.popleft()
        for t in fsm.successors(s):
            if t not in seen and (t, fsm.input_codes[0]) in fsm.delta:
                seen.add(t)
                order.append(t)
                queue.append(t)
    return order


def analyze_fsm(fsm: FSM) -> Analysis:
    reach = reachable_from(fsm, fsm.initial)
    notes: list[str] = []
    if fsm.reset_state is not None and fsm.reset_state not in reach and fsm.reset_state in fsm.states:
        extra = [s for s in reachable_from(fsm, fsm.reset_state) if s not in reach]
        notes.append(f"states reachable only after the asynchronous reset ({fsm.name(fsm.reset_state)}): "
                     + ", ".join(fsm.name(s) for s in extra))
        reach += extra
    rset = set(reach)
    unreachable = [s for s in fsm.states if s not in rset]
    xs = fsm.input_codes
    dead = [s for s in reach if all(fsm.delta[(s, x)] == s for x in xs)]
    loops = [(s, x) for s in fsm.states for x in xs if fsm.delta[(s, x)] == s]
    succ = {s: {fsm.delta[(s, x)] for x in xs} for s in reach}
    sccs = tarjan_scc(reach, succ)
    bottoms = []
    for comp in sccs:
        cset = set(comp)
        if all(t in cset for s in comp for t in succ[s]):
            bottoms.append(sorted(comp, key=reach.index))
    strongly = len(sccs) == 1 and set(sccs[0]) == rset
    traps = [b for b in bottoms if set(b) != rset]
    order = reach + unreachable
    rows = []
    for s in order:
        nxt = [fsm.name(fsm.delta[(s, x)]) for x in xs]
        outs = ["".join(fsm.lam[(s, x)]) for x in xs] if fsm.kind == "mealy" else [fsm.out_str(s)]
        rows.append(TableRow(s, fsm.name(s), nxt, outs, s in rset))
    if fsm.initial == "0" * len(fsm.state_vars):
        notes.append(f"initial state {fsm.name(fsm.initial)} (code {fsm.initial or '-'}): Logisim flip-flops "
                     "power on at 0")
    if fsm.reset_state is not None:
        notes.append(f"asserting {', '.join(fsm.async_inputs)} forces state {fsm.name(fsm.reset_state)} "
                     f"(code {fsm.reset_state})")
    return Analysis(fsm.initial, reach, unreachable, dead, traps, loops, strongly, rows, xs, fsm.kind, notes)


def _joined(names: list[str]) -> str:
    if not names:
        return "-"
    return "".join(names) if all(len(n) == 1 for n in names) else ",".join(names)


def render_table(fsm: FSM, an: Analysis) -> str:
    """Plain-text transition table: state | next state per input | output(s)."""
    xs = an.columns
    xname = _joined(fsm.inputs)
    head = ["state"] + [f"{xname}={x}" if x else "next" for x in xs]
    yname = ",".join(fsm.outputs)
    head += [f"{yname} ({xname}={x})" for x in xs] if fsm.kind == "mealy" else [yname or "out"]
    body = []
    for r in an.rows:
        mark = "" if r.reachable else " (unreachable)"
        initial = "→" if r.state == fsm.initial else " "
        body.append([f"{initial}{r.name}{mark}"] + r.next + r.outputs)
    widths = [max(len(head[i]), *(len(b[i]) for b in body)) for i in range(len(head))]
    lines = [" │ ".join(h.ljust(w) for h, w in zip(head, widths)),
             "─┼─".join("─" * w for w in widths)]
    lines += [" │ ".join(c.ljust(w) for c, w in zip(b, widths)) for b in body]
    return "\n".join(lines)


def rich_table(fsm: FSM, an: Analysis):  # type: ignore[no-untyped-def]
    """The transition table as a ``rich.table.Table``."""
    from rich.table import Table

    xs = an.columns
    xname = _joined(fsm.inputs)
    t = Table(title=f"transition table ({fsm.kind})")
    t.add_column("state", style="bold")
    for x in xs:
        t.add_column(f"{xname}={x}" if x else "next", justify="center")
    yname = ",".join(fsm.outputs)
    for x in (xs if fsm.kind == "mealy" else [None]):
        t.add_column(f"{yname} ({xname}={x})" if x is not None else (yname or "out"), justify="center",
                     style="green")
    for r in an.rows:
        label = ("→ " if r.state == fsm.initial else "  ") + r.name
        t.add_row(label if r.reachable else f"[dim]{label}[/dim]", *r.next, *r.outputs)
    return t
