"""Quine–McCluskey prime implicant generation with teaching steps."""

from __future__ import annotations

from collections import defaultdict

from logilens.core.logic_types import Cube, Step
from logilens.logic.cube import cube_mask, cube_sort_key, merge_adjacent, minterm_cube, ones_count
from logilens.logic.truth_table import minterms_of


def _label(c: Cube) -> str:
    return f"m({','.join(map(str, minterms_of(cube_mask(c))))})"


def _group_step(level: int, cubes: list[Cube]) -> Step:
    groups: dict[int, list[Cube]] = defaultdict(list)
    for c in cubes:
        groups[ones_count(c)].append(c)
    lines = []
    for ones in sorted(groups):
        items = ", ".join(f"{c} {_label(c)}" for c in sorted(groups[ones], key=lambda x: x.value))
        lines.append(f"{ones} ones: {items}")
    return Step("qm.group", f"Level {level}: implicants grouped by number of ones", tuple(lines),
                {"level": level, "groups": {k: [str(c) for c in v] for k, v in groups.items()}})


def _merge_level(cubes: list[Cube]) -> tuple[list[Cube], set[Cube], list[str]]:
    """One QM pass: merge neighbours in adjacent ones-groups. Returns (merged, used, lines)."""
    groups: dict[int, list[Cube]] = defaultdict(list)
    for c in cubes:
        groups[ones_count(c)].append(c)
    merged: dict[tuple[int, int], Cube] = {}
    used: set[Cube] = set()
    lines: list[str] = []
    for ones in sorted(groups):
        for a in groups[ones]:
            for b in groups.get(ones + 1, ()):
                m = merge_adjacent(a, b)
                if m is None:
                    continue
                used.update((a, b))
                if m.key not in merged:
                    merged[m.key] = m
                    lines.append(f"{a} + {b} -> {m} {_label(m)}")
    return list(merged.values()), used, lines


def qm_primes(n: int, on: int, dc: int = 0, keep_dc_only: bool = False) -> tuple[list[Cube], list[Step]]:
    """Prime implicants of ``on ∪ dc`` (QM tabulation). Primes covering only DC are dropped unless
    ``keep_dc_only``. Returns ``(primes, steps)``."""
    current = [minterm_cube(n, m) for m in minterms_of(on | dc)]
    primes: list[Cube] = []
    steps: list[Step] = []
    level = 0
    while current:
        steps.append(_group_step(level, current))
        merged, used, lines = _merge_level(current)
        if lines:
            steps.append(Step("qm.merge", f"Level {level} -> {level + 1}: merges", tuple(lines)))
        primes.extend(c for c in current if c not in used)
        current = merged
        level += 1
    dropped = [p for p in primes if not cube_mask(p) & on]
    if not keep_dc_only:
        primes = [p for p in primes if cube_mask(p) & on]
    primes.sort(key=cube_sort_key)
    lines = [f"P{k + 1} = {p} {_label(p)}" for k, p in enumerate(primes)]
    if dropped and not keep_dc_only:
        lines.append("dropped (cover only don't cares): " + ", ".join(str(p) for p in dropped))
    steps.append(Step("qm.primes", f"Prime implicants ({len(primes)})", tuple(lines),
                      {"primes": [str(p) for p in primes]}))
    return primes, steps
