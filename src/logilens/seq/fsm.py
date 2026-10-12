"""Finite-state machine extracted from a clocked circuit.

States and input combinations are MSB-first bit strings over ``state_vars`` / ``inputs`` (the state *code*);
``names`` maps a code to its display name (the code itself unless the caller supplied names). ``lam`` holds
the outputs observed *before* the clock edge for every (state, input) pair; for a Moore machine they do not
depend on the input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FSM:
    state_vars: list[str]
    ff_kinds: list[str]  # per state variable: D | T | JK | SR | REG
    inputs: list[str]  # input bit names, MSB-first
    outputs: list[str]  # output pin names (values are Logisim strings, MSB-first)
    states: list[str]  # state codes in table order
    delta: dict[tuple[str, str], str]
    lam: dict[tuple[str, str], tuple[str, ...]]
    kind: str = "moore"  # moore | mealy
    initial: str = ""
    names: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reset_state: str | None = None  # state forced by asserting the asynchronous inputs (if any)
    ff_inputs: dict[tuple[str, str], dict[str, dict[str, str]]] = field(default_factory=dict)
    complete: bool = True  # every state code enumerated (False = only reachable ones)
    circuit: str = ""
    async_inputs: list[str] = field(default_factory=list)
    clock_inputs: list[str] = field(default_factory=list)
    clock_sources: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- accessors
    @property
    def input_codes(self) -> list[str]:
        m = len(self.inputs)
        return [format(i, f"0{m}b") if m else "" for i in range(1 << m)]

    def name(self, code: str) -> str:
        return self.names.get(code, code or "S")

    def code_of(self, name_or_code: str) -> str:
        """Accept a display name or a code."""
        if name_or_code in self.states:
            return name_or_code
        for code, n in self.names.items():
            if n == name_or_code:
                return code
        raise KeyError(name_or_code)

    def out_str(self, state: str, inp: str | None = None) -> str:
        """Outputs concatenated (``"100"``); for a Moore machine ``inp`` may be omitted."""
        if inp is None:
            inp = self.input_codes[0]
        return "".join(self.lam[(state, inp)])

    def moore_output(self, state: str) -> str:
        return self.out_str(state)

    def detect_kind(self) -> str:
        """Mealy when, for some state, the outputs differ between input combinations."""
        for s in self.states:
            if len({self.lam[(s, x)] for x in self.input_codes}) > 1:
                return "mealy"
        return "moore"

    def successors(self, state: str) -> list[str]:
        return [self.delta[(state, x)] for x in self.input_codes]

    def restricted(self, states: list[str]) -> FSM:
        """Copy keeping only ``states`` (their transitions must stay inside)."""
        keep = set(states)
        delta = {k: v for k, v in self.delta.items() if k[0] in keep}
        lam = {k: v for k, v in self.lam.items() if k[0] in keep}
        return FSM(self.state_vars, self.ff_kinds, self.inputs, self.outputs, [s for s in self.states if s in keep],
                   delta, lam, self.kind, self.initial, dict(self.names), list(self.warnings), self.reset_state,
                   {k: v for k, v in self.ff_inputs.items() if k[0] in keep}, False, self.circuit,
                   list(self.async_inputs), list(self.clock_inputs), list(self.clock_sources))

    # ------------------------------------------------------------- export
    def to_dict(self) -> dict[str, Any]:
        xs = self.input_codes
        return {
            "circuit": self.circuit,
            "kind": self.kind,
            "state_vars": list(self.state_vars),
            "ff_kinds": list(self.ff_kinds),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "initial": self.initial,
            "initial_name": self.name(self.initial),
            "reset_state": self.reset_state,
            "async_inputs": list(self.async_inputs),
            "clock_inputs": list(self.clock_inputs),
            "clock_sources": list(self.clock_sources),
            "complete": self.complete,
            "states": [{"code": s, "name": self.name(s)} for s in self.states],
            "transitions": [
                {"state": s, "input": x, "next": self.delta[(s, x)], "outputs": list(self.lam[(s, x)])}
                for s in self.states for x in xs],
            "warnings": list(self.warnings),
        }
