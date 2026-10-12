"""State minimization by partition refinement (Moore/Mealy equivalence).

The initial partition groups states with the same output row (Moore: the state output; Mealy: the outputs for
every input combination). Each round splits blocks whose members go to different blocks for some input, until
nothing changes. By default only states reachable from the initial state take part.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logilens.seq.analysis import reachable_from
from logilens.seq.fsm import FSM


@dataclass
class Minimization:
    classes: list[list[str]]  # state codes per equivalence class (class order = first appearance)
    rounds: list[list[list[str]]] = field(default_factory=list)  # partition after each refinement round
    original_count: int = 0
    outputs_used: list[str] = field(default_factory=list)

    @property
    def minimal_count(self) -> int:
        return len(self.classes)

    @property
    def is_minimal(self) -> bool:
        return self.minimal_count == self.original_count

    def class_of(self, state: str) -> int:
        return next(i for i, c in enumerate(self.classes) if state in c)

    def to_dict(self, fsm: FSM | None = None) -> dict[str, Any]:
        name = (lambda s: fsm.name(s)) if fsm is not None else (lambda s: s)
        return {
            "original_count": self.original_count,
            "minimal_count": self.minimal_count,
            "is_minimal": self.is_minimal,
            "classes": [[name(s) for s in c] for c in self.classes],
            "rounds": [[[name(s) for s in c] for c in p] for p in self.rounds],
            "outputs_used": list(self.outputs_used),
        }


def minimize_states(fsm: FSM, states: list[str] | None = None, outputs: list[str] | None = None) -> Minimization:
    """Equivalence classes of ``states`` (default: reachable from the initial state).

    ``outputs`` limits the outputs that distinguish states (default: all output pins).
    """
    if states is None:
        states = reachable_from(fsm, fsm.initial)
    xs = fsm.input_codes
    idx = [fsm.outputs.index(o) for o in outputs] if outputs else list(range(len(fsm.outputs)))

    def out_row(s: str) -> tuple[tuple[str, ...], ...]:
        rows = [tuple(fsm.lam[(s, x)][i] for i in idx) for x in xs]
        return tuple(rows[:1]) if fsm.kind == "moore" else tuple(rows)

    block: dict[str, int] = {}
    keys: dict[object, int] = {}
    for s in states:
        block[s] = keys.setdefault(out_row(s), len(keys))
    rounds = [_partition(states, block)]
    sset = set(states)
    while True:
        keys = {}
        new = {}
        for s in states:
            sig = (block[s], tuple(block[fsm.delta[(s, x)]] if fsm.delta[(s, x)] in sset else -1 for x in xs))
            new[s] = keys.setdefault(sig, len(keys))
        changed = len(set(new.values())) != len(set(block.values()))
        block = new
        if not changed:
            break
        rounds.append(_partition(states, block))
    return Minimization(_partition(states, block), rounds, len(states),
                        [fsm.outputs[i] for i in idx])


def _partition(states: list[str], block: dict[str, int]) -> list[list[str]]:
    groups: dict[int, list[str]] = {}
    for s in states:
        groups.setdefault(block[s], []).append(s)
    return list(groups.values())


def reduced_fsm(fsm: FSM, mini: Minimization) -> FSM:
    """Quotient machine: one state per class, represented by its first member (the initial state's class keeps
    the initial state as representative)."""
    reps = []
    for c in mini.classes:
        reps.append(fsm.initial if fsm.initial in c else c[0])
    rep_of = {s: reps[i] for i, c in enumerate(mini.classes) for s in c}
    xs = fsm.input_codes
    delta = {(r, x): rep_of.get(fsm.delta[(r, x)], fsm.delta[(r, x)]) for r in reps for x in xs}
    lam = {(r, x): fsm.lam[(r, x)] for r in reps for x in xs}
    names = {}
    for i, c in enumerate(mini.classes):
        names[reps[i]] = fsm.name(reps[i]) if len(c) == 1 else "{" + ",".join(fsm.name(s) for s in c) + "}"
    out = fsm.restricted(reps)
    out.delta, out.lam, out.names = delta, lam, names
    out.ff_inputs = {}
    return out
