"""Tison's iterated-consensus method (one consensus pass per variable) with teaching steps."""

from __future__ import annotations

from logilens.core.logic_types import Cube, Step
from logilens.logic.cube import consensus, contains, cube_mask, cube_sort_key, minterm_cube
from logilens.logic.truth_table import minterms_of


def absorb(cubes: list[Cube]) -> list[Cube]:
    """Remove cubes contained in another cube (keeps one copy of duplicates)."""
    unique = list({c.key: c for c in cubes}.values())
    unique.sort(key=lambda c: c.num_literals)
    kept: list[Cube] = []
    for c in unique:
        if not any(contains(k, c) for k in kept):
            kept.append(c)
    return kept


def _pass(cubes: list[Cube], bit: int) -> tuple[list[Cube], list[str]]:
    """Add all consensus terms on variable ``bit``; return (new list after absorption, lines)."""
    found: dict[tuple[int, int], Cube] = {}
    lines: list[str] = []
    for i, a in enumerate(cubes):
        for b in cubes[i + 1:]:
            c = consensus(a, b, bit)
            if c is not None and c.key not in found and not any(contains(x, c) for x in cubes):
                found[c.key] = c
                lines.append(f"{a} ⊙ {b} -> {c}")
    return absorb(cubes + list(found.values())), lines


def tison_primes(
    n: int, on: int, dc: int = 0, names: tuple[str, ...] | None = None, start: list[Cube] | None = None
) -> tuple[list[Cube], list[Step]]:
    """All prime implicants of ``on ∪ dc`` by Tison's method (starting from ``start`` or the minterms).
    Primes covering only don't cares are dropped. Returns ``(primes, steps)``."""
    names = names or tuple(f"x{i}" for i in range(n))
    cubes = absorb(list(start) if start else [minterm_cube(n, m) for m in minterms_of(on | dc)])
    steps = [Step("tison.start", f"Start: {len(cubes)} cubes", tuple(str(c) for c in cubes))]
    for i in range(n):
        bit = n - 1 - i
        cubes, lines = _pass(cubes, bit)
        title = f"Consensus on {names[i]}: {len(lines)} new, {len(cubes)} after absorption"
        steps.append(Step("tison.pass", title, tuple(lines), {"variable": names[i]}))
    primes = sorted((c for c in cubes if cube_mask(c) & on), key=cube_sort_key)
    steps.append(Step("tison.primes", f"Prime implicants ({len(primes)})",
                      tuple(f"P{k + 1} = {p}" for k, p in enumerate(primes)),
                      {"primes": [str(p) for p in primes], "minterms": minterms_of(on)}))
    return primes, steps
