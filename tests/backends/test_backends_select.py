"""Backend selection, jar lookup, public API, and (marked `java`) cross-validation against real Logisim."""

from __future__ import annotations

from pathlib import Path

import pytest

from logilens.backends import load_project, select_backend, truth_table
from logilens.backends.base import tie_duplicate_inputs
from logilens.backends.crossval import crossval
from logilens.backends.java.locate import find_jar, jar_candidates
from logilens.backends.python_backend import PythonBackend
from logilens.backends.select import trace
from logilens.core.errors import BackendError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ALL = sorted(FIXTURES.glob("*.circ")) + sorted((FIXTURES / "gen").glob("*.circ"))


def test_python_backend_selected_explicitly() -> None:
    backend, warnings = select_backend("python")
    assert isinstance(backend, PythonBackend) and warnings == []
    with pytest.raises(ValueError):
        select_backend("bogus")


def test_jar_lookup_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    jar = tmp_path / "logisim.jar"
    jar.write_bytes(b"x")
    monkeypatch.setenv("LOGISIM_JAR", str(jar))
    monkeypatch.setenv("LOGILENS_HOME", str(tmp_path / "home"))
    sources = [c.source for c in jar_candidates("/nonexistent/explicit.jar")]
    assert sources[:2] == ["argument", "env"] and sources[-2:] == ["app", "cache"] and "home" in sources
    assert find_jar() == jar
    assert find_jar("/nonexistent/explicit.jar") is None  # an explicit wrong path is not silently replaced


def test_explicit_java_with_bad_jar_raises() -> None:
    with pytest.raises(BackendError):
        select_backend("java", jar="/nonexistent/logisim.jar")


def test_auto_without_jar_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("logilens.backends.select.find_jar", lambda jar=None: None)
    project = load_project(FIXTURES / "mixed_gates.circ")
    assert project.backend == "python"
    assert any("Python backend" in n for n in project.notes)


def test_tie_duplicate_inputs_noop_without_duplicates() -> None:
    table = truth_table(load_project(FIXTURES / "mixed_gates.circ", backend="python"))
    assert tie_duplicate_inputs(table)["rows"] == table["rows"]


# ------------------------------------------------------------------ Java (real Logisim)
@pytest.mark.java
@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_crossval_ports_pins_nets_tables(path: Path) -> None:
    report = crossval(path)
    for c in report.circuits:
        assert c.component_mismatches == [], c.component_mismatches
        assert c.port_mismatches == [], c.port_mismatches
        assert c.pin_mismatches == [], c.pin_mismatches
        assert c.net_mismatches == [], c.net_mismatches
        assert c.table_mismatches == [], c.table_mismatches
        assert c.ports_compared > 0
    assert report.ok


@pytest.mark.java
@pytest.mark.parametrize("name", ["converter_nand_nor", "converter_draft", "mixed_gates", "sample_bcd_excess3"])
def test_truth_tables_identical(name: str) -> None:
    project = load_project(FIXTURES / f"{name}.circ", backend="java")
    assert project.backend == "java"
    tj = truth_table(project)
    tp = truth_table(project, backend="python")
    assert tj["backend"] == "java" and tp["backend"] == "python"
    assert tj["inputs"] == tp["inputs"] and tj["outputs"] == tp["outputs"]
    assert tj["rows"] == tp["rows"]


@pytest.mark.java
def test_java_ports_equal_python_ports() -> None:
    pj = load_project(FIXTURES / "converter_draft.circ", backend="java")
    pp = load_project(FIXTURES / "converter_draft.circ", backend="python")
    for cj, cp in zip(pj.main_circuit.components, pp.main_circuit.components):
        assert [p.loc for p in cj.ports] == [p.loc for p in cp.ports]
        assert [p.name for p in cj.ports] == [p.name for p in cp.ports]


@pytest.mark.java
@pytest.mark.parametrize(("name", "steps"), [
    ("moore_fsm", ["0,1", "1,0", "t", "t", "t", "t", "t", "t", "t", "t", "0,0", "t", "t", "1,0", "t", "t"]),
    ("d_flipflop", ["1", "t", "t", "0", "t", "1", "t"]),
    ("jk_flipflop", ["1,0,0,0", "1,0,1,0", "1,0,0,0", "1,1,0,0", "1,1,1,0", "1,1,0,0", "1,1,1,0", "1,1,0,1"]),
])
def test_sequential_traces_identical(name: str, steps: list[str]) -> None:
    project = load_project(FIXTURES / "gen" / f"{name}.circ", backend="python")
    tj = trace(project, steps, backend="java")
    tp = trace(project, steps, backend="python")
    assert [r["out"] for r in tj["rows"]] == [r["out"] for r in tp["rows"]]


@pytest.mark.java
def test_java_error_becomes_backend_error(tmp_path: Path) -> None:
    from logilens.backends.java.backend import JavaBridge

    with pytest.raises(BackendError):
        JavaBridge().table(str(FIXTURES / "mixed_gates.circ"), "no-such-circuit")
