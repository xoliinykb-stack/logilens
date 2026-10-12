"""Petrick + sharing: best combination of individually minimal covers under the NAND/NOR cost."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from itertools import product
from math import prod

from logilens.core.logic_types import (
    CostModel,
    Cover,
    Form,
    MinimizationResult,
    MultiFunction,
    Proof,
    Step,
)
from logilens.logic.cost import nandnor_cost, objective_key
from logilens.minimize.base import default_model, finish, make_cover, make_problem
from logilens.minimize.petrick import petrick_all

MAX_COMBINATIONS = 2_000_000


@dataclass(frozen=True)
class SharingStats:
    """Distribution of NAND/NOR costs over all combinations of per-output minimal variants."""

    combinations: int
    best: tuple[int, int]
    worst: tuple[int, int]
    distribution: dict[tuple[int, int], int]
    exhaustive: bool


def best_sharing(
    mf: MultiFunction,
    form: Form,
    model: CostModel | None = None,
    prime_method: str = "qm",
    limit: int = MAX_COMBINATIONS,
) -> tuple[MinimizationResult, SharingStats]:
    """Enumerate all combinations of per-output minimal variants and keep the cheapest one."""
    started = time.perf_counter()
    model = model or default_model(form)
    problem = make_problem(mf, form)
    results = petrick_all(problem, prime_method)
    names = list(problem.outputs)
    pools = [results[o].variants or [()] for o in names]
    total = prod(len(p) for p in pools)
    exhaustive = total <= limit
    best_cover: Cover | None = None
    best_key: tuple[int, ...] | None = None
    dist: Counter[tuple[int, int]] = Counter()
    for k, combo in enumerate(product(*pools)):
        if k >= limit:
            break
        cover = make_cover(problem, dict(zip(names, combo)))
        cost = nandnor_cost(cover, model)
        dist[(cost.gates, cost.inputs)] += 1
        key = objective_key(cost, model.objective) + (k,)
        if best_key is None or key < best_key:
            best_key, best_cover = key, cover
    stats = SharingStats(min(total, limit), min(dist), max(dist), dict(dist), exhaustive)
    step = Step("sharing.enumerate", f"{stats.combinations} combinations of minimal covers",
                tuple(f"{g}/{i}: {c}" for (g, i), c in sorted(dist.items())), {"distribution": dict(dist)})
    status = "optimal among minimal per-output covers" if exhaustive else "partial enumeration"
    proof = Proof("exhaustive", status, None, None, "petrick+sharing")
    notes = [(f"{stats.combinations} combinations, best {stats.best[0]}/{stats.best[1]}, "
              f"worst {stats.worst[0]}/{stats.worst[1]}")]
    if not exhaustive:
        notes.append(f"only the first {limit} of {total} combinations were evaluated")
    res = finish("petrick+sharing", problem, best_cover, multi_output=True, model=model, proof=proof,
                 started=started, steps=[step], notes=notes)
    return res, stats

