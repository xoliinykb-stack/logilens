"""Sequential-circuit analysis: FSM extraction, transition table, minimization, encodings, excitation,
timing diagrams and transition graphs.

Entry point: :func:`analyze_sequential`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from logilens.core.netlist import ProjectNetlist
from logilens.seq.analysis import Analysis, analyze_fsm, reachable_from, render_table, rich_table
from logilens.seq.dot import to_dot, to_svg
from logilens.seq.dot import to_text as graph_text
from logilens.seq.encoding import Encoding, compare_encodings
from logilens.seq.excitation import Excitation, excitation_functions, excitation_table_text
from logilens.seq.extract import (
    MAX_INPUT_BITS,
    MAX_STATE_BITS,
    Extraction,
    Runner,
    SeqNotApplicable,
    SeqTooLarge,
    extract_fsm,
    find_structure,
)
from logilens.seq.fsm import FSM
from logilens.seq.state_min import Minimization, minimize_states, reduced_fsm
from logilens.seq.timing import Timing, parse_sequence, simulate_timing


@dataclass
class SeqResult:
    applicable: bool
    reason: str = ""
    circuit: str = ""
    fsm: FSM | None = None
    analysis: Analysis | None = None
    minimization: Minimization | None = None
    encodings: list[Encoding] = field(default_factory=list)
    excitation: Excitation | None = None
    timing: Timing | None = None
    dot: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def table_text(self) -> str:
        return render_table(self.fsm, self.analysis) if self.fsm and self.analysis else ""

    def graph_text(self, ascii_only: bool = False) -> str:
        if not self.fsm or not self.analysis:
            return ""
        return graph_text(self.fsm, self.analysis.reachable + self.analysis.unreachable, ascii_only)

    def svg(self) -> str | None:
        return to_svg(self.dot) if self.dot else None

    def to_dict(self) -> dict[str, Any]:
        fsm = self.fsm
        return {
            "applicable": self.applicable,
            "reason": self.reason,
            "circuit": self.circuit,
            "fsm": fsm.to_dict() if fsm else None,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "minimization": self.minimization.to_dict(fsm) if self.minimization else None,
            "encodings": [e.to_dict(fsm) for e in self.encodings],
            "excitation": self.excitation.to_dict() if self.excitation else None,
            "timing": self.timing.to_dict() if self.timing else None,
            "dot": self.dot,
            "warnings": list(self.warnings),
        }


def analyze_sequential(
    project: ProjectNetlist,
    circuit: str | None = None,
    input_sequence: str | int | Sequence[str] | Sequence[Mapping[str, Any]] | None = None,
    *,
    state_names: Mapping[str, str] | None = None,
    naming: str = "code",
    outputs_for_minimization: list[str] | None = None,
    estimate_encodings: bool = True,
    max_state_bits: int = MAX_STATE_BITS,
    max_input_bits: int = MAX_INPUT_BITS,
    encoding_time_limit: float = 20.0,
) -> SeqResult:
    """Full sequential analysis of ``circuit`` (default: main).

    ``state_names`` maps state codes (MSB-first over the state variables) to display names; ``naming='index'``
    names states ``S<code value>`` instead of by their code.
    """
    name = project.circuit(circuit).name
    try:
        fsm = extract_fsm(project, circuit, max_state_bits=max_state_bits, max_input_bits=max_input_bits,
                          state_names=dict(state_names or {}), naming=naming)
    except (SeqNotApplicable, SeqTooLarge) as exc:
        return SeqResult(False, str(exc), name)
    warnings = list(fsm.warnings)
    an = analyze_fsm(fsm)
    mini = minimize_states(fsm, an.reachable, outputs_for_minimization)
    excitation = excitation_functions(fsm, care=set(an.reachable))
    warnings += [f"excitation mismatch: {m}" for m in excitation.mismatches]
    encs: list[Encoding] = []
    if estimate_encodings:
        red = reduced_fsm(fsm, mini)
        order = [s for s in reachable_from(red, red.initial)]
        encs = compare_encodings(red, order, time_limit=encoding_time_limit)
        if not mini.is_minimal:
            for e in encs:
                e.notes.append(f"applied to the minimized machine ({mini.minimal_count} of "
                               f"{mini.original_count} states)")
    timing = None
    if input_sequence is not None:
        ex = find_structure(project, circuit)
        steps = parse_sequence(input_sequence, fsm)
        timing = simulate_timing(Runner(project, ex), fsm, steps)
        warnings += [f"timing: {m}" for m in timing.mismatches]
    dot = to_dot(fsm, an.reachable + an.unreachable, set(an.unreachable))
    return SeqResult(True, "", name, fsm, an, mini, encs, excitation, timing, dot, warnings)


__all__ = [
    "FSM", "Analysis", "CrossCheck", "Encoding", "Excitation", "Extraction", "Minimization", "SeqNotApplicable",
    "SeqResult", "SeqTooLarge", "Timing", "analyze_fsm", "analyze_sequential", "compare_encodings",
    "excitation_functions", "excitation_table_text", "extract_fsm", "find_structure", "minimize_states",
    "parse_sequence", "reduced_fsm", "render_table", "rich_table", "simulate_timing", "to_dot", "to_svg",
]


def __getattr__(name: str) -> Any:  # lazy: validate imports the backends
    if name in ("CrossCheck", "crosscheck", "covering_walk"):
        from logilens.seq import validate

        return getattr(validate, name)
    raise AttributeError(name)
