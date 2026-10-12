"""L006 — collinear wires overlapping by more than a point (WARNING). Logisim merges them into one net."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from logilens.core.netlist import Wire
from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity


def _span(w: Wire) -> tuple[int, int]:
    return (w.a.y, w.b.y) if w.vertical else (w.a.x, w.b.x)


def check(ctx: LintContext) -> Iterator[LintIssue]:
    lines: dict[tuple[bool, int], list[Wire]] = defaultdict(list)
    for w in ctx.circuit.wires:
        if w.a.x == w.b.x or w.a.y == w.b.y:
            lines[(w.vertical, w.a.x if w.vertical else w.a.y)].append(w)
    for key in sorted(lines):
        ws = sorted(lines[key], key=_span)
        for i, w1 in enumerate(ws):
            lo1, hi1 = _span(w1)
            for w2 in ws[i + 1:]:
                lo2, _ = _span(w2)
                if lo2 >= hi1:
                    break
                start = max(lo1, lo2)
                loc = w1.a.__class__(key[1], start) if key[0] else w1.a.__class__(start, key[1])
                yield ctx.issue(RULE, loc=loc, related=[w1.a, w1.b, w2.a, w2.b],
                                params={"first": f"{w1.a}-{w1.b}", "second": f"{w2.a}-{w2.b}"})


RULE = Rule("L006", Severity.WARNING, "overlapping wires", check)
