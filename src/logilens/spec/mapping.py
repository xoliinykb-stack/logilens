"""Map specification outputs (and inputs) to circuit pin labels.

Rules per spec output, first match wins: explicit override; exact label; case-insensitive label;
label prefix before ``_`` (``A`` -> ``A_N`` and ``A_R``), exact then case-insensitive.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class OutputMapping:
    """Spec output -> circuit labels, how each was matched, and leftovers."""

    mapping: dict[str, tuple[str, ...]]
    how: dict[str, str]
    unmapped_spec: tuple[str, ...]
    unused_labels: tuple[str, ...]

    def lines(self) -> list[str]:
        """``'A -> A_N, A_R (prefix)'`` lines for printing."""
        out = [f"{o} -> {', '.join(ls)} ({self.how[o]})" for o, ls in self.mapping.items()]
        out += [f"{o} -> (no circuit output)" for o in self.unmapped_spec]
        return out


def _prefix(label: str) -> str:
    return label.split("_", 1)[0]


def _match(output: str, labels: list[str]) -> tuple[list[str], str]:
    rules = (
        ("exact", lambda lab: lab == output),
        ("case-insensitive", lambda lab: lab.lower() == output.lower()),
        ("prefix", lambda lab: "_" in lab and _prefix(lab) == output),
        ("prefix, case-insensitive", lambda lab: "_" in lab and _prefix(lab).lower() == output.lower()),
    )
    for how, rule in rules:
        hits = [lab for lab in labels if rule(lab)]
        if hits:
            return hits, how
    return [], ""


def map_outputs(
    spec_outputs: Iterable[str], labels: Iterable[str], overrides: Mapping[str, Iterable[str] | str] | None = None
) -> OutputMapping:
    """Map every spec output to circuit output labels (see module doc)."""
    labels = list(labels)
    spec_outputs = list(spec_outputs)
    for out, target in (overrides or {}).items():
        if out not in spec_outputs:
            raise ValueError(f"--map: the specification has no output {out!r} (outputs: {', '.join(spec_outputs)})")
        missing = [t for t in ([target] if isinstance(target, str) else target) if t not in labels]
        if missing:
            raise ValueError(f"--map: the circuit has no output labelled {missing[0]!r} (outputs: {', '.join(labels)})")
    mapping: dict[str, tuple[str, ...]] = {}
    how: dict[str, str] = {}
    unmapped: list[str] = []
    for out in spec_outputs:
        if overrides and out in overrides:
            target = overrides[out]
            mapping[out] = (target,) if isinstance(target, str) else tuple(target)
            how[out] = "override"
            continue
        hits, rule = _match(out, labels)
        if hits:
            mapping[out], how[out] = tuple(hits), rule
        else:
            unmapped.append(out)
    used = {lab for ls in mapping.values() for lab in ls}
    return OutputMapping(mapping, how, tuple(unmapped), tuple(lab for lab in labels if lab not in used))


def parse_map_args(items: Iterable[str]) -> dict[str, list[str]]:
    """Parse ``--map`` values like ``'A=A_N,A_R'`` (several items allowed, ``;`` also separates pairs)."""
    out: dict[str, list[str]] = {}
    for item in items:
        for pair in item.split(";"):
            if not pair.strip():
                continue
            name, sep, targets = pair.partition("=")
            if not sep or not name.strip() or not targets.strip():
                raise ValueError(f"bad --map value {pair!r}; expected SPEC=LABEL[,LABEL...]")
            out.setdefault(name.strip(), []).extend(t.strip() for t in targets.split(",") if t.strip())
    return out


def map_inputs(spec_inputs: Iterable[str], circuit_inputs: Iterable[str]) -> list[int] | None:
    """Position of each spec input in the circuit input order (exact, then case-insensitive); None if not
    every spec input is found."""
    circ = list(circuit_inputs)
    positions = []
    for name in spec_inputs:
        if name in circ:
            positions.append(circ.index(name))
            continue
        lowered = [c.lower() for c in circ]
        if name.lower() not in lowered:
            return None
        positions.append(lowered.index(name.lower()))
    return positions
