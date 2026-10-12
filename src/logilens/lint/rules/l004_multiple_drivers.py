"""L004 — several outputs drive one net (ERROR). Structural: equal values in simulation do not hide it.

Drivers that can float (controlled buffers/inverters, gates with ``out`` = 0Z / Z1, tri-state plexers, inout
memory ports) are legitimate on a shared bus and are not counted.
"""

from __future__ import annotations

from collections.abc import Iterator

from logilens.core.netlist import Component
from logilens.lint.engine import LintContext, Rule
from logilens.lint.issue import LintIssue, Severity


def hard_driver(comp: Component, port_index: int) -> bool:
    """True when the port always drives a definite value."""
    port = comp.ports[port_index]
    if port.direction != "output" or comp.kind in ("controlled", "switch"):
        return False
    if comp.kind in ("gate", "not", "buffer") and comp.attrs.get("out", "01") != "01":
        return False
    floating = comp.attrs.get("tristate") or (comp.attrs.get("disabled") == "Z" and comp.attrs.get("enable"))
    return not (comp.kind == "plexer" and floating)


def check(ctx: LintContext) -> Iterator[LintIssue]:
    circ, g = ctx.circuit, ctx.graph
    reported: set[frozenset] = set()
    for t, drivers in sorted(g.thread_drivers.items()):
        hard = sorted({ref for ref in drivers if hard_driver(circ.components[ref[0]], ref[1])})
        key = frozenset(hard)
        if len(hard) < 2 or key in reported:
            continue
        reported.add(key)
        comps = [circ.components[c] for c, _ in hard]
        net = circ.net_of(hard[0])
        loc = net.points[0]
        yield ctx.issue(RULE, loc=loc, component=comps[0], related=[circ.port(r).loc for r in hard],
                        params={"count": len(hard), "drivers": ", ".join(c.describe() for c in comps)})


RULE = Rule("L004", Severity.ERROR, "multiple drivers on one net", check)
