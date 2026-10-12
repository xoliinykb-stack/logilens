"""Robustness of the optimum: ILP under the four objective variants and negator-limit feasibility."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from logilens.core.logic_types import (
    Cost,
    CostModel,
    Form,
    MinimizationResult,
    MultiFunction,
    Objective,
)
from logilens.minimize.ilp import ilp_minimize


@dataclass
class RobustnessReport:
    """NAND/NOR cost of the ILP optimum per objective, minimum negators and limit feasibility."""

    form: Form
    costs: dict[Objective, Cost | None]
    identical: bool
    min_negators: int | None
    negator_limits: dict[int, str] = field(default_factory=dict)
    results: dict[str, MinimizationResult] = field(default_factory=dict)

    def summary(self) -> list[str]:
        """Readable lines."""
        lines = [f"{obj.value}: {cost.short() if cost else 'n/a'}" for obj, cost in self.costs.items()]
        lines.append("optimum identical under all objectives" if self.identical else "optimum depends on objective")
        lines.append(f"minimum negators: {self.min_negators}")
        lines += [f"<= {lim} negators: {status}" for lim, status in sorted(self.negator_limits.items())]
        return lines


def robustness(
    mf: MultiFunction, form: Form, limits: Iterable[int] | None = None, time_limit: float | None = 60.0
) -> RobustnessReport:
    """Re-run the ILP for every :class:`Objective`; check negator limits (default: min_negators - 1)."""
    costs: dict[Objective, Cost | None] = {}
    results: dict[str, MinimizationResult] = {}
    for obj in Objective:
        res = ilp_minimize(mf, form, CostModel(tech=form.tech, objective=obj), time_limit=time_limit)
        costs[obj] = res.cost if res.proof and res.proof.optimal else None
        results[obj.value] = res
    pairs = {(c.gates, c.inputs) for c in costs.values() if c is not None}
    identical = len(pairs) == 1 and all(c is not None for c in costs.values())
    min_neg_cost = costs.get(Objective.MIN_NEGATORS)
    min_neg = min_neg_cost.inverters if min_neg_cost else None
    if limits is None:
        limits = [min_neg - 1] if min_neg else []
    report = RobustnessReport(form, costs, identical, min_neg, {}, results)
    for lim in limits:
        res = ilp_minimize(mf, form, max_negators=lim, time_limit=time_limit)
        status = res.proof.status if res.proof else "unknown"
        if res.cost is not None:
            status += f" ({res.cost.short()})"
        report.negator_limits[lim] = status
        results[f"max_negators={lim}"] = res
    return report
