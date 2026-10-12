"""Event-driven evaluator over bit threads of a :class:`FlatCircuit`.

Every component starts dirty (like a fresh Logisim ``CircuitState``); a component is re-evaluated when one of
the threads it reads changes; a thread's value is the ``combine`` of all its drivers (X when undriven), then
pull resistors replace floating bits. Settles to the same fixpoint as Logisim for loop-free logic; for
asynchronous loops the event order differs from Logisim's delay queue, so results there are best effort and
``oscillating`` is reported when the iteration budget is exhausted.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from logilens.core.netlist import UnsupportedItem
from logilens.parse.hierarchy import FlatCircuit
from logilens.sim.models import Model, SimContext, is_simulated, model_for
from logilens.sim.values import ONE, ZERO, Bit, E, Value, X, b_combine, from_int, to_str


@dataclass
class _Node:
    model: Model | None
    reads: list[int]  # threads read
    drives: list[tuple[int, int, int]] = field(default_factory=list)  # (port, bit, thread)


class Simulator:
    """Bit-level simulator; structure is built once, :meth:`reset` gives a fresh state."""

    def __init__(self, flat: FlatCircuit, ctx: SimContext | None = None, sim_limit: int = 1000) -> None:
        self.flat = flat
        self.ctx = ctx or SimContext()
        self.sim_limit = sim_limit
        self.nodes: list[_Node] = []
        self.readers: list[list[int]] = [[] for _ in range(flat.n_threads)]
        self.drivers: list[list[tuple[int, int, int]]] = [[] for _ in range(flat.n_threads)]
        self.unsupported: list[UnsupportedItem] = []
        for i, fc in enumerate(flat.components):
            comp = fc.comp
            model = model_for(comp)
            if not is_simulated(comp):
                self.unsupported.append(UnsupportedItem("simulation", comp.name, fc.path, comp.loc,
                                                        "component not modeled by the Python simulator"))
            node = _Node(model, [])
            for port, bits in zip(comp.ports, fc.threads):
                if port.direction in ("input", "inout"):
                    node.reads.extend(bits)
                    for t in bits:
                        self.readers[t].append(i)
                if model is not None and port.direction in ("output", "inout"):
                    for b, t in enumerate(bits):
                        if t in flat.invalid:
                            continue  # Logisim: invalid (width-conflict) bundles carry no value
                        node.drives.append((port.index, b, t))
                        self.drivers[t].append((i, port.index, b))
            self.nodes.append(node)
        self.reset()

    # -------------------------------------------------------------- state
    def reset(self) -> None:
        """Fresh state: all threads X, all components dirty, empty instance data."""
        self.values: list[Bit] = [X] * self.flat.n_threads
        for t, pull in self.flat.pulls.items():
            self.values[t] = pull
        self.out: list[dict[int, Value]] = [{} for _ in self.nodes]
        self.state: list[dict[str, Any]] = [{} for _ in self.nodes]
        self.dirty: deque[int] = deque(range(len(self.nodes)))
        self.queued = [True] * len(self.nodes)
        self.oscillating = False

    def _mark(self, i: int) -> None:
        if not self.queued[i]:
            self.queued[i] = True
            self.dirty.append(i)

    def poke(self, comp_index: int, key: str, value: Any) -> None:
        """Set instance data (e.g. a pin's value or a clock level) and schedule the component."""
        self.state[comp_index][key] = value
        self._mark(comp_index)

    # -------------------------------------------------------------- evaluation
    def port_value(self, i: int, port: int) -> Value:
        return tuple(self.values[t] for t in self.flat.components[i].threads[port])

    def _thread_value(self, t: int) -> Bit:
        v = X
        for i, port, b in self.drivers[t]:
            out = self.out[i].get(port)
            if out is not None and b < len(out):
                v = b_combine(v, out[b])
        if v == X and t in self.flat.pulls:
            v = self.flat.pulls[t]
        return v

    def _evaluate(self, i: int) -> set[int]:
        node = self.nodes[i]
        self.queued[i] = False
        if node.model is None:
            return set()
        fc = self.flat.components[i]
        ins = [tuple(self.values[t] for t in bits) for bits in fc.threads]
        new = node.model(fc.comp, ins, fc.connected, self.state[i], self.ctx)
        changed: set[int] = set()
        for port, value in new.items():
            if self.out[i].get(port) != value:
                self.out[i][port] = value
                changed.update(t for t in fc.threads[port])
        return changed

    def propagate(self) -> bool:
        """Run to a fixpoint in delta cycles (all dirty components see the same snapshot, like Logisim's
        first propagation step where every component reads still-floating inputs). Returns False and sets
        ``oscillating`` when ``sim_limit`` cycles are exceeded."""
        cycles = 0
        while self.dirty:
            cycles += 1
            if cycles > self.sim_limit:
                self.oscillating = True
                return False
            batch = list(self.dirty)
            self.dirty.clear()
            changed: set[int] = set()
            for i in batch:
                changed |= self._evaluate(i)
            for t in sorted(changed):
                v = self._thread_value(t)
                if v != self.values[t]:
                    self.values[t] = v
                    for r in self.readers[t]:
                        self._mark(r)
        self.oscillating = False
        return True

    # -------------------------------------------------------------- pins
    def index_of_pin(self, comp_id: int) -> int:
        """Index (in ``flat.components``) of a top-level component by its id."""
        if not hasattr(self, "_top_index"):
            self._top_index = {fc.comp.id: i for i, fc in enumerate(self.flat.components)
                               if fc.path == self.flat.top}
        return self._top_index[comp_id]

    def set_inputs(self, values: list[Value]) -> None:
        """Poke every top-level input pin (same order as ``flat.inputs``)."""
        for (pin, _), value in zip(self.flat.inputs, values):
            self.poke(self.index_of_pin(pin.comp_id), "value", tuple(value))

    def read_outputs(self) -> list[str]:
        """Output pin values as Logisim prints them (MSB first)."""
        return [to_str(tuple(self.values[t] for t in threads)) for _, threads in self.flat.outputs]


def evaluate_row(sim: Simulator, row: int, widths: list[int]) -> tuple[list[str], list[str], bool]:
    """Fresh state, apply input combination ``row`` (MSB = first input), propagate, read outputs."""
    sim.reset()
    shift = sum(widths)
    values: list[Value] = []
    for w in widths:
        shift -= w
        values.append(from_int((row >> shift) & ((1 << w) - 1), w))
    sim.set_inputs(values)
    stable = sim.propagate()
    return [to_str(v) for v in values], sim.read_outputs(), not stable


__all__ = ["ONE", "ZERO", "E", "SimContext", "Simulator", "X", "evaluate_row"]
