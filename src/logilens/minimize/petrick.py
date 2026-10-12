"""Prime chart, essential primes and Petrick's method (single-output exact minimization)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from logilens.core.logic_types import (
    CostModel,
    Cube,
    Form,
    MinimizationResult,
    MultiFunction,
    Proof,
    Step,
)
from logilens.logic.cube import cube_mask
from logilens.logic.truth_table import minterms_of
from logilens.minimize.base import Problem, finish, make_cover, make_problem
from logilens.minimize.qm import qm_primes
from logilens.minimize.tison import tison_primes

MAX_PRODUCTS = 200_000


@dataclass
class PetrickResult:
    """Single-output result: primes, essentials, all minimal (terms, literals) covers."""

    output: str
    primes: list[Cube]
    essentials: list[Cube]
    variants: list[tuple[Cube, ...]]
    best: tuple[int, int]
    irredundant: int
    complete: bool
    steps: list[Step] = field(default_factory=list)


def _p(k: int) -> str:
    return f"P{k + 1}"


def chart_step(primes: list[Cube], on: int) -> Step:
    """Prime implicant chart: one line per prime with the ON-minterms it covers."""
    ms = minterms_of(on)
    width = max((len(str(m)) for m in ms), default=1)
    header = " " * 12 + " ".join(str(m).rjust(width) for m in ms)
    lines = [header]
    for k, p in enumerate(primes):
        mask = cube_mask(p)
        marks = " ".join(("X" if mask >> m & 1 else ".").rjust(width) for m in ms)
        lines.append(f"{_p(k):>4} {p.to_str():<7}{marks}")
    return Step("petrick.chart", "Prime implicant chart", tuple(lines), {"minterms": ms})


def essential_indices(primes: list[Cube], on: int) -> list[int]:
    """Indices of essential primes (sole cover of some ON-minterm)."""
    ess: set[int] = set()
    for m in minterms_of(on):
        covering = [k for k, p in enumerate(primes) if cube_mask(p) >> m & 1]
        if len(covering) == 1:
            ess.add(covering[0])
    return sorted(ess)


def _clauses(primes: list[Cube], on: int) -> list[int]:
    """Petrick clauses as bitmasks of prime indices, deduplicated and absorbed."""
    clauses = set()
    for m in minterms_of(on):
        clause = 0
        for k, p in enumerate(primes):
            if cube_mask(p) >> m & 1:
                clause |= 1 << k
        clauses.add(clause)
    ordered = sorted(clauses, key=lambda c: (c.bit_count(), c))
    return [c for i, c in enumerate(ordered) if not any(o & c == o for o in ordered[:i])]


def _absorb_products(products: set[int]) -> set[int]:
    ordered = sorted(products, key=lambda x: (x.bit_count(), x))
    kept: list[int] = []
    for x in ordered:
        if not any(k & x == k for k in kept):
            kept.append(x)
    return set(kept)


def expand(clauses: list[int], limit: int = MAX_PRODUCTS) -> set[int] | None:
    """Multiply out the product of sums with absorption; None if it exceeds ``limit`` products."""
    products = {0}
    for clause in clauses:
        bits = [1 << k for k in range(clause.bit_length()) if clause >> k & 1]
        new = {p | b for p in products for b in bits}
        products = _absorb_products(new)
        if len(products) > limit:
            return None
    return products


def _set_cost(mask: int, primes: list[Cube]) -> tuple[int, int]:
    idx = [k for k in range(len(primes)) if mask >> k & 1]
    return len(idx), sum(primes[k].num_literals for k in idx)


def _product_text(mask: int) -> str:
    return "".join(_p(k) for k in range(mask.bit_length()) if mask >> k & 1) or "1"


def petrick(output: str, primes: list[Cube], on: int, limit: int = MAX_PRODUCTS) -> PetrickResult:
    """All minimal covers (fewest terms, then fewest literals) of ``on`` by ``primes``."""
    steps = [chart_step(primes, on)]
    ess = essential_indices(primes, on)
    ess_mask = sum(1 << k for k in ess)
    covered = 0
    for k in ess:
        covered |= cube_mask(primes[k])
    steps.append(Step("petrick.essential", f"Essential primes ({len(ess)})",
                      tuple(f"{_p(k)} = {primes[k]}" for k in ess)))
    rest = on & ~covered
    clauses = _clauses(primes, rest)
    pos = "".join("(" + " + ".join(_p(k) for k in range(c.bit_length()) if c >> k & 1) + ")" for c in clauses)
    steps.append(Step("petrick.product", "Petrick product of sums", (f"P = {pos or '1'}",)))
    products = expand(clauses, limit)
    if products is None:
        return _fallback(output, primes, on, ess, steps)
    full = sorted((p | ess_mask for p in products), key=lambda x: (_set_cost(x, primes), _bits(x)))
    best = _set_cost(full[0], primes)
    optimal = [x for x in full if _set_cost(x, primes) == best]
    lines = [" + ".join(_product_text(x) for x in full[:60]) + (" + ..." if len(full) > 60 else "")]
    steps.append(Step("petrick.expansion", f"Expanded: {len(full)} irredundant covers", tuple(lines)))
    steps.append(Step("petrick.minimal", f"Minimal covers: {len(optimal)} × ({best[0]} terms, {best[1]} literals)",
                      tuple(" + ".join(str(primes[k]) for k in _bits(x)) for x in optimal[:60])))
    variants = [tuple(primes[k] for k in _bits(x)) for x in optimal]
    return PetrickResult(output, primes, [primes[k] for k in ess], variants, best, len(full), True, steps)


def _bits(mask: int) -> list[int]:
    return [k for k in range(mask.bit_length()) if mask >> k & 1]


def _fallback(output: str, primes: list[Cube], on: int, ess: list[int], steps: list[Step]) -> PetrickResult:
    """Expansion too large: exact branch & bound for one minimal cover."""
    best_mask = _bnb_cover(primes, on)
    best = _set_cost(best_mask, primes)
    steps.append(Step("petrick.fallback", "Expansion too large; branch & bound used (one optimal cover)",
                      (" + ".join(str(primes[k]) for k in _bits(best_mask)),)))
    variants = [tuple(primes[k] for k in _bits(best_mask))]
    return PetrickResult(output, primes, [primes[k] for k in ess], variants, best, 0, False, steps)


def _bnb_cover(primes: list[Cube], on: int) -> int:
    """Minimum (terms, literals) cover by DFS branch & bound."""
    masks = [cube_mask(p) for p in primes]
    best: list[object] = [(10**9, 10**9), 0]

    def dfs(uncovered: int, chosen: int, cost: tuple[int, int]) -> None:
        if cost >= best[0]:  # type: ignore[operator]
            return
        if not uncovered:
            best[0], best[1] = cost, chosen
            return
        m = (uncovered & -uncovered).bit_length() - 1
        options = sorted((k for k in range(len(primes)) if masks[k] >> m & 1),
                         key=lambda k: -(masks[k] & uncovered).bit_count())
        for k in options:
            dfs(uncovered & ~masks[k], chosen | 1 << k, (cost[0] + 1, cost[1] + primes[k].num_literals))

    dfs(on, 0, (0, 0))
    return best[1]  # type: ignore[return-value]


def primes_for(problem: Problem, output: str, method: str = "qm") -> tuple[list[Cube], list[Step]]:
    """Prime implicants of one output's target function by 'qm' or 'tison'."""
    t = problem.targets[output]
    if method == "tison":
        return tison_primes(problem.n, t.on, t.dc, problem.inputs)
    return qm_primes(problem.n, t.on, t.dc)


