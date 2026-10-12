"""Clocked simulation on top of :class:`Simulator` with a persistent state (unlike truth tables).

Flip-flops follow ``AbstractFlipFlop`` (rising edge by default, async reset/preset, initial Q = 0) and remember
their last clock value, so edges are detected exactly like Logisim. ``tick()`` mirrors ``Propagator.tick``:
every Clock component toggles (the first tick drives it high = rising edge).
"""

from __future__ import annotations

from dataclasses import dataclass

from logilens.parse.hierarchy import FlatCircuit
from logilens.sim.combinational import Simulator
from logilens.sim.models import SimContext
from logilens.sim.values import ONE, ZERO, Value, from_int, to_str


@dataclass(frozen=True)
class TraceRow:
    """One observation: the operation performed and the resulting outputs / flip-flop states."""

    op: str
    outputs: list[str]
    state: dict[str, str]


class SequentialSimulator:
    """Persistent-state simulator: set inputs, tick clocks, observe outputs and flip-flop contents."""

    def __init__(self, flat: FlatCircuit, ctx: SimContext | None = None) -> None:
        self.sim = Simulator(flat, ctx)
        self.flat = flat
        self.clocks = [i for i, fc in enumerate(flat.components) if fc.comp.name == "Clock"]
        self.memories = [i for i, fc in enumerate(flat.components) if fc.comp.kind in ("flipflop", "register")]
        self.reset()

    def reset(self) -> None:
        """Power-on state: flip-flops 0, clocks low, inputs undefined; then settle."""
        self.sim.reset()
        self.clock_level = ZERO
        self.sim.propagate()

    def set_inputs(self, values: list[Value] | list[int]) -> None:
        """Poke all input pins (``flat.inputs`` order); ints are converted with each pin's width."""
        conv = [from_int(v, pin.width) if isinstance(v, int) else v for (pin, _), v in zip(self.flat.inputs, values)]
        self.sim.set_inputs(conv)
        self.sim.propagate()

    def set_clock(self, level: int) -> None:
        """Drive every Clock component to ``level`` and settle."""
        self.clock_level = ONE if level else ZERO
        for i in self.clocks:
            self.sim.poke(i, "value", self.clock_level)
        self.sim.propagate()

    def tick(self) -> None:
        """Toggle the clocks once (``Propagator.tick``)."""
        self.set_clock(0 if self.clock_level == ONE else 1)

    def step(self, clock: int | None = None) -> None:
        """Set the clock level, or toggle it when ``clock`` is None."""
        if clock is None:
            self.tick()
        else:
            self.set_clock(clock)

    def cycle(self, inputs: list[Value] | list[int] | None = None) -> TraceRow:
        """Apply inputs, one full clock period (rise, fall); return the observation after the period."""
        if inputs is not None:
            self.set_inputs(inputs)
        self.set_clock(1)
        self.set_clock(0)
        return self.observe("cycle")

    def outputs(self) -> list[str]:
        return self.sim.read_outputs()

    def memory_state(self) -> dict[str, str]:
        """Flip-flop / register contents keyed by ``"path:NAME (x,y)"``."""
        out: dict[str, str] = {}
        for i in self.memories:
            fc = self.flat.components[i]
            st = self.sim.state[i]
            if fc.comp.kind == "flipflop":
                val = st.get("q", ZERO)
            else:
                val = to_str(from_int(st.get("value", 0), int(fc.comp.attrs.get("width") or 8)))
            out[f"{fc.path}:{fc.comp.describe()}"] = val
        return out

    def observe(self, op: str) -> TraceRow:
        return TraceRow(op, self.outputs(), self.memory_state())


def run_trace(flat: FlatCircuit, steps: list[str], ctx: SimContext | None = None) -> list[TraceRow]:
    """Run a step script: ``"t"`` = tick clocks; otherwise comma-separated input bit strings (MSB first)."""
    from logilens.sim.values import from_str

    sim = SequentialSimulator(flat, ctx)
    rows: list[TraceRow] = []
    for step in steps:
        if step == "t":
            sim.tick()
        else:
            sim.set_inputs([from_str(s) for s in step.split(",")])
        rows.append(sim.observe(step))
    return rows
