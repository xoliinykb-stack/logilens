"""Four-valued logic with Logisim 2.7.1 semantics (``data/Value``).

A bit is one of ``'0'``, ``'1'``, ``'x'`` (unknown / floating) or ``'E'`` (error), the same characters
``Value.toString`` prints. Multi-bit values are tuples of bits, **LSB first**.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

Bit = str
ZERO: Bit = "0"
ONE: Bit = "1"
X: Bit = "x"
E: Bit = "E"
BITS = (ZERO, ONE, X, E)

Value = tuple[Bit, ...]


def b_not(a: Bit) -> Bit:
    """``Value.not``: 0<->1, anything undefined -> E."""
    if a == ONE:
        return ZERO
    if a == ZERO:
        return ONE
    return E


def b_and(a: Bit, b: Bit) -> Bit:
    """``Value.and``: 0 dominates; otherwise any X/E -> E."""
    if a == ZERO or b == ZERO:
        return ZERO
    if a == ONE and b == ONE:
        return ONE
    return E


def b_or(a: Bit, b: Bit) -> Bit:
    """``Value.or``: 1 dominates; otherwise any X/E -> E."""
    if a == ONE or b == ONE:
        return ONE
    if a == ZERO and b == ZERO:
        return ZERO
    return E


def b_xor(a: Bit, b: Bit) -> Bit:
    """``Value.xor``: any X/E -> E."""
    if a in (X, E) or b in (X, E):
        return E
    return ZERO if a == b else ONE


def b_combine(a: Bit, b: Bit) -> Bit:
    """``Value.combine`` (two drivers on one bit): X yields to the other value, conflicts -> E."""
    if a == b:
        return a
    if a == X:
        return b
    if b == X:
        return a
    return E


def defined(bit: Bit) -> bool:
    return bit in (ZERO, ONE)


def fully_defined(v: Sequence[Bit]) -> bool:
    return all(b in (ZERO, ONE) for b in v)


def unknown(width: int) -> Value:
    return (X,) * width


def error(width: int) -> Value:
    return (E,) * width


def from_int(n: int, width: int) -> Value:
    """Known value of ``width`` bits (two's complement truncation)."""
    return tuple(ONE if (n >> i) & 1 else ZERO for i in range(width))


def to_int(v: Sequence[Bit]) -> int:
    """Unsigned integer of a fully defined value."""
    return sum(1 << i for i, b in enumerate(v) if b == ONE)


def to_str(v: Sequence[Bit]) -> str:
    """MSB-first string as printed by Logisim (without the 4-bit spacing)."""
    return "".join(reversed(tuple(v)))


def from_str(s: str) -> Value:
    """Inverse of :func:`to_str` (spaces ignored; 'X' accepted for 'x')."""
    bits = [ch if ch != "X" else X for ch in s.replace(" ", "")]
    for ch in bits:
        if ch not in BITS:
            raise ValueError(f"bad bit {ch!r} in {s!r}")
    return tuple(reversed(bits))


def bitwise(op, a: Sequence[Bit], b: Sequence[Bit]) -> Value:  # type: ignore[no-untyped-def]
    """Apply a bit operation pairwise (shorter operand padded with E, like Logisim width mismatch)."""
    n = max(len(a), len(b))
    return tuple(op(a[i] if i < len(a) else E, b[i] if i < len(b) else E) for i in range(n))


def v_not(a: Sequence[Bit]) -> Value:
    return tuple(b_not(x) for x in a)


def combine_all(values: Iterable[Sequence[Bit]], width: int) -> Value:
    """Resolve several drivers of one multi-bit node."""
    out: list[Bit] = [X] * width
    for v in values:
        for i in range(min(width, len(v))):
            out[i] = b_combine(out[i], v[i])
    return tuple(out)
