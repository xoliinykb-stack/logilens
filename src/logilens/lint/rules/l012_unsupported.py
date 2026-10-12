"""L012 — unknown / unsupported component (WARNING); parsed-but-not-simulated parts are INFO."""

from __future__ import annotations

from collections.abc import Iterator

from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity
from logilens.sim.models import is_simulated


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    flagged = set()
    for item in ctx.project.unsupported:
        if item.circuit != circ.name or item.kind != "component":
            continue
        flagged.add((item.name, item.loc))
        comp = next((c for c in circ.components if c.name == item.name and c.loc == item.loc), None)
        yield ctx.issue(RULE, loc=item.loc, component=comp, params={"name": item.name, "reason": item.reason})
    for comp in circ.components:
        if (comp.name, comp.loc) in flagged or not comp.supported or comp.kind == "text":
            continue
        if not is_simulated(comp):
            yield ctx.issue(RULE, loc=comp.loc, component=comp, variant="sim", severity=Severity.INFO,
                            params={"name": comp.name})


RULE = Rule("L012", Severity.WARNING, "unsupported component", check)
