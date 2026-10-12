"""L003 — gate output drives nothing (WARNING)."""

from __future__ import annotations

from collections.abc import Iterator

from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity

CHECKED = ("gate", "not", "buffer", "controlled")


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ, g = ctx.circuit, ctx.graph
    for comp in circ.components:
        if comp.kind not in CHECKED or not comp.ports:
            continue
        ref = (comp.id, 0)
        threads = circ.port_threads(ref)
        readers = {r for t in threads for r in g.thread_readers.get(t, []) if r[0] != comp.id}
        if not readers:
            yield ctx.issue(RULE, loc=comp.ports[0].loc, component=comp)


RULE = Rule("L003", Severity.WARNING, "gate output drives nothing", check)
