"""Lint issue record and default (English) message templates.

``msg_key`` / ``fix_key`` are stable i18n keys; :data:`DEFAULT_TEXT` provides English templates formatted
with ``params`` so that a report can be rendered even without a translation catalog.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from logilens.core.geometry import Point


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]


@dataclass
class LintIssue:
    rule: str
    severity: Severity
    circuit: str
    loc: Point | None
    component: str | None  # e.g. "NOR (1170,300)"
    msg_key: str
    fix_key: str
    params: dict[str, Any] = field(default_factory=dict)
    related: list[Point] = field(default_factory=list)

    @property
    def is_problem(self) -> bool:
        """ERROR and WARNING count as problems ("0 problems" ignores INFO)."""
        return self.severity in (Severity.ERROR, Severity.WARNING)

    def message(self) -> str:
        return render(self.msg_key, self.params)

    def fix(self) -> str:
        return render(self.fix_key, self.params)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["loc"] = list(self.loc) if self.loc else None
        d["related"] = [list(p) for p in self.related]
        d["message"] = self.message()
        d["fix"] = self.fix()
        return d


def render(key: str, params: dict[str, Any]) -> str:
    """Format the English template of ``key`` (falls back to the key itself)."""
    template = DEFAULT_TEXT.get(key, key)
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template


DEFAULT_TEXT: dict[str, str] = {
    "lint.L001.msg": "input {input} of {component} is not connected (nothing at {point}); Logisim silently "
                     "ignores it and computes the gate from the remaining inputs",
    "lint.L001.msg.not": "the input of {component} is not connected (nothing at {point}); its output is E",
    "lint.L001.msg.ff": "input '{port}' of {component} is not connected (nothing at {point})",
    "lint.L001.fix": "draw a wire that ends exactly at {point}, or reduce the number of inputs",
    "lint.L002.msg": "wire end {point} touches nothing (no wire, no component port)",
    "lint.L002.fix": "extend the wire to the intended port or delete the loose piece",
    "lint.L003.msg": "output of {component} drives nothing",
    "lint.L003.fix": "connect the output or delete the unused gate",
    "lint.L004.msg": "net at {point} has {count} drivers: {drivers}",
    "lint.L004.fix": "only one output may drive a net; remove one connection (identical values hide this in "
                     "simulation)",
    "lint.L005.msg": "wire end {point} lies in the middle of another wire; Logisim connects them (implicit "
                     "junction)",
    "lint.L005.msg.port": "port {port} of {component} lies in the middle of a wire at {point}; Logisim connects "
                          "them",
    "lint.L005.fix": "fine if intended; otherwise move the wire end / component",
    "lint.L006.msg": "wires {first} and {second} overlap; Logisim merges them into one net",
    "lint.L006.fix": "delete the duplicate segment",
    "lint.L007.msg": "wire {wire} passes through the body of {component}",
    "lint.L007.fix": "route the wire around the component",
    "lint.L008.msg": "combinational loop without a flip-flop through {count} components: {members}",
    "lint.L008.fix": "break the loop or use a flip-flop (asynchronous feedback is a latch / oscillator)",
    "lint.L009.msg": "{count} pins share the label '{label}'",
    "lint.L009.fix": "give every pin a unique label (Logisim renames duplicates to {renamed})",
    "lint.L010.msg.space": "label '{label}' has leading/trailing whitespace",
    "lint.L010.msg.invalid": "label '{label}' is not an identifier; Logisim's analyzer calls it '{valid}'",
    "lint.L010.msg.case": "labels {labels} differ only in letter case",
    "lint.L010.msg.tunnel": "tunnel label '{label}' is used only once, so the tunnel connects nothing",
    "lint.L010.fix": "use consistent, unique identifiers",
    "lint.L011.msg": "{component} is not allowed (allowed: {allowed})",
    "lint.L011.msg.not": "{component} is not allowed (allowed: {allowed}); NOT counts as a separate gate type",
    "lint.L011.msg.negated": "{component} has negated input(s) {inputs}: each bubble is a hidden inverter",
    "lint.L011.fix": "rebuild with {allowed} gates only",
    "lint.L011.fix.not": "replace NOT by a {hint} gate with all inputs tied together",
    "lint.L011.fix.negated": "remove the bubbles and invert with a {hint} gate with tied inputs",
    "lint.L012.msg": "unsupported component '{name}' at {point}: {reason}",
    "lint.L012.msg.sim": "'{name}' at {point} is parsed but not simulated by the Python backend",
    "lint.L012.fix": "results involving this component are not checked; use the Java backend or remove it",
    "lint.L013.msg": "bit-width mismatch on the net at {point}: {widths}",
    "lint.L013.fix": "make all connected ports the same width (Logisim shows an orange 'incompatible widths' wire)",
    "lint.L014.msg": "{direction} pin at {point} has no label (Logisim calls it '{name}')",
    "lint.L014.fix": "label every input and output pin",
}
