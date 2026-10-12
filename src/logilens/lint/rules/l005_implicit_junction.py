"""L005 — implicit T-junction (INFO).

Decision (verified in Logisim 2.7.1 sources): loading a file runs ``WireRepair``, which splits every wire at every
wire endpoint / port lying inside it, so a wire end (or a port) in the middle of another wire IS connected —
Logisim even draws a junction dot. The original idea "no connection there" is wrong for 2.7.1; we report it as
INFO only, so the user knows the connection exists (and can spot an unintended one).
"""

from __future__ import annotations

from collections.abc import Iterator

from logilens.core.geometry import Point
from logilens.core.netlist import Component, Port
from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity
from logilens.lint.rules._util import points_on_wires


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ = ctx.circuit
    ends = {pt for w in circ.wires for pt in (w.a, w.b)}
    ports: dict[Point, tuple[Component, Port]] = {}
    for c in circ.components:
        for p in c.ports:
            ports.setdefault(p.loc, (c, p))
    on = points_on_wires(circ)
    for w in circ.wires:
        for pt in sorted(on[w.index]):
            if pt in (w.a, w.b):
                continue
            if pt in ends:
                yield ctx.issue(RULE, loc=pt, related=[w.a, w.b], params={"wire": f"{w.a}-{w.b}"})
            elif pt in ports:
                comp, port = ports[pt]
                yield ctx.issue(RULE, loc=pt, component=comp, variant="port", related=[w.a, w.b],
                                params={"port": port.name})


RULE = Rule("L005", Severity.INFO, "implicit T-junction", check)
