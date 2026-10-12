"""Compare a circuit truth table with a :class:`Spec`.

The circuit table may be oriented either way:

* ``{input_bits: {label: value}}`` (row-major), or
* ``{label: {input_bits: value}}`` (per label),

where ``input_bits`` is an MSB-first bit string in circuit input order (or an int minterm) and values are
``0/1`` (int or str), ``'x'`` (floating) or ``'E'`` (error). Floating/error values never match.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from logilens.core.logic_types import Spec
from logilens.logic.truth_table import minterm_bits
from logilens.spec.mapping import OutputMapping, map_inputs

Table = Mapping[object, Mapping[object, object]]


@dataclass(frozen=True)
class Mismatch:
    """A specified value the circuit does not produce."""

    minterm: int
    inputs: str
    output: str
    label: str
    expected: str
    actual: str


@dataclass(frozen=True)
class DCDifference:
    """Don't-care row where circuit outputs implementing the same spec output differ (info only)."""

    minterm: int
    inputs: str
    output: str
    values: dict[str, str]


@dataclass
class CheckResult:
    """Outcome of :func:`check_against_spec`."""

    mismatches: list[Mismatch] = field(default_factory=list)
    dc_differences: list[DCDifference] = field(default_factory=list)
    rows_checked: int = 0
    rows_ok_by_group: dict[str, int] = field(default_factory=dict)
    missing_labels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """No mismatches and every mapped label present."""
        return not self.mismatches and not self.missing_labels

    def summary(self) -> list[str]:
        """``'*_D: 16/16 rows correct'`` style lines."""
        return [f"{group}: {ok}/{self.rows_checked} rows correct" for group, ok in self.rows_ok_by_group.items()]


def _norm_value(v: object) -> str:
    text = str(v).strip()
    if text in ("0", "1"):
        return text
    if text.lower() in ("x", "u", "z", "-"):
        return "x"
    return "E"


def _row_major(table: Table, labels: set[str]) -> dict[object, Mapping[object, object]]:
    """Normalize to ``{row_key: {label: value}}``."""
    keys = list(table)
    if keys and all(isinstance(k, str) and k in labels for k in keys):
        rows: dict[object, dict[object, object]] = {}
        for label, col in table.items():
            for row_key, value in col.items():
                rows.setdefault(row_key, {})[label] = value
        return rows  # type: ignore[return-value]
    return dict(table)


def _row_index(rows: Mapping[object, object], n: int, perm: Sequence[int] | None) -> dict[int, object]:
    """Map spec minterms to the table's row keys (handles input permutation and int/str keys)."""
    out: dict[int, object] = {}
    for key in rows:
        bits = key if isinstance(key, str) else minterm_bits(int(key), n)  # type: ignore[call-overload]
        bits = bits.replace(" ", "")
        if perm is not None:
            bits = "".join(bits[p] for p in perm)
        out[int(bits, 2)] = key
    return out


def _group(label: str) -> str:
    return "*_" + label.split("_", 1)[1] if "_" in label else label


def check_against_spec(
    table: Table,
    spec: Spec,
    mapping: OutputMapping,
    circuit_inputs: Sequence[str] | None = None,
) -> CheckResult:
    """Mismatches on specified rows, plus DC rows where same-spec-output labels disagree."""
    result = CheckResult()
    labels = {lab for ls in mapping.mapping.values() for lab in ls}
    rows = _row_major(table, labels)
    perm = map_inputs(spec.inputs, circuit_inputs) if circuit_inputs else None
    if circuit_inputs and perm is None:
        result.notes.append("circuit inputs do not match spec inputs by name; positional order assumed")
    index = _row_index(rows, len(spec.inputs), perm)
    present = {lab for r in rows.values() for lab in r}
    result.missing_labels = sorted(labels - present)
    groups = sorted({_group(lab) for lab in labels})
    result.rows_ok_by_group = {g: 0 for g in groups}
    n = len(spec.inputs)
    for m in range(1 << n):
        expected = spec.rows.get(m)
        row = rows.get(index[m], {}) if m in index else {}
        if expected is None:
            expected = {"dc": "-", "0": "0", "1": "1"}[spec.unlisted] * len(spec.outputs)
            listed = False
        else:
            listed = True
        if listed:
            result.rows_checked += 1
        if m not in index:
            if listed:
                result.notes.append(f"row {minterm_bits(m, n)} missing from circuit table")
            continue
        bad_groups = _check_row(result, spec, mapping, m, expected, row)
        if listed:
            for g in groups:
                if g not in bad_groups:
                    result.rows_ok_by_group[g] += 1
    return result


def _check_row(
    result: CheckResult, spec: Spec, mapping: OutputMapping, m: int, expected: str, row: Mapping[object, object]
) -> set[str]:
    bits = minterm_bits(m, len(spec.inputs))
    bad: set[str] = set()
    for k, out in enumerate(spec.outputs):
        want = expected[k]
        values = {lab: _norm_value(row[lab]) for lab in mapping.mapping.get(out, ()) if lab in row}
        if want == "-":
            if len(set(values.values())) > 1:
                result.dc_differences.append(DCDifference(m, bits, out, values))
            continue
        for lab, got in values.items():
            if got != want:
                result.mismatches.append(Mismatch(m, bits, out, lab, want, got))
                bad.add(_group(lab))
    return bad
