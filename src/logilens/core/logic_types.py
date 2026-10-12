"""Shared dataclasses of the logic core: functions, cubes, covers, costs, proofs and results.

Conventions:

* ``n`` inputs, names MSB-first. Minterm ``m``: input ``i`` (0-based, first = MSB) has value
  ``(m >> (n - 1 - i)) & 1``.
* A Boolean function is three disjoint bitmasks over the ``2**n`` minterms (bit ``m`` set = minterm ``m``).
* A :class:`Cube` stores ``care``/``value`` masks in the same bit order (bit ``n-1`` = first input) and an
  optional output-tag bitmask for multi-output covers.

This module contains data only (plus trivial derived properties); algorithms live in ``logic/`` and
``minimize/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Form(str, Enum):
    """Two-level form. SOP covers the ON-set (MDNF, NAND-NAND); POS covers the OFF-set (MKNF, NOR-NOR)."""

    SOP = "SOP"
    POS = "POS"

    @property
    def negated_char(self) -> str:
        """Cube character that denotes a complemented literal in this form."""
        return "0" if self is Form.SOP else "1"

    @property
    def tech(self) -> str:
        """Gate technology that implements the form."""
        return "nand" if self is Form.SOP else "nor"


class Objective(str, Enum):
    """Lexicographic cost objectives used by exact minimizers and robustness checks."""

    GATES_INPUTS = "gates_inputs"
    INPUTS_GATES = "inputs_gates"
    GATES_NO_NEGATORS = "gates_no_negators"
    MIN_NEGATORS = "min_negators"


@dataclass(frozen=True)
class BoolFunction:
    """Incompletely specified single-output function as disjoint ON/OFF/DC minterm bitmasks."""

    n: int
    on: int
    off: int
    dc: int

    def __post_init__(self) -> None:
        full = (1 << (1 << self.n)) - 1
        if self.on & self.off or self.on & self.dc or self.off & self.dc:
            raise ValueError("on/off/dc sets must be disjoint")
        if (self.on | self.off | self.dc) != full:
            raise ValueError("on/off/dc sets must cover all 2**n minterms")


@dataclass(frozen=True)
class MultiFunction:
    """Multi-output function (truth table): input names MSB-first, ordered outputs."""

    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    functions: dict[str, BoolFunction]

    @property
    def n(self) -> int:
        """Number of inputs."""
        return len(self.inputs)


TruthTable = MultiFunction


@dataclass(frozen=True, order=True)
class Cube:
    """Product term (SOP) or complement cube (POS) over ``n`` variables.

    ``care`` bit ``n-1-i`` set means variable ``i`` is present; ``value`` gives its polarity.
    ``outputs`` is an output-tag bitmask (bit ``k`` = k-th output) used by multi-output methods.
    """

    n: int
    care: int
    value: int
    outputs: int = 0

    @property
    def key(self) -> tuple[int, int]:
        """Identity of the cube ignoring the output tag."""
        return (self.care, self.value)

    @property
    def num_literals(self) -> int:
        """Number of literals (present variables)."""
        return self.care.bit_count()

    def to_str(self) -> str:
        """Positional string, e.g. ``'--101'`` ('-' absent, '1'/'0' value of the variable)."""
        chars = []
        for i in range(self.n):
            bit = 1 << (self.n - 1 - i)
            chars.append("-" if not self.care & bit else ("1" if self.value & bit else "0"))
        return "".join(chars)

    def __str__(self) -> str:
        return self.to_str()


@dataclass(frozen=True)
class Cover:
    """Two-level cover: for each output the cubes used (SOP: ON-set cubes; POS: OFF-set cubes)."""

    form: Form
    inputs: tuple[str, ...]
    terms: dict[str, tuple[Cube, ...]]

    def distinct_cubes(self) -> list[Cube]:
        """Distinct cubes (by ``key``) in first-use order, output tags cleared."""
        seen: dict[tuple[int, int], Cube] = {}
        for cubes in self.terms.values():
            for c in cubes:
                seen.setdefault(c.key, Cube(c.n, c.care, c.value))
        return list(seen.values())


@dataclass(frozen=True)
class CostModel:
    """Parameters of the NAND/NOR cost model.

    * ``not_as_tied_gate``: a NOT is a NAND/NOR with tied inputs (1 gate / 2 inputs); else 1 gate / 1 input.
    * ``single_literal_free``: an output equal to one literal needs no gate; else it is driven by an output
      gate fed with the opposite literal (like a one-literal term in the second level).
    * ``complemented_inputs_available``: complemented variables are free (no negators counted).
    """

    tech: str = "nand"
    not_as_tied_gate: bool = True
    single_literal_free: bool = True
    complemented_inputs_available: bool = False
    objective: Objective = Objective.GATES_INPUTS


@dataclass(frozen=True)
class Cost:
    """Cost of a cover. ``inverters`` = input negators; output inverters are in ``breakdown``."""

    gates: int
    inputs: int
    inverters: int
    breakdown: dict[str, object] = field(default_factory=dict)

    def short(self) -> str:
        """``'22/64'`` style text."""
        return f"{self.gates}/{self.inputs}"


@dataclass(frozen=True)
class Proof:
    """Evidence of optimality. ``kind``: 'ilp' | 'bnb' | 'exhaustive' | 'none'."""

    kind: str
    status: str
    objective: float | None = None
    mip_gap: float | None = None
    solver: str | None = None

    @property
    def optimal(self) -> bool:
        """True when the solver/search proved optimality."""
        return self.status.lower() == "optimal"


@dataclass(frozen=True)
class Step:
    """Human-readable teaching step (QM grouping, merges, prime chart, Petrick product, ...)."""

    kind: str
    title: str
    lines: tuple[str, ...] = ()
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class MinimizationResult:
    """Outcome of one minimization method for one form (cover is None when infeasible/failed)."""

    method: str
    form: Form
    multi_output: bool
    cover: Cover | None
    cost: Cost | None
    proof: Proof | None = None
    verified: bool = False
    runtime_s: float = 0.0
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CodeRow:
    """One row of a code-table specification (``number input output``)."""

    number: int | None
    inputs: str
    outputs: str


@dataclass(frozen=True)
class Spec:
    """Specification. ``rows`` maps minterm -> output chars ('0', '1', '-') in ``outputs`` order.

    ``unlisted`` says what minterms absent from ``rows`` mean: 'dc', '0' or '1'.
    ``kind``: 'codes' | 'table' | 'expr'.
    """

    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    rows: dict[int, str]
    unlisted: str = "dc"
    codes: tuple[CodeRow, ...] = ()
    source: str = ""
    kind: str = "table"


@dataclass(frozen=True)
class KMapGroup:
    """A cube drawn on a K-map: rectangles are (row0, col0, row1, col1) inclusive cell ranges."""

    cube: Cube
    label: str
    color: str
    rects: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True)
class KMapView:
    """Renderer-independent K-map: cell values ('0', '1', 'X'), axis codes, variable bars and groups."""

    output: str
    variables: tuple[str, ...]
    row_vars: tuple[str, ...]
    col_vars: tuple[str, ...]
    row_codes: tuple[str, ...]
    col_codes: tuple[str, ...]
    values: tuple[tuple[str, ...], ...]
    minterms: tuple[tuple[int, ...], ...]
    row_bars: dict[str, tuple[int, ...]]
    col_bars: dict[str, tuple[int, ...]]
    groups: tuple[KMapGroup, ...] = ()
    form: Form = Form.SOP
