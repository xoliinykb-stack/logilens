"""L001 — unconnected gate input (ERROR).

Logisim's ``AbstractGate.propagate`` skips inputs with nothing at their location (``gateUndefined=ignore``), so a
5-input NOR with one loose input silently behaves as a 4-input NOR — the classic invisible bug. NOT/Buffer inputs
and flip-flop data/clock inputs are checked too (they produce E / never update).
"""

from __future__ import annotations

from collections.abc import Iterator

from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity

FF_CHECKED = {"d", "t", "j", "k", "s", "r", "clock"}


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    for comp in circ.components:
        if comp.kind == "gate":
            n = int(comp.attrs.get("inputs", 0))
            for i in range(n):
                port = comp.ports[i + 1]
                if (comp.id, port.index) not in circ.connected:
                    yield ctx.issue(RULE, loc=port.loc, component=comp,
                                    params={"input": i + 1, "inputs": n, "gate": comp.short})
        elif comp.kind in ("not", "buffer", "controlled"):
            for port in comp.ports[1:]:
                if (comp.id, port.index) not in circ.connected:
                    yield ctx.issue(RULE, loc=port.loc, component=comp, variant="not",
                                    params={"port": port.name})
        elif comp.kind == "flipflop":
            for port in comp.ports:
                if port.name in FF_CHECKED and (comp.id, port.index) not in circ.connected:
                    yield ctx.issue(RULE, loc=port.loc, component=comp, variant="ff", params={"port": port.name})


RULE = Rule("L001", Severity.ERROR, "unconnected gate input", check)
