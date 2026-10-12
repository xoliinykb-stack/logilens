"""Cube operations over bitmask cubes (see :class:`logilens.core.logic_types.Cube`)."""

from __future__ import annotations

from collections.abc import Iterator
from functools import cache, lru_cache
from itertools import product

from logilens.core.logic_types import Cube


def full_mask(n: int) -> int:
    """Bitmask with all ``2**n`` minterms set."""
    return (1 << (1 << n)) - 1


@cache
def var_true_mask(n: int, bit: int) -> int:
    """Bitmask of minterms whose variable bit ``bit`` (0 = LSB = last input) equals 1."""
    mask = 0
    for m in range(1 << n):
        if (m >> bit) & 1:
            mask |= 1 << m
    return mask


@lru_cache(maxsize=1 << 16)
def _mask(n: int, care: int, value: int) -> int:
    mask = full_mask(n)
    for bit in range(n):
        if care >> bit & 1:
            vm = var_true_mask(n, bit)
            mask &= vm if value >> bit & 1 else ~vm
    return mask


def cube_mask(c: Cube) -> int:
    """Bitmask of the minterms covered by the cube."""
    return _mask(c.n, c.care, c.value)


def cube_from_str(text: str, outputs: int = 0) -> Cube:
    """Parse ``'--101'`` (positions = input order) into a :class:`Cube`."""
    n = len(text)
    care = value = 0
    for i, ch in enumerate(text):
        bit = 1 << (n - 1 - i)
        if ch in "01":
            care |= bit
            if ch == "1":
                value |= bit
        elif ch not in "-xX":
            raise ValueError(f"bad cube character {ch!r} in {text!r}")
    return Cube(n, care, value, outputs)


def minterm_cube(n: int, m: int, outputs: int = 0) -> Cube:
    """Cube consisting of the single minterm ``m``."""
    full = (1 << n) - 1
    return Cube(n, full, m & full, outputs)


def covers_minterm(c: Cube, m: int) -> bool:
    """True if minterm ``m`` lies in the cube."""
    return (m & c.care) == c.value


def cube_minterms(c: Cube) -> list[int]:
    """Sorted list of covered minterms."""
    mask = cube_mask(c)
    return [m for m in range(1 << c.n) if mask >> m & 1]


def contains(a: Cube, b: Cube) -> bool:
    """True if cube ``a`` contains cube ``b`` (a ⊇ b)."""
    return (a.care & ~b.care) == 0 and (b.value & a.care) == a.value


def intersects(a: Cube, b: Cube) -> bool:
    """True if the cubes share at least one minterm."""
    common = a.care & b.care
    return (a.value & common) == (b.value & common)


def merge_adjacent(a: Cube, b: Cube) -> Cube | None:
    """QM merge: same variables, values differing in exactly one bit -> merged cube, else None."""
    if a.care != b.care:
        return None
    diff = a.value ^ b.value
    if diff == 0 or diff & (diff - 1):
        return None
    return Cube(a.n, a.care & ~diff, a.value & ~diff, a.outputs & b.outputs)


def consensus(a: Cube, b: Cube, bit: int | None = None) -> Cube | None:
    """Consensus of two cubes (exactly one opposed variable), optionally restricted to variable ``bit``."""
    common = a.care & b.care
    opposed = (a.value ^ b.value) & common
    if opposed == 0 or opposed & (opposed - 1):
        return None
    if bit is not None and opposed != 1 << bit:
        return None
    care = (a.care | b.care) & ~opposed
    value = (a.value | b.value) & care
    return Cube(a.n, care, value, a.outputs & b.outputs)


def is_implicant(c: Cube, off: int) -> bool:
    """True if the cube does not intersect the OFF-set mask."""
    return cube_mask(c) & off == 0


def all_cubes(n: int) -> Iterator[Cube]:
    """All ``3**n`` cubes (including the universal cube)."""
    for chars in product("-01", repeat=n):
        yield cube_from_str("".join(chars))


def literal_positions(c: Cube) -> list[tuple[int, int]]:
    """``(input_index, value)`` for each present variable, in input order."""
    out = []
    for i in range(c.n):
        bit = 1 << (c.n - 1 - i)
        if c.care & bit:
            out.append((i, 1 if c.value & bit else 0))
    return out


def ones_count(c: Cube) -> int:
    """Number of '1' characters (QM grouping key)."""
    return (c.value & c.care).bit_count()


def without_tag(c: Cube) -> Cube:
    """Copy of the cube with the output tag cleared."""
    return Cube(c.n, c.care, c.value)


def cube_sort_key(c: Cube) -> tuple[int, int, str]:
    """Deterministic display order: fewer literals first, then fewer ones, then string."""
    return (c.num_literals, ones_count(c), c.to_str().replace("-", "2"))
