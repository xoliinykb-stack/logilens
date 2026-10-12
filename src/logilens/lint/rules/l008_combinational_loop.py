"""L008 — combinational loop without a state element (WARNING): asynchronous feedback (latch / oscillator)."""

from __future__ import annotations

from collections.abc import Iterator

from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    for loop in ctx.classification.comb_loops:
        comps = [circ.components[i] for i in loop]
        yield ctx.issue(RULE, loc=comps[0].loc, component=comps[0], related=[c.loc for c in comps],
                        params={"count": len(comps), "members": ", ".join(c.describe() for c in comps)})


RULE = Rule("L008", Severity.WARNING, "combinational loop", check)
