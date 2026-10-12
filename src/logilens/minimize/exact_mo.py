"""Exact multi-output minimization independent of the ILP.

1. Multi-output primes: primes of the product of every non-empty output subset, kept with their maximal
   output tag and only if they touch the ON-set of an output in the tag.
2. DFS branch & bound over these cubes minimizing the number of *distinct* cubes covering every
   (output, ON-minterm) pair; all minimum solutions are enumerated.
3. For each minimum solution every output picks its cheapest sub-cover (fewest cubes, then literals);
   the solution with the best NAND/NOR cost wins.

The proof covers the number of distinct terms; the NAND/NOR cost is optimal among minimum-term solutions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from logilens.core.logic_types import (
    CostModel,
    Cover,
    Cube,
    Form,
    MinimizationResult,
    MultiFunction,
    Proof,
    Step,
)
from logilens.logic.cost import nandnor_cost, objective_key
from logilens.logic.cube import cube_mask, cube_sort_key
from logilens.logic.truth_table import minterms_of
from logilens.minimize.base import Problem, default_model, finish, make_cover, make_problem
from logilens.minimize.petrick import _bnb_cover
from logilens.minimize.qm import qm_primes

MAX_SOLUTIONS = 50_000


def usable_tag(problem: Problem, c: Cube) -> int:
    """Outputs for which ``c`` is an implicant touching the target ON-set."""
    mask = cube_mask(c)
    tag = 0
    for k, name in enumerate(problem.outputs):
        t = problem.targets[name]
        if not mask & t.off and mask & t.on:
            tag |= 1 << k
    return tag


def _implicant_tag(problem: Problem, c: Cube) -> int:
    mask = cube_mask(c)
    return sum(1 << k for k, o in enumerate(problem.outputs) if not mask & problem.targets[o].off)


def multi_output_primes(problem: Problem) -> list[Cube]:
    """Multi-output prime implicants (``Cube.outputs`` = usable tag), deterministic order."""
    full = (1 << (1 << problem.n)) - 1
    found: dict[tuple[int, int], Cube] = {}
    names = problem.outputs
    for subset in range(1, 1 << len(names)):
        off = 0
        for k, name in enumerate(names):
            if subset >> k & 1:
                off |= problem.targets[name].off
        primes, _ = qm_primes(problem.n, full & ~off, 0, keep_dc_only=True)
        for p in primes:
            if p.key in found or _implicant_tag(problem, p) != subset:
                continue
            tag = usable_tag(problem, p)
            if tag:
                found[p.key] = Cube(p.n, p.care, p.value, tag)
    return sorted(found.values(), key=cube_sort_key)


@dataclass
class _Search:
    cand_masks: list[int]  # per cube: element bitmask
    elem_cands: list[int]  # per element: cube bitmask
    best: int
    solutions: list[int]
    nodes: int = 0
    truncated: bool = False


def _lower_bound(s: _Search, uncovered: int, excluded: int) -> int:
    remaining = uncovered.bit_count()
    if not remaining:
        return 0
    biggest = max(((m & uncovered).bit_count() for k, m in enumerate(s.cand_masks) if not excluded >> k & 1),
                  default=0)
    if biggest == 0:
        return 10**9
    lb1 = -(-remaining // biggest)
    used = 0
    lb2 = 0
    elems = [e for e in range(len(s.elem_cands)) if uncovered >> e & 1]
    elems.sort(key=lambda e: (s.elem_cands[e] & ~excluded).bit_count())
    for e in elems:
        cands = s.elem_cands[e] & ~excluded
        if not cands & used:
            used |= cands
            lb2 += 1
    return max(lb1, lb2)


def _dfs(s: _Search, uncovered: int, chosen: int, excluded: int) -> None:
    s.nodes += 1
    count = chosen.bit_count()
    if not uncovered:
        if count < s.best:
            s.best, s.solutions = count, []
        if len(s.solutions) < MAX_SOLUTIONS:
            s.solutions.append(chosen)
        else:
            s.truncated = True
        return
    if count + _lower_bound(s, uncovered, excluded) > s.best:
        return
    elems = [e for e in range(len(s.elem_cands)) if uncovered >> e & 1]
    e = min(elems, key=lambda x: (s.elem_cands[x] & ~excluded).bit_count())
    cands = [k for k in range(len(s.cand_masks)) if (s.elem_cands[e] & ~excluded) >> k & 1]
    cands.sort(key=lambda k: -(s.cand_masks[k] & uncovered).bit_count())
    for k in cands:
        _dfs(s, uncovered & ~s.cand_masks[k], chosen | 1 << k, excluded)
        excluded |= 1 << k


def _elements(problem: Problem) -> list[tuple[int, int]]:
    return [(k, m) for k, o in enumerate(problem.outputs) for m in minterms_of(problem.targets[o].on)]


def min_distinct_cover(problem: Problem, cubes: list[Cube], upper: int | None = None) -> tuple[int, list[int], bool]:
    """All covers with the minimum number of distinct cubes: ``(min_count, solutions, truncated)``."""
    elems = _elements(problem)
    index = {e: i for i, e in enumerate(elems)}
    cand_masks = []
    for c in cubes:
        mask = cube_mask(c)
        em = 0
        for k in range(len(problem.outputs)):
            if c.outputs >> k & 1:
                for m in minterms_of(mask & problem.targets[problem.outputs[k]].on):
                    em |= 1 << index[(k, m)]
        cand_masks.append(em)
    elem_cands = [sum(1 << k for k, em in enumerate(cand_masks) if em >> i & 1) for i in range(len(elems))]
    s = _Search(cand_masks, elem_cands, upper if upper is not None else len(cubes), [])
    _dfs(s, (1 << len(elems)) - 1, 0, 0)
    return s.best, s.solutions, s.truncated


def _subcovers(problem: Problem, chosen: list[Cube]) -> dict[str, tuple[Cube, ...]]:
    """Per output: cheapest (fewest cubes, then literals) sub-cover from the chosen cubes."""
    terms = {}
    for k, name in enumerate(problem.outputs):
        avail = [c for c in chosen if c.outputs >> k & 1]
        pick = _bnb_cover(avail, problem.targets[name].on)
        terms[name] = tuple(avail[i] for i in range(len(avail)) if pick >> i & 1)
    return terms


def exact_multi_output(mf: MultiFunction, form: Form, model: CostModel | None = None) -> MinimizationResult:
    """Exact multi-output minimization via multi-output primes + branch & bound (see module doc)."""
    started = time.perf_counter()
    model = model or default_model(form)
    problem = make_problem(mf, form)
    primes = multi_output_primes(problem)
    best, solutions, truncated = min_distinct_cover(problem, primes)
    best_cover: Cover | None = None
    best_key: tuple[int, ...] | None = None
    for sol in solutions:
        chosen = [primes[k] for k in range(len(primes)) if sol >> k & 1]
        cover = make_cover(problem, _subcovers(problem, chosen))
        key = objective_key(nandnor_cost(cover, model), model.objective)
        if best_key is None or key < best_key:
            best_key, best_cover = key, cover
    steps = [
        Step("exact_mo.primes", f"Multi-output primes ({len(primes)})",
             tuple(f"{p} -> {_tag_names(problem, p.outputs)}" for p in primes)),
        Step("exact_mo.bnb", f"Branch & bound: minimum {best} distinct terms, {len(solutions)} minimum solutions",
             ()),
    ]
    status = "optimal" if not truncated else "optimal count, solutions truncated"
    proof = Proof("bnb", status, float(best), None, "exact_mo dfs (distinct terms)")
    notes = [(f"{len(primes)} multi-output primes; minimum {best} distinct terms; "
              f"{len(solutions)} minimum-term solutions evaluated with the NAND/NOR cost"),
             "proof covers the number of distinct terms; NAND/NOR cost is optimal among minimum-term solutions"]
    return finish("exact_mo", problem, best_cover, multi_output=True, model=model, proof=proof,
                  started=started, steps=steps, notes=notes)


def _tag_names(problem: Problem, tag: int) -> str:
    return ",".join(o for k, o in enumerate(problem.outputs) if tag >> k & 1)
