"""Analysis facade shared by the CLI and the TUI."""

from logilens.analysis.options import Options
from logilens.analysis.service import analyze

__all__ = ["Options", "analyze"]
