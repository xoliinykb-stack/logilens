"""Spec -> circuit output mapping with two fallbacks for unlabeled circuits.

1. :func:`logilens.spec.mapping.map_outputs` (override, exact, case-insensitive, ``A`` -> ``A_*`` prefix);
2. *function*: an unused circuit output that agrees with exactly one still-unmapped spec output on every specified
   row is mapped to it (e.g. the unlabeled outputs of converter_draft.circ);
3. *position*: remaining spec outputs are mapped to the i-th output of every output group that has exactly as many
   unused outputs as there are spec outputs (printed so that the user can correct it with ``--map``).
"""

from __future__ import annotations

from collections.abc import Sequence

from logilens.analysis.tables import TableView
from logilens.core.logic_types import Spec
from logilens.spec.mapping import OutputMapping, map_inputs, map_outputs


def _agrees(view: TableView, spec: Spec, perm: list[int], spec_k: int, out_k: int) -> bool:
    checked = 0
    for bits, outs in view.rows:
        spec_bits = "".join(bits[p] for p in perm)
        want = spec.rows.get(int(spec_bits, 2)) if spec_bits else None
        if want is None or want[spec_k] == "-":
            continue
        checked += 1
        if outs[out_k] != want[spec_k]:
            return False
    return checked > 0


def _by_function(view: TableView, spec: Spec, todo: list[str], unused: list[str]) -> dict[str, list[str]]:
    perm = map_inputs(spec.inputs, view.inputs)
    if perm is None:
        return {}
    matches: dict[str, list[str]] = {}
    for label in unused:
        k = view.outputs.index(label)
        hits = [s for s in todo if _agrees(view, spec, perm, spec.outputs.index(s), k)]
        if len(hits) == 1:
            matches.setdefault(hits[0], []).append(label)
    return matches


def _by_position(todo: list[str], spec: Spec, groups: Sequence[Sequence[str]], unused: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    ordered = [s for s in spec.outputs if s in todo]
    if len(ordered) != len(spec.outputs):
        return out
    for group in groups:
        if len(group) == len(ordered) and all(lab in unused for lab in group):
            for s, lab in zip(ordered, group):
                out.setdefault(s, []).append(lab)
    return out


def map_spec_outputs(
    spec: Spec, view: TableView, groups: Sequence[Sequence[str]], overrides: dict[str, list[str]] | None = None
) -> OutputMapping:
    """Full mapping with the fallbacks described in the module docstring."""
    base = map_outputs(spec.outputs, view.outputs, overrides)
    mapping = dict(base.mapping)
    how = dict(base.how)
    todo = list(base.unmapped_spec)
    used = {lab for labels in mapping.values() for lab in labels}
    for rule in ("function", "position"):
        if not todo:
            break
        if rule == "function":
            found = _by_function(view, spec, todo, [o for o in view.outputs if o not in used])
        else:
            found = _by_position(todo, spec, groups, set(view.outputs) - used)
        for s, labels in found.items():
            mapping[s] = tuple(labels)
            how[s] = rule
            used.update(labels)
        todo = [s for s in todo if s not in mapping]
    ordered = {s: mapping[s] for s in spec.outputs if s in mapping}
    return OutputMapping(ordered, {s: how[s] for s in ordered}, tuple(todo),
                         tuple(o for o in view.outputs if o not in used))
