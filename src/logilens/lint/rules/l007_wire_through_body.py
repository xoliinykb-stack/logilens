"""L007 — wire passing through a component body (WARNING), using Logisim ``getOffsetBounds``.

Wires ending at one of the component's own ports are skipped (they legitimately reach into the body, e.g. a
plain input next to a negated one).
"""

from __future__ import annotations

from collections.abc import Iterator

from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    for comp in circ.components:
        if comp.bounds is None:
            continue
        own = {p.loc for p in comp.ports}
        for w in circ.wires:
            if w.a in own or w.b in own:
                continue
            if comp.bounds.segment_crosses_interior(w.a, w.b):
                yield ctx.issue(RULE, loc=comp.loc, component=comp, related=[w.a, w.b],
                                params={"wire": f"{w.a}-{w.b}"})


RULE = Rule("L007", Severity.WARNING, "wire through component body", check)
