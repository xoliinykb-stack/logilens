"""Shared paths and an in-process CLI runner for the integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from logilens.cli.app import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONVERTER = str(FIXTURES / "converter_nand_nor.circ")
DRAFT = str(FIXTURES / "converter_draft.circ")
MIXED = str(FIXTURES / "mixed_gates.circ")
SPEC = str(FIXTURES / "converter.spec.txt")


class Cli:
    """Runs the typer app in-process."""

    def __init__(self) -> None:
        # Fixed width and no locale: output must not depend on the developer's terminal.
        self.runner = CliRunner(env={"COLUMNS": "200", "LANG": None, "LC_ALL": None, "LC_MESSAGES": None,
                                     "LOGILENS_LANG": None, "NO_COLOR": None})

    def __call__(self, *args: str) -> Any:
        return self.runner.invoke(app, list(args), catch_exceptions=False)

    def json(self, *args: str) -> tuple[int, dict[str, Any]]:
        result = self(*args)
        return result.exit_code, json.loads(result.stdout)
