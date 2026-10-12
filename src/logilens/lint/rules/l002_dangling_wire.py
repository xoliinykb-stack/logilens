"""L002 — dangling wire end (WARNING): a wire endpoint touching no other wire and no port."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from logilens.core.geometry import on_segment
from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity
from logilens.parse.connectivity import WIRE_TOLERANCE, index_points


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    ports = {p.loc for c in circ.components for p in c.ports}
    ends = Counter(pt for w in circ.wires for pt in (w.a, w.b))
    by_x, by_y = index_points(ends)
    touched: set = set()
    for w in circ.wires:
        if w.vertical:
            cands = [p for x in range(w.a.x - WIRE_TOLERANCE, w.a.x + WIRE_TOLERANCE + 1) for p in by_x.get(x, ())]
        else:
            cands = [p for y in range(w.a.y - WIRE_TOLERANCE, w.a.y + WIRE_TOLERANCE + 1) for p in by_y.get(y, ())]
        for p in cands:
            if p not in (w.a, w.b) and on_segment(p, w.a, w.b, WIRE_TOLERANCE):
                touched.add(p)
    for w in circ.wires:
        for pt in (w.a, w.b):
            if ends[pt] == 1 and pt not in ports and pt not in touched:
                yield ctx.issue(RULE, loc=pt, related=[w.a, w.b], params={"wire": f"{w.a}-{w.b}"})


RULE = Rule("L002", Severity.WARNING, "dangling wire end", check)
