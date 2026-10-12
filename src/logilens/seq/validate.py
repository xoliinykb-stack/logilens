"""Cross-check an extracted FSM against a backend ``trace`` (the Java backend = the real Logisim engine).

A walk from the power-on state covers every reachable transition (greedy: take an unused transition, else go
to the nearest state that still has one), optionally followed by random steps. Each step is replayed as a
backend script (set inputs, clock high, clock low) and every observed output row is compared with λ of the FSM.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from logilens.core.netlist import ProjectNetlist
from logilens.seq.analysis import reachable_from
from logilens.seq.extract import Extraction
from logilens.seq.fsm import FSM


@dataclass
class CrossCheck:
    backend: str
    walk: list[str]  # input codes
    covered: int
    total: int
    compared: int = 0
    mismatches: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.mismatches and not self.note and self.covered == self.total


def covering_walk(fsm: FSM, extra: int = 0, seed: int = 0) -> list[str]:
    """Input codes whose run from the initial state uses every reachable transition at least once."""
    rng = random.Random(seed)
    xs = fsm.input_codes
    reach = reachable_from(fsm, fsm.initial)
    todo = {(s, x) for s in reach for x in xs}
    walk: list[str] = []
    s = fsm.initial
    while todo:
        options = [x for x in xs if (s, x) in todo]
        if options:
            x = rng.choice(options)
        else:
            path = _path_to_todo(fsm, s, todo)
            if path is None:
                break
            x = path[0]
        todo.discard((s, x))
        walk.append(x)
        s = fsm.delta[(s, x)]
    for _ in range(extra):
        walk.append(rng.choice(xs))
    return walk


def _path_to_todo(fsm: FSM, start: str, todo: set[tuple[str, str]]) -> list[str] | None:
    pending = {s for s, _ in todo}
    prev: dict[str, tuple[str, str] | None] = {start: None}
    queue = deque([start])
    while queue:
        s = queue.popleft()
        if s in pending and s != start:
            path: list[str] = []
            while prev[s] is not None:
                p, x = prev[s]  # type: ignore[misc]
                path.append(x)
                s = p
            return path[::-1]
        for x in fsm.input_codes:
            t = fsm.delta[(s, x)]
            if t not in prev:
                prev[t] = (s, x)
                queue.append(t)
    return None


def _pin_strings(ex: Extraction, code: str, clock: int) -> str:
    vals, pos = [], 0
    for role in ex.pins:
        if role.role == "data":
            vals.append(code[pos:pos + role.width])
            pos += role.width
        elif role.role == "clock":
            vals.append(str(clock) * role.width)
        else:
            vals.append("0" * role.width)
    return ",".join(vals)


def crosscheck(project: ProjectNetlist, fsm: FSM, ex: Extraction, *, backend: str = "java", extra: int = 20,
               seed: int = 0) -> CrossCheck:
    """Replay a covering walk with ``backends.select.trace`` and compare every output row with the FSM."""
    from logilens.backends.select import trace

    walk = covering_walk(fsm, extra, seed)
    reach = reachable_from(fsm, fsm.initial)
    total = len(reach) * len(fsm.input_codes)
    used = set()
    s = fsm.initial
    for x in walk:
        used.add((s, x))
        s = fsm.delta[(s, x)]
    result = CrossCheck(backend, walk, len(used), total)
    has_comp = bool(ex.clock_comps)
    has_pin = any(p.role == "clock" for p in ex.pins)
    if has_comp and has_pin:
        result.note = "both Clock components and clock pins: cannot replay simultaneous edges"
        return result
    steps: list[str] = []
    expected: list[tuple[str, ...]] = []
    s = fsm.initial
    for x in walk:
        nxt = fsm.delta[(s, x)]
        if ex.pins:  # a circuit without input pins cannot take an input step
            steps.append(_pin_strings(ex, x, 0))
            expected.append(fsm.lam[(s, x)])
        if has_comp:
            steps += ["t", "t"]
        else:
            steps += [_pin_strings(ex, x, 1), _pin_strings(ex, x, 0)]
        expected += [fsm.lam[(nxt, x)]] * 2
        s = nxt
    data = trace(project, steps, fsm.circuit or None, backend=backend)
    result.backend = str(data.get("backend", backend))
    rows = data["rows"]
    for i, (row, exp) in enumerate(zip(rows, expected)):
        got = tuple(str(v).replace(" ", "") for v in row["out"])
        result.compared += 1
        if got != exp:
            result.mismatches.append(f"step {i} ({steps[i]}): backend {','.join(got)}, FSM {','.join(exp)}")
    if len(rows) != len(expected):
        result.mismatches.append(f"backend returned {len(rows)} rows, expected {len(expected)}")
    return result
