"""Tests marked ``java`` run only when Java and a Logisim jar are found; elsewhere they are skipped."""

from __future__ import annotations

import pytest

from logilens.backends.java.locate import find_jar, find_java


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if find_java() is not None and find_jar() is not None:
        return
    skip = pytest.mark.skip(reason="java or Logisim jar not available")
    for item in items:
        if "java" in item.keywords:
            item.add_marker(skip)
