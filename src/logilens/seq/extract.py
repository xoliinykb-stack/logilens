"""Find the state elements of a clocked circuit and extract its FSM by simulation.

Flip-flops (D, T, J-K, S-R) and registers are the state bits. Input pins are classified by what they reach
through combinational logic: *clock* pins (only clock ports), *async* pins (only asynchronous reset/preset/
clear ports; held inactive = 0 during extraction) and *data* pins (the FSM inputs).

Extraction forces every state code into the flip-flops of the Python simulator (``SequentialSimulator``),
applies every input combination, reads the outputs before the clock edge (λ) and the flip-flop contents after
one full clock period (δ). Logisim flip-flops power on at 0, so the initial state is the all-zero code.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

from logilens.core.errors import LogilensError
from logilens.core.netlist import ProjectNetlist
from logilens.graph.classify import classify
from logilens.parse.hierarchy import FlatCircuit, flatten
from logilens.seq.fsm import FSM
from logilens.sim.models import SimContext
from logilens.sim.sequential import SequentialSimulator
from logilens.sim.values import ONE, ZERO, Value, from_int, to_str

MAX_STATE_BITS = 16
MAX_INPUT_BITS = 12
MAX_COMBINATIONS = 1 << 16
"""Above this many (state, input) pairs only the states reachable from the initial state are enumerated."""

FF_KIND = {"D Flip-Flop": "D", "T Flip-Flop": "T", "J-K Flip-Flop": "JK", "S-R Flip-Flop": "SR", "Register": "REG"}
FF_DATA_PORTS = {"D": ("d",), "T": ("t",), "JK": ("j", "k"), "SR": ("s", "r"), "REG": ("d",)}
ASYNC_PORTS = frozenset({"reset", "preset", "clear"})
_NOT_SIMULATED_STATE = frozenset({"Counter", "Shift Register", "Random", "RAM", "ROM"})


class SeqTooLarge(LogilensError):
    """The state/input space exceeds the supported limits."""


class SeqNotApplicable(LogilensError):
    """The circuit has no (supported) state elements."""


@dataclass
class StateElement:
    """One flip-flop or register (``bits`` > 1 only for registers)."""

    index: int  # index in FlatCircuit.components
    kind: str  # D | T | JK | SR | REG
    name: str  # base name of its state variable(s)
    path: str
    describe: str
    trigger: str
    bits: int = 1
    named: bool = False  # name came from a label / pin / tunnel (not generated)

    def var_names(self) -> list[str]:
        """State variable names MSB-first."""
        if self.bits == 1:
            return [self.name]
        return [f"{self.name}{b}" for b in range(self.bits - 1, -1, -1)]


@dataclass
class PinRole:
    name: str
    width: int
    role: str  # data | clock | async
    via_logic: bool = False


@dataclass
class Extraction:
    """Structure found in the flattened circuit, plus a reusable simulator runner."""

    circuit: str
    flat: FlatCircuit
    elements: list[StateElement]
    pins: list[PinRole]
    clock_comps: list[int]
    warnings: list[str] = field(default_factory=list)

    @property
    def state_vars(self) -> list[str]:
        return [v for e in self.elements for v in e.var_names()]

    @property
    def ff_kinds(self) -> list[str]:
        return [e.kind for e in self.elements for _ in range(e.bits)]

    @property
    def data_pins(self) -> list[PinRole]:
        return [p for p in self.pins if p.role == "data"]

    @property
    def input_names(self) -> list[str]:
        """FSM input bit names MSB-first (multi-bit pins expand to name<bit>)."""
        out: list[str] = []
        for p in self.data_pins:
            out += [p.name] if p.width == 1 else [f"{p.name}{b}" for b in range(p.width - 1, -1, -1)]
        return out

    @property
    def output_names(self) -> list[str]:
        return [pin.name for pin, _ in self.flat.outputs]


# ------------------------------------------------------------------ structure
def _natural_key(text: str) -> list[object]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def _readers(flat: FlatCircuit) -> dict[int, list[tuple[int, int]]]:
    readers: dict[int, list[tuple[int, int]]] = {}
    for i, fc in enumerate(flat.components):
        for port, bits in zip(fc.comp.ports, fc.threads):
            if port.direction in ("input", "inout"):
                for t in bits:
                    readers.setdefault(t, []).append((i, port.index))
    return readers


def _reach(flat: FlatCircuit, readers: dict[int, list[tuple[int, int]]], start: list[int]
           ) -> list[tuple[int, str, bool]]:
    """Sinks reached from ``start`` threads through combinational parts: (state comp, port name, via_logic)."""
    seen_threads = set(start)
    queue: deque[tuple[int, bool]] = deque((t, False) for t in start)
    seen_comps: set[int] = set()
    sinks: list[tuple[int, str, bool]] = []
    while queue:
        t, via = queue.popleft()
        for i, p in readers.get(t, []):
            comp = flat.components[i].comp
            if comp.kind in ("flipflop", "register"):
                sinks.append((i, comp.ports[p].name, via))
                continue
            if comp.kind == "pin" or i in seen_comps:
                continue
            seen_comps.add(i)
            fc = flat.components[i]
            for port, bits in zip(comp.ports, fc.threads):
                if port.direction in ("output", "inout"):
                    for b in bits:
                        if b not in seen_threads:
                            seen_threads.add(b)
                            queue.append((b, True))
    return sinks


def _port_threads(flat: FlatCircuit, i: int, name: str) -> list[int]:
    fc = flat.components[i]
    for port, bits in zip(fc.comp.ports, fc.threads):
        if port.name == name:
            return bits
    return []


def _name_elements(project: ProjectNetlist, flat: FlatCircuit, elements: list[StateElement]) -> None:
    """FF label > output pin on the Q net > tunnel label on the Q net (top level) > z1..zk."""
    top = project.circuit(flat.top)
    out_by_thread = {threads[0]: pin.name for pin, threads in flat.outputs if len(threads) == 1}
    used: set[str] = set()
    for e in elements:
        comp = flat.components[e.index].comp
        name = comp.label.strip()
        if not name and e.bits == 1:
            q = _port_threads(flat, e.index, "q")
            name = out_by_thread.get(q[0], "") if q else ""
        if not name and e.path == flat.top:
            port = next((p for p in comp.ports if p.name == "q"), None)
            if port is not None and (comp.id, port.index) in top.port_net:
                tunnels = top.net_of((comp.id, port.index)).tunnels
                name = min(tunnels) if tunnels else ""
        if name and name not in used:
            e.name, e.named = name, True
            used.add(name)
    if all(e.named for e in elements):
        elements.sort(key=lambda e: _natural_key(e.name))
        return
    elements.sort(key=lambda e: (e.path, flat.components[e.index].comp.loc.y, flat.components[e.index].comp.loc.x))
    k = 0
    for e in elements:
        if not e.named:
            k += 1
            while f"z{k}" in used:
                k += 1
            e.name = f"z{k}"
            used.add(e.name)


def find_structure(project: ProjectNetlist, circuit: str | None = None) -> Extraction:
    """Locate state elements, clocks and the role of every input pin."""
    flat = flatten(project, circuit)
    warnings: list[str] = []
    elements: list[StateElement] = []
    for i, fc in enumerate(flat.components):
        comp = fc.comp
        if comp.name in FF_KIND and comp.lib is not None:
            bits = int(comp.attrs.get("width") or 8) if comp.name == "Register" else 1
            elements.append(StateElement(i, FF_KIND[comp.name], "", fc.path, comp.describe(),
                                         str(comp.attrs.get("trigger", "rising")), bits))
        elif comp.name in _NOT_SIMULATED_STATE and comp.lib is not None:
            warnings.append(f"{comp.describe()} in {fc.path}: state element not supported by the FSM extractor "
                            "(its contents are not part of the state)")
    if not elements:
        if classify(project.circuit(circuit)).comb_loops:
            raise SeqNotApplicable("no flip-flops or registers; asynchronous feedback loops (latches built from "
                                   "gates) are not supported by the FSM analysis")
        raise SeqNotApplicable("no flip-flops or registers: the circuit is not a synchronous sequential circuit")
    _name_elements(project, flat, elements)
    readers = _readers(flat)
    clock_comps = [i for i, fc in enumerate(flat.components) if fc.comp.kind == "clock"]

    pins: list[PinRole] = []
    for pin, threads in flat.inputs:
        sinks = _reach(flat, readers, threads)
        roles = {("clock" if port == "clock" else "async" if port in ASYNC_PORTS else "data") for _, port, _ in sinks}
        reaches_logic_out = _reaches_output(flat, readers, threads)
        via = any(v for _, port, v in sinks if port == "clock")
        if roles == {"clock"}:
            role = "clock"
        elif roles == {"async"}:
            role = "async"
        else:
            role = "data"
            if "clock" in roles:
                warnings.append(f"input {pin.name} reaches both flip-flop data and clock inputs (gated clock); "
                                "it is treated as a data input and the extraction may be wrong")
        if role != "data" and reaches_logic_out:
            warnings.append(f"input {pin.name} ({role}) also drives outputs; it is held at "
                            f"{'the clock level' if role == 'clock' else '0'} for the FSM")
        pins.append(PinRole(pin.name, pin.width, role, via))
        if role == "clock" and via:
            warnings.append(f"gated clock: input {pin.name} reaches clock inputs through logic")
        if role == "async":
            targets = sorted({f"{port} of {_elem_name(elements, i)}" for i, port, _ in sinks})
            warnings.append(f"asynchronous set/reset used: input {pin.name} drives {', '.join(targets)}; "
                            "held at 0 (inactive) for the FSM")

    # clock sources per element
    sources: dict[int, list[str]] = {e.index: [] for e in elements}
    for c in clock_comps:
        fc = flat.components[c]
        for i, port, via in _reach(flat, readers, fc.threads[0]):
            if port == "clock" and i in sources:
                sources[i].append(fc.comp.label or fc.comp.describe())
                if via:
                    warnings.append(f"gated clock: {fc.comp.label or 'clock'} reaches the clock of "
                                    f"{_elem_name(elements, i)} through logic")
    for (pin, threads), pin_role in zip(flat.inputs, pins):
        if pin_role.role == "clock":
            for i, port, _ in _reach(flat, readers, threads):
                if port == "clock" and i in sources:
                    sources[i].append(pin.name)
    all_sources = sorted({s for v in sources.values() for s in v})
    if len(all_sources) > 1:
        warnings.append(f"multiple clocks: {', '.join(all_sources)} (all are toggled together for the FSM)")
    for e in elements:
        if not sources[e.index]:
            warnings.append(f"{e.name} ({e.describe}) has no clock source (no Clock component or clock pin "
                            "reaches it); it never changes")
        if e.trigger in ("high", "low"):
            warnings.append(f"{e.name} is level-triggered ({e.trigger}); treated as one full clock period")
    triggers = {e.trigger for e in elements}
    if len(triggers) > 1:
        warnings.append(f"mixed clock triggers ({', '.join(sorted(triggers))}); one period = rise then fall")
    for e in elements:
        fc = flat.components[e.index]
        for comp_port, conn in zip(fc.comp.ports, fc.connected):
            if comp_port.name in ASYNC_PORTS and conn:
                drivers = _async_driven_by_pins(flat, readers, pins, e.index, comp_port.name)
                if not drivers:
                    warnings.append(f"asynchronous {comp_port.name} of {e.name} is driven by internal logic "
                                    "(simulated, but not a clean synchronous FSM)")
    return Extraction(flat.top, flat, elements, pins, clock_comps, warnings)


def _elem_name(elements: list[StateElement], index: int) -> str:
    return next((e.name for e in elements if e.index == index), str(index))


def _reaches_output(flat: FlatCircuit, readers: dict[int, list[tuple[int, int]]], start: list[int]) -> bool:
    outs = {t for _, threads in flat.outputs for t in threads}
    seen, queue = set(start), deque(start)
    while queue:
        t = queue.popleft()
        if t in outs:
            return True
        for i, _ in readers.get(t, []):
            fc = flat.components[i]
            if fc.comp.kind in ("flipflop", "register", "pin"):
                continue
            for port, bits in zip(fc.comp.ports, fc.threads):
                if port.direction in ("output", "inout"):
                    for b in bits:
                        if b not in seen:
                            seen.add(b)
                            queue.append(b)
    return False


def _async_driven_by_pins(flat: FlatCircuit, readers: dict[int, list[tuple[int, int]]], pins: list[PinRole],
                          index: int, port: str) -> bool:
    for (pin, threads), role in zip(flat.inputs, pins):
        if role.role == "async" and any(i == index and p == port for i, p, _ in _reach(flat, readers, threads)):
            return True
    return False


# ------------------------------------------------------------------ simulation runner
class Runner:
    """Drives a :class:`SequentialSimulator` in FSM terms (state codes / input codes, MSB-first strings)."""

    def __init__(self, project: ProjectNetlist, ex: Extraction) -> None:
        self.ex = ex
        self.seq = SequentialSimulator(ex.flat, SimContext(project.gate_undefined_error))
        self.sim = self.seq.sim
        self.clock_level = 0
        self.data_code = "0" * len(ex.input_names)
        self.async_level = 0

    # inputs
    def _pin_values(self) -> list[Value]:
        values: list[Value] = []
        pos = 0
        for role in self.ex.pins:
            if role.role == "data":
                bits = self.data_code[pos:pos + role.width]
                pos += role.width
                values.append(from_int(int(bits, 2) if bits else 0, role.width))
            elif role.role == "clock":
                values.append(from_int(self.clock_level, role.width))
            else:
                values.append(from_int(-1 if self.async_level else 0, role.width))
        return values

    def power_on(self) -> None:
        """Fresh Logisim state: flip-flops 0, clocks low, data inputs 0, async controls inactive."""
        self.seq.reset()
        self.clock_level = 0
        self.data_code = "0" * len(self.ex.input_names)
        self.async_level = 0
        self.seq.set_inputs(self._pin_values())

    def set_inputs(self, code: str) -> None:
        self.data_code = code
        self.seq.set_inputs(self._pin_values())

    def set_async(self, level: int) -> None:
        self.async_level = level
        self.seq.set_inputs(self._pin_values())

    def force_state(self, code: str) -> None:
        pos = 0
        for e in self.ex.elements:
            bits = code[pos:pos + e.bits]
            pos += e.bits
            if e.kind == "REG":
                self.sim.poke(e.index, "value", int(bits, 2))
            else:
                self.sim.poke(e.index, "q", ONE if bits == "1" else ZERO)
        self.sim.propagate()

    def _set_clock(self, level: int) -> None:
        self.clock_level = level
        lvl = ONE if level else ZERO
        for i in self.ex.clock_comps:
            self.sim.poke(i, "value", lvl)
        self.seq.clock_level = lvl
        self.seq.set_inputs(self._pin_values())

    def clock(self) -> None:
        """One full period: rise, then fall."""
        self._set_clock(1)
        self._set_clock(0)

    def state(self) -> str:
        out = []
        for e in self.ex.elements:
            st = self.sim.state[e.index]
            if e.kind == "REG":
                out.append(to_str(from_int(st.get("value", 0), e.bits)))
            else:
                out.append("1" if st.get("q", ZERO) == ONE else "0")
        return "".join(out)

    def outputs(self) -> tuple[str, ...]:
        return tuple(self.sim.read_outputs())

    def ff_inputs(self) -> dict[str, dict[str, str]]:
        """Current values on the data inputs of every flip-flop: {state var: {port: bit}}."""
        out: dict[str, dict[str, str]] = {}
        for e in self.ex.elements:
            if e.kind == "REG":
                v = self.sim.port_value(e.index, 1)
                for b, name in zip(range(e.bits - 1, -1, -1), e.var_names()):
                    out[name] = {"d": v[b] if b < len(v) else "x"}
                continue
            ports = {p.name: p.index for p in self.ex.flat.components[e.index].comp.ports}
            out[e.name] = {p: self.sim.port_value(e.index, ports[p])[0] for p in FF_DATA_PORTS[e.kind]}
        return out

    @property
    def oscillating(self) -> bool:
        return self.sim.oscillating

    def evaluate(self, state: str, inputs: str) -> tuple[tuple[str, ...], str, dict[str, dict[str, str]], bool]:
        """(outputs before the edge, next state, flip-flop inputs, forced state held) for one pair."""
        self.power_on()
        self.data_code = inputs
        self.seq.set_inputs(self._pin_values())
        self.force_state(state)
        held = self.state() == state
        outs, ffin = self.outputs(), self.ff_inputs()
        self.clock()
        return outs, self.state(), ffin, held


# ------------------------------------------------------------------ FSM construction
def _codes(n: int) -> list[str]:
    return [format(i, f"0{n}b") if n else "" for i in range(1 << n)]


def extract_fsm(project: ProjectNetlist, circuit: str | None = None, *,
                max_state_bits: int = MAX_STATE_BITS, max_input_bits: int = MAX_INPUT_BITS,
                max_combinations: int = MAX_COMBINATIONS, state_names: dict[str, str] | None = None,
                naming: str = "code") -> FSM:
    """Build the FSM of ``circuit`` (default main) by simulation; see module docstring."""
    ex = find_structure(project, circuit)
    k, m = len(ex.state_vars), len(ex.input_names)
    if k > max_state_bits:
        raise SeqTooLarge(f"not supported: too large ({k} state bits > {max_state_bits})")
    if m > max_input_bits:
        raise SeqTooLarge(f"not supported: too large ({m} input bits > {max_input_bits})")
    runner = Runner(project, ex)
    warnings = list(ex.warnings)
    loops = classify(project.circuit(circuit)).comb_loops
    if loops:
        warnings.append(f"{len(loops)} asynchronous feedback loop(s) outside flip-flops; the FSM covers only "
                        "flip-flop state")

    initial = "0" * k
    inputs = _codes(m)
    delta: dict[tuple[str, str], str] = {}
    lam: dict[tuple[str, str], tuple[str, ...]] = {}
    ffin: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    unstable: set[str] = set()
    osc: set[tuple[str, str]] = set()

    def visit(s: str) -> None:
        for x in inputs:
            outs, nxt, f, held = runner.evaluate(s, x)
            if runner.oscillating:
                osc.add((s, x))
            if not held:
                unstable.add(s)
            delta[(s, x)], lam[(s, x)], ffin[(s, x)] = nxt, outs, f

    complete = (1 << (k + m)) <= max_combinations
    if complete:
        states = _codes(k)
        for s in states:
            visit(s)
    else:
        states, queue, seen = [], deque([initial]), {initial}
        while queue:
            s = queue.popleft()
            states.append(s)
            if len(states) * len(inputs) > max_combinations:
                raise SeqTooLarge(f"not supported: too large (more than {max_combinations} reachable "
                                  "state/input pairs)")
            visit(s)
            for x in inputs:
                if delta[(s, x)] not in seen:
                    seen.add(delta[(s, x)])
                    queue.append(delta[(s, x)])
        states.sort()
        warnings.append(f"{k + m} state+input bits: only the {len(states)} states reachable from the initial "
                        "state were enumerated")
    if unstable:
        warnings.append("forced state not stable before the clock edge (asynchronous set/reset from logic?) "
                        f"in: {', '.join(sorted(unstable))}")
    if osc:
        warnings.append(f"oscillation while evaluating {len(osc)} state/input pair(s)")

    reset_state = None
    if any(p.role == "async" for p in ex.pins):
        runner.power_on()
        runner.set_async(1)
        reset_state = runner.state()
        runner.set_async(0)

    names = dict(state_names or {})
    for s in states:
        if s not in names:
            names[s] = f"S{int(s, 2)}" if naming == "index" and s else (s or "S")
    fsm = FSM(state_vars=ex.state_vars, ff_kinds=ex.ff_kinds, inputs=ex.input_names, outputs=ex.output_names,
              states=states, delta=delta, lam=lam, kind="moore", initial=initial, names=names,
              warnings=warnings, reset_state=reset_state, ff_inputs=ffin, complete=complete,
              circuit=ex.circuit, async_inputs=[p.name for p in ex.pins if p.role == "async"],
              clock_inputs=[p.name for p in ex.pins if p.role == "clock"],
              clock_sources=[ex.flat.components[i].comp.label or "clock" for i in ex.clock_comps])
    fsm.kind = fsm.detect_kind()
    return fsm


__all__ = ["MAX_INPUT_BITS", "MAX_STATE_BITS", "Extraction", "Runner", "SeqNotApplicable", "SeqTooLarge",
           "StateElement", "extract_fsm", "find_structure"]
