"""Truth-table plumbing for the analysis service: backend table dict -> functions over chosen variables."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from logilens.backends.base import TruthTableDict
from logilens.core.logic_types import BoolFunction, MultiFunction, Spec
from logilens.logic.truth_table import function_from_sets, minterm_bits, multi_from_functions
from logilens.spec.mapping import OutputMapping, map_inputs
from logilens.spec.parse import spec_function


@dataclass(frozen=True)
class TableView:
    """A truth table with single-bit columns: input names, output names and rows of chars."""

    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    rows: tuple[tuple[str, str], ...]  # (input bits, output chars) per row, chars '0' '1' 'x' 'E'
    oscillating: int

    @property
    def n(self) -> int:
        return len(self.inputs)

    def row_major(self) -> dict[str, dict[str, str]]:
        """``{input_bits: {output: value}}`` as :func:`check_against_spec` expects."""
        return {bits: dict(zip(self.outputs, outs)) for bits, outs in self.rows}


def single_bit(table: TruthTableDict) -> bool:
    """True when every pin of the table is one bit wide."""
    return all(c["width"] == 1 for c in table["inputs"] + table["outputs"])


def table_view(table: TruthTableDict) -> TableView:
    """Flatten a backend table (single-bit pins) into a :class:`TableView`."""
    rows = []
    osc = 0
    for r in table["rows"]:
        rows.append(("".join(r["in"]), "".join(r["out"])))
        osc += bool(r.get("osc"))
    return TableView(tuple(c["name"] for c in table["inputs"]), tuple(c["name"] for c in table["outputs"]),
                     tuple(rows), osc)


def circuit_functions(view: TableView, outputs: Sequence[str], variables: Sequence[str]) -> dict[str, BoolFunction]:
    """Behavior of ``outputs`` over ``variables`` (other inputs held at 0; undefined values become DC)."""
    pos = [view.inputs.index(v) for v in variables]
    others = [i for i in range(view.n) if i not in pos]
    out_idx = {o: view.outputs.index(o) for o in outputs}
    n = len(variables)
    on = dict.fromkeys(outputs, 0)
    dc = dict.fromkeys(outputs, 0)
    seen = 0
    for bits, outs in view.rows:
        if any(bits[i] != "0" for i in others):
            continue
        m = int("".join(bits[i] for i in pos), 2) if pos else 0
        seen |= 1 << m
        for o, k in out_idx.items():
            ch = outs[k]
            if ch == "1":
                on[o] |= 1 << m
            elif ch not in "0":
                dc[o] |= 1 << m
    missing = ((1 << (1 << n)) - 1) & ~seen
    return {o: function_from_sets(n, on[o], dc[o] | missing) for o in outputs}


def multi(variables: Iterable[str], functions: Mapping[str, BoolFunction]) -> MultiFunction:
    return multi_from_functions(tuple(variables), dict(functions))


def spec_functions(
    spec: Spec, mapping: OutputMapping, outputs: Sequence[str], variables: Sequence[str]
) -> dict[str, BoolFunction] | None:
    """Spec behavior (with DCs) of every circuit output in ``outputs`` that is mapped, over ``variables``.

    Returns None when the spec inputs cannot be matched with ``variables`` one-to-one.
    """
    perm = map_inputs(spec.inputs, variables)
    if perm is None or len(spec.inputs) != len(variables) or len(set(perm)) != len(perm):
        return None
    mf = spec_function(spec)
    n = len(variables)
    owner = {lab: out for out, labels in mapping.mapping.items() for lab in labels}
    result: dict[str, BoolFunction] = {}
    for o in outputs:
        spec_out = owner.get(o)
        if spec_out is None:
            continue
        f = mf.functions[spec_out]
        on = dc = 0
        for m in range(1 << n):
            bits = minterm_bits(m, n)
            sm = int("".join(bits[p] for p in perm), 2)  # spec input j sits at circuit variable perm[j]
            if f.on >> sm & 1:
                on |= 1 << m
            elif f.dc >> sm & 1:
                dc |= 1 << m
        result[o] = function_from_sets(n, on, dc)
    return result
