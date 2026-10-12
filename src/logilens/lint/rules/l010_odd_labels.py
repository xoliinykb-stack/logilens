"""L010 — inconsistent or odd labels (INFO): whitespace, non-identifiers, case-only differences, lonely tunnels."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity
from logilens.parse.connectivity import to_valid_label


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    by_lower = defaultdict(set)
    for p in circ.inputs + circ.outputs:
        comp = circ.components[p.comp_id]
        label = p.label
        if not label.strip():
            continue
        by_lower[label.strip().lower()].add(label.strip())
        if label != label.strip():
            yield ctx.issue(RULE, loc=p.loc, component=comp, variant="space", params={"label": label})
        valid = to_valid_label(label)
        if valid != label.strip():
            yield ctx.issue(RULE, loc=p.loc, component=comp, variant="invalid", params={"label": label, "valid": valid})
    for variants in by_lower.values():
        if len(variants) > 1:
            labels = sorted(variants)
            pins = [p for p in circ.inputs + circ.outputs if p.label.strip() in variants]
            yield ctx.issue(RULE, loc=pins[0].loc, variant="case", related=[p.loc for p in pins],
                            params={"labels": ", ".join(repr(s) for s in labels)})
    tunnels = defaultdict(list)
    for c in circ.components:
        if c.kind == "tunnel" and c.label.strip():
            tunnels[c.label.strip()].append(c)
    for label, comps in sorted(tunnels.items()):
        if len(comps) == 1:
            yield ctx.issue(RULE, loc=comps[0].loc, component=comps[0], variant="tunnel", params={"label": label})


RULE = Rule("L010", Severity.INFO, "inconsistent labels", check)
