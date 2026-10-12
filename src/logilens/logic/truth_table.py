"""Truth-table helpers: building functions, minterm/bit conversions and form targets."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from logilens.core.logic_types import BoolFunction, Form, MultiFunction
from logilens.logic.cube import full_mask


def minterm_bits(m: int, n: int) -> str:
    """Minterm as an MSB-first bit string, e.g. ``minterm_bits(5, 5) == '00101'``."""
    return format(m, f"0{n}b") if n else ""


def bits_to_minterm(bits: str) -> int:
    """Inverse of :func:`minterm_bits`."""
    return int(bits, 2) if bits else 0


def input_value(m: int, n: int, i: int) -> int:
    """Value of input ``i`` (0 = first/MSB) in minterm ``m``."""
    return (m >> (n - 1 - i)) & 1


def mask_from_minterms(minterms: Iterable[int]) -> int:
    """Bitmask with the given minterms set."""
    mask = 0
    for m in minterms:
        mask |= 1 << m
    return mask


def minterms_of(mask: int) -> list[int]:
    """Sorted minterms present in a bitmask."""
    out = []
    m = 0
    while mask:
        if mask & 1:
            out.append(m)
        mask >>= 1
        m += 1
    return out


def function_from_sets(n: int, on: int, dc: int = 0) -> BoolFunction:
    """Function from ON and DC masks; OFF is the rest."""
    full = full_mask(n)
    return BoolFunction(n, on, full & ~(on | dc), dc & ~on)


def function_from_callable(n: int, fn: Callable[[int], int | None]) -> BoolFunction:
    """Function from ``fn(m) -> 1 | 0 | None`` (None = don't care)."""
    on = dc = 0
    for m in range(1 << n):
        v = fn(m)
        if v is None:
            dc |= 1 << m
        elif v:
            on |= 1 << m
    return function_from_sets(n, on, dc)


def multi_from_rows(
    inputs: Iterable[str], outputs: Iterable[str], rows: Mapping[int, str], unlisted: str = "dc"
) -> MultiFunction:
    """Build a :class:`MultiFunction` from ``minterm -> output chars`` ('0', '1', '-'/'x')."""
    ins, outs = tuple(inputs), tuple(outputs)
    n = len(ins)
    funcs = {}
    for k, name in enumerate(outs):
        on = dc = 0
        for m in range(1 << n):
            ch = rows[m][k] if m in rows else {"dc": "-", "0": "0", "1": "1"}[unlisted]
            if ch == "1":
                on |= 1 << m
            elif ch in "-xX":
                dc |= 1 << m
        funcs[name] = function_from_sets(n, on, dc)
    return MultiFunction(ins, outs, funcs)


def multi_from_functions(inputs: Iterable[str], funcs: Mapping[str, BoolFunction]) -> MultiFunction:
    """Wrap per-output functions (dict order = output order)."""
    return MultiFunction(tuple(inputs), tuple(funcs), dict(funcs))


def target_sets(f: BoolFunction, form: Form) -> tuple[int, int, int]:
    """``(target_on, target_off, dc)``: what the cover of ``form`` must cover / avoid.

    SOP covers the ON-set; POS covers the OFF-set (cubes of the complement).
    """
    if form is Form.SOP:
        return f.on, f.off, f.dc
    return f.off, f.on, f.dc


def value_char(f: BoolFunction, m: int) -> str:
    """'1', '0' or 'X' for minterm ``m``."""
    if f.on >> m & 1:
        return "1"
    if f.dc >> m & 1:
        return "X"
    return "0"


def table_rows(mf: MultiFunction) -> list[tuple[str, str]]:
    """``(input_bits, output_chars)`` for every minterm, outputs in order, DC as 'X'."""
    rows = []
    for m in range(1 << mf.n):
        outs = "".join(value_char(mf.functions[o], m) for o in mf.outputs)
        rows.append((minterm_bits(m, mf.n), outs))
    return rows


def with_dont_cares(mf: MultiFunction, dc_mask: int) -> MultiFunction:
    """Copy of ``mf`` where minterms in ``dc_mask`` become don't cares for every output."""
    funcs = {}
    for name in mf.outputs:
        f = mf.functions[name]
        funcs[name] = function_from_sets(mf.n, f.on & ~dc_mask, f.dc | dc_mask)
    return MultiFunction(mf.inputs, mf.outputs, funcs)
