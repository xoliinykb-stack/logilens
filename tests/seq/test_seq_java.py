"""Cross-check of the extracted FSMs against the real Logisim engine (Java backend ``trace``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from logilens.backends import load_project
from logilens.seq import analyze_sequential, find_structure
from logilens.seq.validate import crosscheck

GEN = Path(__file__).resolve().parents[1] / "fixtures" / "gen"


def _check(path: Path, seed: int) -> None:
    project = load_project(path, backend="python")
    res = analyze_sequential(project, estimate_encodings=False)
    report = crosscheck(project, res.fsm, find_structure(project), backend="java", extra=30, seed=seed)
    assert report.backend == "java"
    assert report.covered == report.total, (report.covered, report.total)
    assert report.compared >= 2 * len(report.walk)
    assert report.mismatches == [], report.mismatches[:5]
    assert report.ok


@pytest.mark.java
@pytest.mark.parametrize("name", ["moore_fsm", "jk_flipflop", "d_flipflop"])
@pytest.mark.parametrize("seed", [0, 1])
def test_fixture_fsm_matches_logisim(name: str, seed: int) -> None:
    _check(GEN / f"{name}.circ", seed)


@pytest.mark.java
def test_mealy_matches_logisim(mealy_circ: Path) -> None:
    _check(mealy_circ, 0)


@pytest.mark.java
def test_t_counter_matches_logisim(t_counter_circ: Path) -> None:
    _check(t_counter_circ, 0)


@pytest.mark.java
def test_register_matches_logisim(register_circ: Path) -> None:
    _check(register_circ, 0)


@pytest.mark.java
def test_java_loaded_project_gives_same_fsm() -> None:
    pj = load_project(GEN / "moore_fsm.circ", backend="java")
    pp = load_project(GEN / "moore_fsm.circ", backend="python")
    fj, fp = analyze_sequential(pj, estimate_encodings=False).fsm, analyze_sequential(pp, estimate_encodings=False).fsm
    assert fj.delta == fp.delta and fj.lam == fp.lam
