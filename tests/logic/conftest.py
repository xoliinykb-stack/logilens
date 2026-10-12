"""Shared fixtures for logic-core tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from logilens.core.logic_types import MultiFunction, Spec
from logilens.spec.parse import load_spec, spec_function

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="session")
def conv_spec() -> Spec:
    """Line-code converter code-table specification."""
    return load_spec(FIXTURES / "converter.spec.txt")


@pytest.fixture(scope="session")
def conv(conv_spec: Spec) -> MultiFunction:
    """Line-code converter multi-output function (unlisted inputs = don't care)."""
    return spec_function(conv_spec)
