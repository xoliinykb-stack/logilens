"""L011 — gate-set restriction (ERROR), active only with ``only={...}`` (e.g. ``{"nand", "nor"}``).

Every gate type outside the set is a violation — NOT included (NOT counts as a NAND/NOR with tied inputs).
Negated input bubbles on otherwise allowed gates are hidden inverters and are reported too; other logic parts
(multiplexers, arithmetic) are violations as well.
"""

from __future__ import annotations

from collections.abc import Iterator

from logilens.lint.engine import GATE_TYPES, LintContext, Rule
from logilens.lint.issue import LintIssue, Severity

OTHER_LOGIC = ("plexer", "arith", "wiring_logic", "switch")


def check(ctx: LintContext) -> Iterator[LintIssue]:
    if ctx.only is None:
        return
    allowed = ", ".join(sorted(s.upper() for s in ctx.only))
    hint = "/".join(s.upper() for s in sorted(ctx.only & {"nand", "nor"})) or "NAND/NOR"
    for comp in ctx.circuit.components:
        token = GATE_TYPES.get(comp.name)
        params = {"allowed": allowed, "hint": hint, "type": token or comp.name}
        if token is not None and token not in ctx.only:
            variant = "not" if token == "not" else ""
            yield ctx.issue(RULE, loc=comp.loc, component=comp, variant=variant, fix_variant=variant or None,
                            params=params)
        elif token is not None and comp.kind == "gate":
            negated = [i + 1 for i in range(int(comp.attrs.get("inputs", 0))) if comp.attrs.get(f"negate{i}")]
            if negated:
                yield ctx.issue(RULE, loc=comp.loc, component=comp, variant="negated", fix_variant="negated",
                                params={**params, "inputs": ", ".join(map(str, negated))})
        elif token is None and comp.kind in OTHER_LOGIC:
            yield ctx.issue(RULE, loc=comp.loc, component=comp, params=params)


RULE = Rule("L011", Severity.ERROR, "gate-set violation", check)
