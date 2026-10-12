"""L013 — ports of different bit widths on one net (ERROR; Logisim: "Incompatible widths")."""

from __future__ import annotations

from collections.abc import Iterator

from logilens.core.geometry import Point
from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    for net in circ.nets:
        if not net.width_conflict:
            continue
        parts = []
        related: list[Point] = []
        for width, refs in sorted(net.widths.items()):
            names = ", ".join(circ.components[c].describe() for c, _ in refs[:4])
            parts.append(f"{width} bit: {names}")
            related.extend(circ.port(r).loc for r in refs)
        yield ctx.issue(RULE, loc=net.points[0], related=related, params={"widths": "; ".join(parts)})


RULE = Rule("L013", Severity.ERROR, "bit-width mismatch", check)
