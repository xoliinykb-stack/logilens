"""Common minimization plumbing: problem targets per form, verification, result construction."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from logilens.core.logic_types import (
    Cost,
    CostModel,
    Cover,
    Cube,
    Form,
    MinimizationResult,
    MultiFunction,
    Proof,
    Step,
)
from logilens.logic.cost import nandnor_cost
from logilens.logic.cube import cube_mask
from logilens.logic.truth_table import target_sets


@dataclass(frozen=True)
class Target:
    """What one output's cover must do: cover ``on`` (target set), avoid ``off``; ``dc`` free."""

    on: int
    off: int
    dc: int


@dataclass(frozen=True)
class Problem:
    """Multi-output covering problem in *target* terms for one form."""

    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    form: Form
    targets: dict[str, Target]

    @property
    def n(self) -> int:
        """Number of inputs."""
        return len(self.inputs)


def make_problem(mf: MultiFunction, form: Form) -> Problem:
    """Translate a :class:`MultiFunction` into the covering problem for ``form``."""
    targets = {o: Target(*target_sets(mf.functions[o], form)) for o in mf.outputs}
    return Problem(mf.inputs, mf.outputs, form, targets)


def default_model(form: Form) -> CostModel:
    """NAND/NOR cost model with the technology matching the form."""
    return CostModel(tech=form.tech)


def verify_cover(problem: Problem, cover: Cover) -> bool:
    """True if every output's cubes cover its target ON-set and never touch its target OFF-set."""
    for name in problem.outputs:
        t = problem.targets[name]
        covered = 0
        for c in cover.terms.get(name, ()):
            mask = cube_mask(c)
            if mask & t.off:
                return False
            covered |= mask
        if t.on & ~covered:
            return False
    return True


def make_cover(problem: Problem, terms: Mapping[str, Sequence[Cube]]) -> Cover:
    """Cover with cubes per output sorted deterministically (output tags cleared)."""
    ordered = {}
    for name in problem.outputs:
        cubes = {Cube(c.n, c.care, c.value) for c in terms.get(name, ())}
        ordered[name] = tuple(sorted(cubes, key=_display_key))
    return Cover(problem.form, problem.inputs, ordered)


def _display_key(c: Cube) -> str:
    return c.to_str().replace("-", "2")


def finish(
    method: str,
    problem: Problem,
    cover: Cover | None,
    *,
    multi_output: bool,
    model: CostModel | None = None,
    proof: Proof | None = None,
    started: float = 0.0,
    steps: list[Step] | None = None,
    notes: list[str] | None = None,
) -> MinimizationResult:
    """Re-cost with the NAND/NOR cost model, verify and package a :class:`MinimizationResult`."""
    cost: Cost | None = None
    verified = False
    if cover is not None:
        cost = nandnor_cost(cover, model or default_model(problem.form))
        verified = verify_cover(problem, cover)
    return MinimizationResult(
        method=method,
        form=problem.form,
        multi_output=multi_output,
        cover=cover,
        cost=cost,
        proof=proof,
        verified=verified,
        runtime_s=time.perf_counter() - started if started else 0.0,
        steps=steps or [],
        notes=notes or [],
    )


@contextmanager
def timer() -> Iterator[Callable[[], float]]:
    """Context manager yielding a function that returns elapsed seconds."""
    start = time.perf_counter()
    yield lambda: time.perf_counter() - start


def output_bit(problem: Problem, name: str) -> int:
    """Output-tag bit of an output."""
    return 1 << problem.outputs.index(name)
