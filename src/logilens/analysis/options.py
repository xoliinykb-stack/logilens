"""Options of the analysis facade (shared by the CLI and the TUI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FORM_CHOICES = ("auto", "sop", "pos", "both")


@dataclass
class Options:
    """What :func:`logilens.analysis.service.analyze` should do.

    * ``spec`` / ``map_overrides`` — specification file and ``--map SPEC=LABEL[,LABEL]`` values;
    * ``only`` — gate-set restriction for lint (``"nand,nor"``);
    * ``methods`` — minimization methods (``None`` = all; ``ilp`` is always added for the proof);
    * ``forms`` — ``auto`` (SOP for NAND/AND-OR groups, POS for NOR/OR-AND, both when unclear), ``sop``, ``pos``,
      ``both``;
    * ``tie_duplicate_labels`` — ``None`` = automatic (enabled when input pins share a label, with a note).
    """

    spec: str | Path | None = None
    map_overrides: list[str] = field(default_factory=list)
    only: str | None = None
    methods: tuple[str, ...] | None = None
    forms: str = "auto"
    backend: str = "auto"
    jar: str | Path | None = None
    lang: str = "ru"
    tie_duplicate_labels: bool | None = None
    circuit: str | None = None
    outputs: list[str] | None = None
    minimize: bool = True
    robustness: bool = True
    kmaps: bool = True
    sequential: bool = True
    input_sequence: str | None = None
    render_image: bool = False
    max_bits: int = 20
    max_minimize_vars: int = 10

    def __post_init__(self) -> None:
        if self.forms not in FORM_CHOICES:
            raise ValueError(f"forms must be one of {', '.join(FORM_CHOICES)}, not {self.forms!r}")
