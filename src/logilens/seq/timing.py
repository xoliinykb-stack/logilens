"""Timing diagram for an input sequence, simulated from the power-on state.

Column ``t`` shows the state S(t), the input x(t) applied during that period and the outputs observed before
the next rising edge; the clock rises at the start of every column t >= 1, which moves S(t-1) -> S(t). The
last column shows the final state (inputs held). The simulation is the real Python simulator (not the
extracted table); the state trace is also checked against δ of the FSM.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from logilens.seq.extract import Runner
from logilens.seq.fsm import FSM

UNICODE = {"hi": "▔", "lo": "▁", "rise": "╱", "fall": "╲", "unk": "░", "bus": "╳", "start": "│", "sep": "│"}
ASCII = {"hi": "-", "lo": "_", "rise": "/", "fall": "\\", "unk": "x", "bus": "X", "start": "|", "sep": "|"}


def parse_sequence(seq: str | int | Sequence[str] | Sequence[Mapping[str, Any]], fsm: FSM) -> list[str]:
    """Input codes per step.

    * ``"0110 1011"``: whitespace/comma separated groups; each group of exactly ``len(inputs)`` bits is one
      step, otherwise all bits are concatenated and split into steps of ``len(inputs)`` bits;
    * a list of codes, or a list of ``{input name: 0/1}`` dicts (missing names keep their previous value);
    * an int = number of steps for a machine without inputs.
    """
    m = len(fsm.inputs)
    if isinstance(seq, int):
        if m:
            raise ValueError("a step count is only valid for a machine without inputs")
        return [""] * seq
    if isinstance(seq, str):
        tokens = [t for t in re.split(r"[\s,;]+", seq.strip()) if t]
        if m == 0:
            return [""] * len(tokens)
        if not all(len(t) == m for t in tokens):
            joined = "".join(tokens)
            if len(joined) % m:
                raise ValueError(f"input sequence has {len(joined)} bits, not a multiple of {m} "
                                 f"({', '.join(fsm.inputs)})")
            tokens = [joined[i:i + m] for i in range(0, len(joined), m)]
        codes = tokens
    else:
        codes = []
        cur = dict.fromkeys(fsm.inputs, "0")
        for item in seq:
            if isinstance(item, Mapping):
                for k, v in item.items():
                    if k not in cur:
                        raise ValueError(f"unknown input {k!r} (inputs: {', '.join(fsm.inputs)})")
                    cur[k] = str(int(v))
                codes.append("".join(cur[n] for n in fsm.inputs))
            else:
                codes.append(str(item).replace(" ", ""))
    for c in codes:
        if len(c) != m or any(ch not in "01" for ch in c):
            raise ValueError(f"bad input step {c!r}: expected {m} bits of 0/1 ({', '.join(fsm.inputs)})")
    return codes


@dataclass
class Timing:
    inputs: list[str]  # x(0..N-1)
    states: list[str]  # S(0..N) codes (simulated)
    outputs: list[tuple[str, ...]]  # y(0..N)
    names: list[str]  # display names of states
    predicted: list[str]  # S(0..N) from δ
    fsm: FSM
    mismatches: list[str] = field(default_factory=list)

    @property
    def trace(self) -> str:
        """State trace like ``"S1 S1 S2 S3"``."""
        return " ".join(self.names)

    @property
    def output_trace(self) -> list[str]:
        return ["".join(o) for o in self.outputs]

    # ------------------------------------------------------------- rendering
    def _signals(self) -> list[tuple[str, str, list[str]]]:
        """(label, kind 'clk'|'bit'|'bus', values per column)."""
        n = len(self.states)
        sig: list[tuple[str, str, list[str]]] = [("clk", "clk", [""] * n)]
        for i, name in enumerate(self.fsm.inputs):
            sig.append((name, "bit", [x[i] for x in self.inputs] + [""]))
        for i, name in enumerate(self.fsm.state_vars):
            sig.append((name, "bit", [s[i] for s in self.states]))
        sig.append(("state", "bus", list(self.names)))
        state_rows = {name: [st[i] for st in self.states] for i, name in enumerate(self.fsm.state_vars)}
        for i, name in enumerate(self.fsm.outputs):
            vals = [o[i] for o in self.outputs]
            if state_rows.get(name) == vals:
                continue  # output pin that just shows a state variable
            sig.append((name, "bit" if all(len(v) == 1 for v in vals) else "bus", vals))
        return sig

    def _width(self) -> int:
        longest = max([len(n) for n in self.names] + [len(o) for out in self.outputs for o in out] + [2])
        return max(4, longest + 2)

    def lines(self, ascii_only: bool = False) -> list[tuple[str, str, str]]:
        """(label, waveform, kind) per signal plus a step header."""
        ch = ASCII if ascii_only else UNICODE
        w = self._width()
        out = [("t", "".join(str(t).ljust(w) for t in range(len(self.states))), "head")]
        for label, kind, vals in self._signals():
            cells = []
            for t, v in enumerate(vals):
                if kind == "clk":
                    if t == 0:
                        cells.append(ch["lo"] * w)
                    else:
                        h = max(1, (w - 2) // 2)
                        cells.append(ch["rise"] + ch["hi"] * h + ch["fall"] + ch["lo"] * (w - 2 - h))
                elif kind == "bit":
                    if v == "":
                        cells.append(" " * w)
                        continue
                    fill = ch["hi"] if v == "1" else ch["lo"] if v == "0" else ch["unk"]
                    prev = vals[t - 1] if t else v
                    first = fill
                    if t and prev in "01" and v in "01" and prev != v:
                        first = ch["rise"] if v == "1" else ch["fall"]
                    cells.append(first + fill * (w - 1))
                else:
                    prev = vals[t - 1] if t else None
                    first = ch["start"] if t == 0 else (ch["bus"] if v != prev else " ")
                    cells.append((first + v).ljust(w)[:w])
            out.append((label, "".join(cells), kind))
        return out

    def text(self, ascii_only: bool = False) -> str:
        rows = self.lines(ascii_only)
        lw = max(len(r[0]) for r in rows)
        sep = ASCII["sep"] if ascii_only else UNICODE["sep"]
        body = [f"{label.rjust(lw)} {sep} {wave.rstrip()}" for label, wave, _ in rows]
        body.append(f"{'trace'.rjust(lw)} {sep} {self.trace}")
        return "\n".join(body)

    def rich(self):  # type: ignore[no-untyped-def]
        """``rich.text.Text`` with colored rows."""
        from rich.text import Text

        styles = {"head": "dim", "clk": "bright_black", "bit": "cyan", "bus": "bold yellow"}
        rows = self.lines()
        lw = max(len(r[0]) for r in rows)
        outs = set(self.fsm.outputs)
        text = Text()
        for label, wave, kind in rows:
            style = "green" if label in outs else styles[kind]
            text.append(f"{label.rjust(lw)} │ ", style="bold")
            text.append(wave.rstrip() + "\n", style=style)
        text.append(f"{'trace'.rjust(lw)} │ ", style="bold")
        text.append(self.trace, style="bold yellow")
        return text

    def to_dict(self) -> dict[str, Any]:
        return {"inputs": list(self.inputs), "states": list(self.states), "names": list(self.names),
                "outputs": [list(o) for o in self.outputs], "trace": self.trace,
                "predicted": list(self.predicted), "mismatches": list(self.mismatches),
                "diagram": self.text()}


def simulate_timing(runner: Runner, fsm: FSM, steps: list[str]) -> Timing:
    """Run ``steps`` from power-on in the real simulator; compare with δ."""
    runner.power_on()
    states = [runner.state()]
    outputs: list[tuple[str, ...]] = []
    for x in steps:
        runner.set_inputs(x)
        outputs.append(runner.outputs())
        runner.clock()
        states.append(runner.state())
    outputs.append(runner.outputs())
    predicted = [fsm.initial]
    for x in steps:
        s = predicted[-1]
        predicted.append(fsm.delta.get((s, x), "?"))
    mismatches = [f"step {t}: simulated {fsm.name(a)}, table {fsm.name(b)}"
                  for t, (a, b) in enumerate(zip(states, predicted)) if a != b]
    return Timing(list(steps), states, outputs, [fsm.name(s) for s in states], predicted, fsm, mismatches)
