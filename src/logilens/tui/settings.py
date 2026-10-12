"""Settings of one TUI session (from the global CLI options)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from logilens.analysis.options import Options
from logilens.i18n import DEFAULT_LANG


@dataclass
class TuiSettings:
    lang: str = DEFAULT_LANG
    backend: str = "auto"
    jar: str | None = None
    only: str | None = None  # gate-set restriction for lint ("nand,nor")
    forms: str = "both"  # SOP and POS for every group, so the K-map tab can toggle between them
    cwd: Path = field(default_factory=Path.cwd)

    def options(self, spec: str | Path | None, only: str | None) -> Options:
        return Options(spec=spec, only=only, backend=self.backend, jar=self.jar, lang=self.lang, forms=self.forms)


__all__ = ["TuiSettings"]
