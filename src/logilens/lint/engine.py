"""Structural lint engine: runs every rule (``lint/rules/Lxxx_*.py``) over every circuit. No simulation."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cached_property

from logilens.core.geometry import Point
from logilens.core.netlist import CircuitNetlist, Component, ProjectNetlist
from logilens.graph.classify import Classification, classify
from logilens.graph.topo import ComponentGraph
from logilens.lint.issue import LintIssue, Severity

GATE_TYPES = {
    "AND Gate": "and", "OR Gate": "or", "NAND Gate": "nand", "NOR Gate": "nor", "XOR Gate": "xor",
    "XNOR Gate": "xnor", "NOT Gate": "not", "Buffer": "buffer", "Odd Parity": "odd_parity",
    "Even Parity": "even_parity", "Controlled Buffer": "controlled_buffer",
    "Controlled Inverter": "controlled_inverter",
}
"""Logisim gate name -> token used in ``only={...}``."""


@dataclass
class LintContext:
    project: ProjectNetlist
    circuit: CircuitNetlist
    only: frozenset[str] | None = None

    @cached_property
    def classification(self) -> Classification:
        return classify(self.circuit)

    @property
    def graph(self) -> ComponentGraph:
        return self.classification.graph

    def issue(self, rule: Rule, *, loc: Point | None, component: Component | None = None, variant: str = "",
              params: Mapping[str, object] | None = None, related: Iterable[Point] = (),
              severity: Severity | None = None, fix_variant: str | None = None) -> LintIssue:
        """Build an issue with standard keys ``lint.<code>.msg[.variant]`` / ``lint.<code>.fix[.variant]``."""
        p = dict(params or {})
        if component is not None:
            p.setdefault("component", component.describe())
        if loc is not None:
            p.setdefault("point", str(loc))
        suffix = f".{variant}" if variant else ""
        fsuffix = f".{fix_variant}" if fix_variant else ""
        return LintIssue(rule.code, severity or rule.severity, self.circuit.name, loc,
                         component.describe() if component else None,
                         f"lint.{rule.code}.msg{suffix}", f"lint.{rule.code}.fix{fsuffix}", p, list(related))


@dataclass(frozen=True)
class Rule:
    code: str
    severity: Severity
    title: str
    check: Callable[[LintContext], Iterable[LintIssue]] = field(compare=False)


def all_rules() -> list[Rule]:
    """Every rule module in ``lint/rules`` exposes ``RULE``; sorted by code."""
    from logilens.lint import rules as pkg

    found = []
    for info in pkgutil.iter_modules(pkg.__path__):
        mod = importlib.import_module(f"{pkg.__name__}.{info.name}")
        if hasattr(mod, "RULE"):
            found.append(mod.RULE)
    return sorted(found, key=lambda r: r.code)


def normalize_only(only: Iterable[str] | str | None) -> frozenset[str] | None:
    """``"nand,NOR"`` / ``{"nand","nor"}`` -> ``frozenset({"nand","nor"})``; None = no restriction."""
    if only is None:
        return None
    items = only.split(",") if isinstance(only, str) else list(only)
    return frozenset(s.strip().lower().replace(" ", "_") for s in items if s.strip())


def lint(project: ProjectNetlist, only: Iterable[str] | str | None = None, circuits: Iterable[str] | None = None,
         rules: Iterable[str] | None = None) -> list[LintIssue]:
    """Run the selected rules (default all) on the selected circuits (default all); sorted by severity, rule, loc."""
    allowed = normalize_only(only)
    wanted = set(rules) if rules is not None else None
    selected = [r for r in all_rules() if wanted is None or r.code in wanted]
    names = list(circuits) if circuits is not None else list(project.circuits)
    issues: list[LintIssue] = []
    for name in names:
        ctx = LintContext(project, project.circuits[name], allowed)
        for rule in selected:
            issues.extend(rule.check(ctx))
    issues.sort(key=lambda i: (i.severity.rank, i.circuit, i.rule, (i.loc or Point(0, 0))))
    return issues


def count_problems(issues: Iterable[LintIssue]) -> int:
    """Number of ERROR + WARNING issues."""
    return sum(1 for i in issues if i.is_problem)


def summarize(issues: Iterable[LintIssue]) -> dict[str, int]:
    """Counts per severity."""
    out = {s.value: 0 for s in Severity}
    for i in issues:
        out[i.severity.value] += 1
    return out
