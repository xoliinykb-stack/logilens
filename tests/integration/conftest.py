from __future__ import annotations

import pytest
from cli_support import Cli


@pytest.fixture(scope="session")
def cli() -> Cli:
    return Cli()
