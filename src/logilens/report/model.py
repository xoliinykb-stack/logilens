"""Report model produced by :func:`logilens.analysis.service.analyze` and consumed by every renderer.

Plain dataclasses. User-facing sentences are stored as :class:`Msg` (i18n key + parameters) so that one report can
be rendered in any language; numbers, covers and K-map views are stored as data.
Schema id: ``logilens/report@1`` (see :mod:`logilens.report.render_json`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from logilens.core.logic_types import Cover, Form, KMapView
from logilens.lint.issue import LintIssue
from logilens.logic.recover import StructuralCost

SCHEMA = "logilens/report@1"


class Verdict(str, Enum):
    """Per-group optimality verdict."""

    OPTIMAL = "optimal"
    IMPROVABLE = "improvable"
    BEYOND_TWO_LEVEL = "beyond_two_level"
    UNPROVEN = "unproven"
    NOT_APPLICABLE = "not_applicable"

    @property
    def rank(self) -> int:
        """Severity order for the overall verdict (higher = worse news)."""
        return {"optimal": 0, "not_applicable": 1, "unproven": 2, "beyond_two_level": 3, "improvable": 4}[self.value]


@dataclass(frozen=True)
class Msg:
    """Translatable message: i18n ``key`` + format ``params``."""

    key: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CostPair:
    """``gates / inputs`` pair."""

    gates: int
    inputs: int

    def short(self) -> str:
        return f"{self.gates}/{self.inputs}"


@dataclass(frozen=True)
class MethodRow:
    """One row of the method comparison table."""

    method: str
    form: Form
    gates: int | None
    inputs: int | None
    proof: str | None
    verified: bool
    runtime_s: float
    note: str = ""
    matches_reference: bool = False


@dataclass
class FormResult:
    """Minimization results of one group for one form (SOP = MDNF / NAND, POS = MKNF / NOR)."""

    form: Form
    rows: list[MethodRow] = field(default_factory=list)
    reference: CostPair | None = None  # proven optimum (ILP status Optimal)
    best_cover: Cover | None = None  # proven-optimal cover, else best verified heuristic cover
    best_cost: CostPair | None = None
    best_method: str | None = None
    proven: bool = False
    robustness: list[str] = field(default_factory=list)
    robust_identical: bool | None = None
    min_negators: int | None = None
    kmaps: list[KMapView] = field(default_factory=list)


@dataclass
class GroupReport:
    """Analysis of one output group (outputs sharing gates)."""

    index: int
    outputs: list[str]
    variables: list[str]
    function_source: str  # 'spec' | 'circuit'
    dc_count: dict[str, int] = field(default_factory=dict)
    technology: str | None = None  # 'nand' | 'nor' | 'and-or' | 'or-and' | 'wire' | 'mixed' | None
    recovered: str = "not_run"  # RecoverStatus value or 'not_run'
    recover_reasons: list[str] = field(default_factory=list)
    implemented_form: Form | None = None
    implemented_cover: Cover | None = None
    implemented_cost: CostPair | None = None  # NAND/NOR cost of the recovered cover
    implemented_kmaps: list[KMapView] = field(default_factory=list)
    structural: StructuralCost | None = None
    forms: list[FormResult] = field(default_factory=list)
    verdict: Verdict = Verdict.NOT_APPLICABLE
    verdict_form: Form | None = None
    delta: CostPair | None = None  # structural (NAND/NOR counting) minus optimum
    notes: list[Msg] = field(default_factory=list)

    def form_result(self, form: Form | None) -> FormResult | None:
        return next((f for f in self.forms if f.form is form), None)

    @property
    def title(self) -> str:
        return ", ".join(self.outputs)


@dataclass
class LintSection:
    issues: list[LintIssue] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    problems: int = 0
    only: str | None = None


@dataclass
class TruthSection:
    inputs: list[str]
    outputs: list[str]
    rows: list[tuple[str, str]]
    oscillating: int = 0
    tied: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SpecSection:
    path: str
    kind: str
    inputs: list[str]
    outputs: list[str]
    listed_rows: int
    mapping: dict[str, list[str]]
    how: dict[str, str]
    unmapped: list[str]
    passed: bool
    rows_checked: int
    rows_ok_by_group: dict[str, int]
    rows_ok_by_output_group: dict[str, int] = field(default_factory=dict)  # "x, y, z, u" -> rows correct
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    dc_differences: list[dict[str, Any]] = field(default_factory=list)
    missing_labels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SeqSection:
    status: str  # 'ok' | 'error' | 'skipped'
    data: dict[str, Any] | None = None
    message: str = ""


@dataclass
class Report:
    """Everything the renderers need."""

    file: str
    circuit: str
    backend: str
    source_version: str
    file_format: str
    lang: str = "ru"
    schema: str = SCHEMA
    tool_version: str = ""
    generated_at: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    circuits: list[str] = field(default_factory=list)
    is_sequential: bool = False
    comb_loops: int = 0
    notes: list[Msg] = field(default_factory=list)
    lint: LintSection = field(default_factory=LintSection)
    truth: TruthSection | None = None
    spec: SpecSection | None = None
    groups: list[GroupReport] = field(default_factory=list)
    seq: SeqSection | None = None
    limitations: list[Msg] = field(default_factory=list)
    recommendations: list[Msg] = field(default_factory=list)
    image_png: str | None = None  # base64 PNG of the circuit (Java render), HTML only

    @property
    def overall(self) -> Verdict:
        """Worst group verdict (NOT_APPLICABLE when there are no groups)."""
        if not self.groups:
            return Verdict.NOT_APPLICABLE
        return max((g.verdict for g in self.groups), key=lambda v: v.rank)

    @property
    def spec_passed(self) -> bool | None:
        return None if self.spec is None else self.spec.passed
