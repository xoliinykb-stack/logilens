"""L014 — input/output pin without a label (WARNING)."""

from __future__ import annotations

from collections.abc import Iterator

from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    for p in circ.inputs + circ.outputs:
        if not p.label.strip():
            yield ctx.issue(RULE, loc=p.loc, component=circ.components[p.comp_id],
                            params={"direction": "input" if p.is_input else "output", "name": p.name})


RULE = Rule("L014", Severity.WARNING, "unlabeled I/O pin", check)
