"""Backend protocol and the shared truth-table result shape.

Truth table (plain dict, JSON-serializable)::

    {"circuit": "main", "backend": "java" | "python",
     "inputs":  [{"name": "a", "label": "a", "width": 1}, ...],     # Logisim order: pins by (y, x)
     "outputs": [{"name": "A_N", "label": "A_N", "width": 1}, ...],
     "rows":    [{"in": ["0", "1", ...], "out": ["1", "x", ...], "osc": False}, ...],  # MSB-first bit strings
     "notes":   [...], "tied": {...}}                               # "tied" only after tie_duplicate_inputs

``name`` is the unique analysis name (``Analyze.getPinLabels``: duplicates get a numeric suffix, unlabeled pins
get a..h / x,y,z,u,v,w,s,t); ``label`` is the raw label from the file. Rows enumerate inputs in binary order,
first input = most significant.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from logilens.core.netlist import CircuitNetlist, ProjectNetlist

TruthTableDict = dict[str, Any]
TraceDict = dict[str, Any]
DEFAULT_MAX_BITS = 20


@runtime_checkable
class Backend(Protocol):
    """What the analysis layer needs from a backend."""

    name: str

    def available(self) -> tuple[bool, str]:
        """(usable, human-readable reason when not)."""

    def load(self, path: str) -> ProjectNetlist:
        """Parse a `.circ` file into a netlist."""

    def truth_table(self, project: ProjectNetlist, circuit: str | None = None,
                    max_bits: int = DEFAULT_MAX_BITS) -> TruthTableDict:
        """Exhaustive table with a fresh simulation state per row."""

    def trace(self, project: ProjectNetlist, steps: list[str], circuit: str | None = None) -> TraceDict:
        """Sequential run: steps are ``"t"`` (clock tick) or comma-separated input bit strings."""


def pin_header(circ: CircuitNetlist) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Input/output column descriptions of a circuit."""
    ins = [{"name": p.name, "label": p.label, "width": p.width} for p in circ.inputs]
    outs = [{"name": p.name, "label": p.label, "width": p.width} for p in circ.outputs]
    return ins, outs


def tie_duplicate_inputs(table: TruthTableDict) -> TruthTableDict:
    """Merge input pins carrying the same raw label (e.g. two copies of a..e driving two halves).

    Keeps rows where all copies agree and drops the duplicate columns. The result's ``tied`` maps the kept
    column name to every merged name. Used for converter_draft.circ, whose halves each have their own a..e pins.
    """
    groups: dict[tuple[str, int], list[int]] = {}
    for i, col in enumerate(table["inputs"]):
        key = (col.get("label", "").strip(), col["width"])
        if key[0]:
            groups.setdefault(key, []).append(i)
    dup = [idx for idx in groups.values() if len(idx) > 1]
    if not dup:
        return {**table, "tied": {}}
    drop = {i for idx in dup for i in idx[1:]}
    keep = [i for i in range(len(table["inputs"])) if i not in drop]
    rows = [{**r, "in": [r["in"][i] for i in keep]} for r in table["rows"]
            if all(len({r["in"][i] for i in idx}) == 1 for idx in dup)]
    tied = {table["inputs"][idx[0]]["name"]: [table["inputs"][i]["name"] for i in idx] for idx in dup}
    notes = list(table.get("notes", [])) + [
        "inputs with identical labels were tied together: "
        + ", ".join(f"{k} = {' = '.join(v)}" for k, v in tied.items())]
    return {**table, "inputs": [table["inputs"][i] for i in keep], "rows": rows, "tied": tied, "notes": notes}
