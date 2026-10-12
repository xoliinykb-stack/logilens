"""JSON rendering of a :class:`Report` (schema ``logilens/report@1``).

Translatable messages are emitted as ``{"key", "params", "text"}`` (``text`` in the report language); covers as
``{"form", "inputs", "terms": {output: [cube strings]}, "expressions": {output: formula}}``.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from logilens.core.geometry import Point
from logilens.core.logic_types import Cover, Cube, KMapGroup, KMapView
from logilens.i18n import issue_fix, issue_message
from logilens.lint.issue import LintIssue
from logilens.logic.recover import StructuralCost
from logilens.report.model import Msg, Report
from logilens.report.text import cover_formulas, derivations, msg


def cover_dict(cover: Cover) -> dict[str, Any]:
    return {
        "form": cover.form.value,
        "inputs": list(cover.inputs),
        "terms": {o: [c.to_str() for c in cubes] for o, cubes in cover.terms.items()},
        "expressions": dict(cover_formulas(cover, "ascii")),
        "nand_nor": {o: lines[-1].split(" = ", 1)[-1] for o, lines in zip(cover.terms, derivations(cover))},
    }


def kmap_dict(view: KMapView) -> dict[str, Any]:
    return {
        "output": view.output, "form": view.form.value, "variables": list(view.variables),
        "row_vars": list(view.row_vars), "col_vars": list(view.col_vars),
        "row_codes": list(view.row_codes), "col_codes": list(view.col_codes),
        "values": [list(r) for r in view.values],
        "groups": [_group_dict(g) for g in view.groups],
    }


def _group_dict(g: KMapGroup) -> dict[str, Any]:
    return {"cube": g.cube.to_str(), "label": g.label, "color": g.color, "rects": [list(r) for r in g.rects]}


def structural_dict(s: StructuralCost) -> dict[str, Any]:
    return {"gates": s.gates, "inputs": s.inputs, "nandnor_gates": s.nandnor_gates, "nandnor_inputs": s.nandnor_inputs,
            "not_gates": s.not_gates, "unconnected_inputs": s.unconnected_inputs,
            "negated_inputs": s.negated_inputs, "by_type": {k: list(v) for k, v in s.by_type.items()}}


def to_jsonable(value: Any, lang: str) -> Any:
    """Recursively convert report objects into JSON-compatible values."""
    if isinstance(value, Msg):
        return {"key": value.key, "params": to_jsonable(value.params, lang), "text": msg(value, lang)}
    if isinstance(value, LintIssue):
        d = value.to_dict()
        d["message"], d["fix"] = issue_message(value, lang), issue_fix(value, lang)
        return to_jsonable(d, lang)
    special = _special(value)
    if special is not None:
        return special
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name), lang) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k.value if isinstance(k, Enum) else k): to_jsonable(v, lang) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v, lang) for v in value]
    return value


def _special(value: Any) -> Any:
    if isinstance(value, Cover):
        return cover_dict(value)
    if isinstance(value, KMapView):
        return kmap_dict(value)
    if isinstance(value, Cube):
        return value.to_str()
    if isinstance(value, StructuralCost):
        return structural_dict(value)
    if isinstance(value, Point):
        return [value.x, value.y]
    return None


def report_dict(report: Report, lang: str | None = None) -> dict[str, Any]:
    """The whole report as a JSON-compatible dict (``schema`` first, derived fields added)."""
    lang = lang or report.lang
    body = to_jsonable(report, lang)
    body["lang"] = lang
    body["overall_verdict"] = report.overall.value
    body["spec_passed"] = report.spec_passed
    return {"schema": report.schema, **{k: v for k, v in body.items() if k != "schema"}}


def render(report: Report, lang: str | None = None, indent: int | None = 2) -> str:
    return json.dumps(report_dict(report, lang), ensure_ascii=False, indent=indent)


def dumps(data: Any, lang: str = "en", indent: int | None = 2) -> str:
    """JSON text of any report fragment (used by the CLI for ``lint --json`` etc.)."""
    return json.dumps(to_jsonable(data, lang), ensure_ascii=False, indent=indent)
