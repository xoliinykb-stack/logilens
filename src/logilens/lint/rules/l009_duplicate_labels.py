"""L009 — several pins with the same label (ERROR). Logisim's analyzer silently renames them (a, a2, ...)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    pins = circ.inputs + circ.outputs
    groups = defaultdict(list)
    for p in pins:
        if p.label.strip():
            groups[p.label.strip()].append(p)
    for label, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        members.sort(key=lambda p: (p.loc.y, p.loc.x))
        comp = circ.components[members[0].comp_id]
        yield ctx.issue(RULE, loc=members[0].loc, component=comp, related=[p.loc for p in members],
                        params={"label": label, "count": len(members),
                                "renamed": ", ".join(p.name for p in members)})


RULE = Rule("L009", Severity.ERROR, "duplicate pin labels", check)
