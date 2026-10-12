"""Flip-flop excitation tables and per-flip-flop input functions (ON/OFF/DC, ready for K-maps).

Excitation table: for a transition Qn -> Qn+1, the values each flip-flop input must have ('X' = don't care).
Input functions are over the variables ``state_vars + inputs`` (MSB-first, minterm convention of
``core/logic_types``); codes of unused / unreachable states are don't cares.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from logilens.core.logic_types import BoolFunction, MultiFunction
from logilens.logic.truth_table import function_from_sets, value_char
from logilens.seq.fsm import FSM

PORTS: dict[str, tuple[str, ...]] = {"D": ("D",), "T": ("T",), "JK": ("J", "K"), "SR": ("S", "R"), "REG": ("D",)}

EXCITATION: dict[str, dict[tuple[str, str], tuple[str, ...]]] = {
    "D": {("0", "0"): ("0",), ("0", "1"): ("1",), ("1", "0"): ("0",), ("1", "1"): ("1",)},
    "T": {("0", "0"): ("0",), ("0", "1"): ("1",), ("1", "0"): ("1",), ("1", "1"): ("0",)},
    "JK": {("0", "0"): ("0", "X"), ("0", "1"): ("1", "X"), ("1", "0"): ("X", "1"), ("1", "1"): ("X", "0")},
    "SR": {("0", "0"): ("0", "X"), ("0", "1"): ("1", "0"), ("1", "0"): ("0", "1"), ("1", "1"): ("X", "0")},
}
EXCITATION["REG"] = EXCITATION["D"]


def excite(kind: str, q: str, qn: str) -> dict[str, str]:
    """Required inputs of a ``kind`` flip-flop for the transition ``q -> qn``."""
    return dict(zip(PORTS[kind], EXCITATION[kind][(q, qn)]))


def excitation_table_text(kind: str) -> str:
    ports = PORTS[kind]
    lines = ["Qn Qn+1 │ " + " ".join(ports), "────────┼─" + "─" * (2 * len(ports) - 1)]
    for (q, qn), vals in EXCITATION[kind].items():
        lines.append(f"{q}  {qn}    │ " + " ".join(vals))
    return "\n".join(lines)


def _fn(n: int, on: int, dc: int) -> BoolFunction:
    return function_from_sets(n, on, dc)


def next_state_functions(codes: Mapping[str, str], delta: Mapping[tuple[str, str], str], input_codes: list[str],
                         state_names: list[str], input_names: list[str], kinds: list[str],
                         care: set[str] | None = None) -> MultiFunction:
    """Flip-flop input functions for an encoding ``codes`` (state -> code bits, MSB-first).

    Outputs are named ``<PORT>_<state var>`` (``D_z1``, ``J_z2``, ...).
    """
    k, m = len(state_names), len(input_names)
    n = k + m
    inv = {c: s for s, c in codes.items() if care is None or s in care}
    names = [f"{p}_{v}" for v, kind in zip(state_names, kinds) for p in PORTS[kind]]
    on = dict.fromkeys(names, 0)
    dc = dict.fromkeys(names, 0)
    for mt in range(1 << n):
        bits = format(mt, f"0{n}b") if n else ""
        s = inv.get(bits[:k])
        x = bits[k:]
        if s is None:
            for nm in names:
                dc[nm] |= 1 << mt
            continue
        nxt = codes[delta[(s, x)]]
        for i, (v, kind) in enumerate(zip(state_names, kinds)):
            for p, val in excite(kind, bits[i], nxt[i]).items():
                nm = f"{p}_{v}"
                if val == "1":
                    on[nm] |= 1 << mt
                elif val == "X":
                    dc[nm] |= 1 << mt
    return MultiFunction(tuple(state_names) + tuple(input_names), tuple(names),
                         {nm: _fn(n, on[nm], dc[nm]) for nm in names})


def output_bit_names(fsm: FSM) -> list[str]:
    """Output pins split into bits (``y`` or ``y1, y0`` for a 2-bit pin)."""
    widths = _output_widths(fsm)
    out = []
    for name, w in zip(fsm.outputs, widths):
        out += [name] if w == 1 else [f"{name}{b}" for b in range(w - 1, -1, -1)]
    return out


def _output_widths(fsm: FSM) -> list[int]:
    any_key = next(iter(fsm.lam))
    return [len(v) for v in fsm.lam[any_key]]


def output_functions(fsm: FSM, codes: Mapping[str, str], state_names: list[str],
                     care: set[str] | None = None) -> MultiFunction:
    """Output functions over ``state_names + inputs`` for an encoding (floating/error outputs = DC)."""
    k, m = len(state_names), len(fsm.inputs)
    n = k + m
    inv = {c: s for s, c in codes.items() if care is None or s in care}
    names = output_bit_names(fsm)
    on = dict.fromkeys(names, 0)
    dc = dict.fromkeys(names, 0)
    for mt in range(1 << n):
        bits = format(mt, f"0{n}b") if n else ""
        s = inv.get(bits[:k])
        if s is None:
            for nm in names:
                dc[nm] |= 1 << mt
            continue
        flat = "".join(fsm.lam[(s, bits[k:])])
        for nm, ch in zip(names, flat):
            if ch == "1":
                on[nm] |= 1 << mt
            elif ch != "0":
                dc[nm] |= 1 << mt
    return MultiFunction(tuple(state_names) + tuple(fsm.inputs), tuple(names),
                         {nm: _fn(n, on[nm], dc[nm]) for nm in names})


@dataclass
class ExcitationRow:
    state: str
    input: str
    next: str
    required: dict[str, str]  # "J_z1" -> '0' | '1' | 'X'
    implemented: dict[str, str]  # values observed on the flip-flop inputs in the circuit


@dataclass
class Excitation:
    kinds: list[str]
    functions: MultiFunction  # required flip-flop inputs (with DC)
    implemented: MultiFunction | None  # what the circuit actually feeds the flip-flops (None if kinds differ)
    rows: list[ExcitationRow] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def fdict(mf: MultiFunction) -> dict[str, Any]:
            return {"variables": list(mf.inputs), "functions": {
                o: {"on": _minterms(mf.functions[o].on), "dc": _minterms(mf.functions[o].dc),
                    "values": "".join(value_char(mf.functions[o], mt) for mt in range(1 << mf.n))}
                for o in mf.outputs}}

        return {
            "kinds": list(self.kinds),
            "tables": {k: [{"q": q, "q_next": qn, "inputs": dict(zip(PORTS[k], v))}
                           for (q, qn), v in EXCITATION[k].items()] for k in sorted(set(self.kinds))},
            "required": fdict(self.functions),
            "implemented": fdict(self.implemented) if self.implemented is not None else None,
            "rows": [{"state": r.state, "input": r.input, "next": r.next, "required": r.required,
                      "implemented": r.implemented} for r in self.rows],
            "mismatches": list(self.mismatches),
        }


def _minterms(mask: int) -> list[int]:
    out, m = [], 0
    while mask:
        if mask & 1:
            out.append(m)
        mask >>= 1
        m += 1
    return out


def excitation_functions(fsm: FSM, kinds: list[str] | str | None = None, care: set[str] | None = None
                         ) -> Excitation:
    """Required flip-flop input functions for the current encoding.

    ``kinds``: one kind for all flip-flops, one per state variable, or None = the circuit's own kinds.
    ``care``: states whose rows are specified (default: all enumerated states; pass the reachable states to
    turn unreachable codes into don't cares).
    """
    if kinds is None:
        kinds = list(fsm.ff_kinds)
    elif isinstance(kinds, str):
        kinds = [kinds] * len(fsm.state_vars)
    kinds = ["D" if k == "REG" else k for k in kinds]
    care = set(fsm.states) if care is None else set(care)
    codes = {s: s for s in fsm.states}
    xs = fsm.input_codes
    mf = next_state_functions(codes, fsm.delta, xs, fsm.state_vars, fsm.inputs, kinds, care)
    rows: list[ExcitationRow] = []
    mismatches: list[str] = []
    same = [("D" if k == "REG" else k) for k in fsm.ff_kinds] == kinds and bool(fsm.ff_inputs)
    impl_on: dict[str, int] = dict.fromkeys(mf.outputs, 0)
    impl_dc: dict[str, int] = dict.fromkeys(mf.outputs, 0)
    k = len(fsm.state_vars)
    for s in fsm.states:
        for x in xs:
            nxt = fsm.delta[(s, x)]
            req: dict[str, str] = {}
            for i, (v, kind) in enumerate(zip(fsm.state_vars, kinds)):
                for p, val in excite(kind, s[i], nxt[i]).items():
                    req[f"{p}_{v}"] = val
            impl: dict[str, str] = {}
            for v, ports in (fsm.ff_inputs.get((s, x)) or {}).items():
                for p, val in ports.items():
                    impl[f"{p.upper()}_{v}"] = val
            rows.append(ExcitationRow(s, x, nxt, req, impl))
            if not same:
                continue
            mt = int(s + x, 2) if (k + len(fsm.inputs)) else 0
            for nm in mf.outputs:
                val = impl.get(nm, "x")
                if val == "1":
                    impl_on[nm] |= 1 << mt
                elif val != "0":
                    impl_dc[nm] |= 1 << mt
                if s in care and req[nm] != "X" and val != req[nm]:
                    mismatches.append(f"{nm} at state {fsm.name(s)}, input {x or '-'}: circuit {val}, "
                                      f"required {req[nm]}")
    implemented = None
    if same:
        n = mf.n
        full = (1 << (1 << n)) - 1
        enumerated = 0
        for s in fsm.states:
            for x in xs:
                enumerated |= 1 << (int(s + x, 2) if n else 0)
        implemented = MultiFunction(mf.inputs, mf.outputs, {
            nm: _fn(n, impl_on[nm] & ~impl_dc[nm], (impl_dc[nm] | (full & ~enumerated)) & ~impl_on[nm])
            for nm in mf.outputs})
    return Excitation(kinds, mf, implemented, rows, mismatches)
