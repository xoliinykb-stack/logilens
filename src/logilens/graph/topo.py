"""Component-level signal-flow graph of one circuit and generic graph algorithms.

Edge u -> v when an output port of u drives a bit thread read by an input port of v (tunnels and splitters are
transparent because they are already folded into threads). Input pins are sources, output pins are sinks.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TypeVar

from logilens.core.netlist import CircuitNetlist


@dataclass
class ComponentGraph:
    nodes: list[int]
    succ: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    pred: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    thread_drivers: dict[int, list[tuple[int, int]]] = field(default_factory=lambda: defaultdict(list))
    thread_readers: dict[int, list[tuple[int, int]]] = field(default_factory=lambda: defaultdict(list))

    def add_edge(self, u: int, v: int) -> None:
        self.succ[u].add(v)
        self.pred[v].add(u)


def build_graph(circ: CircuitNetlist) -> ComponentGraph:
    """Signal-flow graph over component ids (wiring-only parts — text, tunnel, splitter — are not nodes)."""
    g = ComponentGraph([c.id for c in circ.components if c.kind not in ("text", "tunnel", "splitter")])
    for c in circ.components:
        if c.kind in ("text", "tunnel", "splitter"):
            continue
        for p in c.ports:
            ref = (c.id, p.index)
            if ref not in circ.port_net:
                continue
            for t in circ.port_threads(ref):
                if p.direction in ("output", "inout"):
                    g.thread_drivers[t].append(ref)
                if p.direction in ("input", "inout"):
                    g.thread_readers[t].append(ref)
    for t, drivers in g.thread_drivers.items():
        for u, _ in drivers:
            for v, _ in g.thread_readers.get(t, []):
                if u != v or _self_loop(circ, u, t):
                    g.add_edge(u, v)
    return g


def _self_loop(circ: CircuitNetlist, comp_id: int, thread: int) -> bool:
    """A component reading a thread it drives through distinct ports (output wired back to an input)."""
    comp = circ.components[comp_id]
    outs = {p.index for p in comp.ports if p.direction == "output" and thread in circ.port_threads((comp_id, p.index))}
    ins = {p.index for p in comp.ports if p.direction == "input" and thread in circ.port_threads((comp_id, p.index))}
    return bool(outs and ins)


N = TypeVar("N", int, str)  # node ids: component indices or FSM state names


def tarjan_scc(nodes: Iterable[N], succ: dict[N, set[N]]) -> list[list[N]]:
    """Strongly connected components (iterative Tarjan), in reverse topological order."""
    index: dict[N, int] = {}
    low: dict[N, int] = {}
    on_stack: set[N] = set()
    stack: list[N] = []
    result: list[list[N]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work: list[tuple[N, Iterable[N]]] = [(root, iter(sorted(succ.get(root, ()))))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(sorted(succ.get(w, ())))))
                    advanced = True
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp: list[N] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                result.append(sorted(comp))
    return result


def cyclic_sccs(nodes: Iterable[int], succ: dict[int, set[int]]) -> list[list[int]]:
    """SCCs that contain a cycle (size > 1, or a node with a self-loop)."""
    return [s for s in tarjan_scc(nodes, succ) if len(s) > 1 or s[0] in succ.get(s[0], ())]


def levelize(nodes: Iterable[int], succ: dict[int, set[int]]) -> dict[int, int]:
    """Logic level = longest path from a source; members of one SCC share a level."""
    node_list = list(nodes)
    sccs = tarjan_scc(node_list, succ)
    comp_of = {v: i for i, s in enumerate(sccs) for v in s}
    level_of_scc: dict[int, int] = {}
    for i in reversed(range(len(sccs))):  # Tarjan emits sinks first -> reversed = topological order
        level_of_scc.setdefault(i, 0)
        for v in sccs[i]:
            for w in succ.get(v, ()):
                j = comp_of.get(w)
                if j is not None and j != i:
                    level_of_scc[j] = max(level_of_scc.get(j, 0), level_of_scc[i] + 1)
    return {v: level_of_scc[comp_of[v]] for v in node_list}


def fan_in_cone(start: int, pred: dict[int, set[int]], stop: Iterable[int] = ()) -> set[int]:
    """All transitive predecessors of ``start`` (excluded); nodes in ``stop`` are included but not crossed."""
    stop_set = set(stop)
    seen: set[int] = set()
    todo = list(pred.get(start, ()))
    while todo:
        v = todo.pop()
        if v in seen or v == start:
            continue
        seen.add(v)
        if v not in stop_set:
            todo.extend(pred.get(v, ()))
    return seen
