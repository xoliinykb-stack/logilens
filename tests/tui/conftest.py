"""Fixtures of the TUI tests (helpers live in ``tui_support``)."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tui_support import CONVERTER, DRAFT, MOORE, SPEC

from logilens.tui.app import LogilensApp


@pytest.fixture
def make_app(tmp_path: Path) -> Callable[..., LogilensApp]:
    def factory(file: Path | None = None, spec: Path | None = None, **kw: Any) -> LogilensApp:
        kw.setdefault("backend", "python")
        kw.setdefault("recent_path", tmp_path / "config" / "recent.json")
        kw.setdefault("cwd", tmp_path)
        return LogilensApp(file, spec, **kw)

    return factory


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    """Copies of the fixtures in a temporary folder (exports are written next to the circuit)."""
    root = tmp_path / "work"
    root.mkdir()
    for src in (CONVERTER, DRAFT, SPEC, MOORE):
        shutil.copy(src, root / src.name)
    return root