def petrick_all(problem: Problem, prime_method: str = "qm") -> dict[str, PetrickResult]:
    """Per-output Petrick results (steps include the prime generation steps)."""
    out = {}
    for name in problem.outputs:
        primes, psteps = primes_for(problem, name, prime_method)
        res = petrick(name, primes, problem.targets[name].on)
        res.steps = psteps + res.steps
        out[name] = res
    return out


def independent_minimize(
    mf: MultiFunction, form: Form, prime_method: str = "qm", model: CostModel | None = None
) -> MinimizationResult:
    """Each output minimized on its own (first minimal variant); identical terms are still shared."""
    started = time.perf_counter()
    problem = make_problem(mf, form)
    results = petrick_all(problem, prime_method)
    cover = make_cover(problem, {o: r.variants[0] if r.variants else () for o, r in results.items()})
    steps = [s for r in results.values() for s in _tag(r)]
    notes = [f"{o}: {len(r.primes)} primes, {len(r.variants)} minimal variants ({r.best[0]} terms, "
             f"{r.best[1]} literals)" for o, r in results.items()]
    exhaustive = all(r.complete for r in results.values())
    status = "per-output optimal" if exhaustive else "per-output optimal (one variant)"
    proof = Proof("exhaustive" if exhaustive else "bnb", status, None, None, "petrick (per output)")
    return finish(f"{prime_method}+petrick", problem, cover, multi_output=False, model=model, proof=proof,
                  started=started, steps=steps, notes=notes)


def _tag(r: PetrickResult) -> list[Step]:
    return [Step(s.kind, f"{r.output}: {s.title}", s.lines, s.data) for s in r.steps]
