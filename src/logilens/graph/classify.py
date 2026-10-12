"""Combinational / sequential classification of one circuit.

* State elements (flip-flops, registers, memories) cut the graph: their outputs act as pseudo-inputs.
* Remaining cycles are combinational (asynchronous) loops.
* For each output pin: its fan-in cone (logic components) and support (input pins / state elements reached).
* Output groups: outputs whose cones share at least one logic component (candidates for multi-output
  minimization, e.g. the NAND half and the NOR half of a converter).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logilens.core.netlist import CircuitNetlist
from logilens.graph.topo import ComponentGraph, build_graph, cyclic_sccs, fan_in_cone, levelize
from logilens.parse.component_specs import STATE_KINDS
from logilens.parse.connectivity import UnionFind

LOGIC_KINDS = frozenset({"gate", "not", "buffer", "controlled", "plexer", "arith", "wiring_logic", "subcircuit",
                         "switch"})


@dataclass
class Classification:
    circuit: str
    graph: ComponentGraph
    state_elements: list[int]
    clocks: list[int]
    comb_loops: list[list[int]]
    levels: dict[int, int]
    cones: dict[str, set[int]] = field(default_factory=dict)  # output name -> logic comp ids
    supports: dict[str, list[str]] = field(default_factory=dict)  # output name -> input names / state comps
    groups: list[list[str]] = field(default_factory=list)

    @property
    def is_sequential(self) -> bool:
        return bool(self.state_elements) or bool(self.comb_loops)

    def group_of(self, output: str) -> list[str]:
        return next((g for g in self.groups if output in g), [output])


def _cut_graph(g: ComponentGraph, state: set[int]) -> dict[int, set[int]]:
    """Successor map without edges entering state elements (their outputs become sources)."""
    return {u: {v for v in vs if v not in state} for u, vs in g.succ.items()}


def classify(circ: CircuitNetlist) -> Classification:
    """Analyze one circuit (not flattened: subcircuit instances are opaque logic nodes)."""
    g = build_graph(circ)
    state = {c.id for c in circ.components if c.kind in STATE_KINDS}
    clocks = [c.id for c in circ.components if c.kind == "clock"]
    succ = _cut_graph(g, state)
    loops = cyclic_sccs(g.nodes, succ)
    result = Classification(circ.name, g, sorted(state), clocks, loops, levelize(g.nodes, succ))
    pred_cut: dict[int, set[int]] = {}
    for u, vs in succ.items():
        for v in vs:
            pred_cut.setdefault(v, set()).add(u)
    input_ids = {p.comp_id: p.name for p in circ.inputs}
    for out in circ.outputs:
        cone = fan_in_cone(out.comp_id, pred_cut, stop=state | set(input_ids))
        result.cones[out.name] = {v for v in cone if circ.components[v].kind in LOGIC_KINDS}
        support = [input_ids[v] for v in cone if v in input_ids]
        support += [circ.components[v].describe() for v in cone if v in state]
        order = {p.name: i for i, p in enumerate(circ.inputs)}
        result.supports[out.name] = sorted(support, key=lambda s: (order.get(s, len(order)), s))
    result.groups = output_groups(circ, result.cones)
    return result


def output_groups(circ: CircuitNetlist, cones: dict[str, set[int]]) -> list[list[str]]:
    """Union outputs whose cones share a logic component; groups keep output (pin) order."""
    uf = UnionFind()
    owner: dict[int, str] = {}
    names = [p.name for p in circ.outputs]
    for name in names:
        uf.add(name)
        for comp in cones.get(name, ()):
            if comp in owner:
                uf.union(owner[comp], name)
            else:
                owner[comp] = name
    groups: dict[object, list[str]] = {}
    for name in names:
        groups.setdefault(uf.find(name), []).append(name)
    return list(groups.values())
