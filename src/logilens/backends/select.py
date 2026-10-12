"""Backend selection and the two entry points used by the CLI / report layer."""

from __future__ import annotations

import os
from functools import lru_cache

from logilens.backends.base import DEFAULT_MAX_BITS, Backend, TruthTableDict, tie_duplicate_inputs
from logilens.backends.java.backend import JavaBackend
from logilens.backends.java.locate import find_jar, find_java
from logilens.backends.python_backend import PythonBackend
from logilens.core.errors import BackendError
from logilens.core.netlist import ProjectNetlist

BACKENDS = ("auto", "java", "python")


@lru_cache(maxsize=8)
def _java(jar: str | None) -> JavaBackend:
    return JavaBackend(jar)


def select_backend(name: str = "auto", jar: str | os.PathLike[str] | None = None) -> tuple[Backend, list[str]]:
    """Pick a backend. ``auto`` = Java when java + jar + compiled helper are OK, else Python with a warning.

    Returns ``(backend, warnings)``. An explicit ``java`` that is unusable raises :class:`BackendError`.
    """
    if name not in BACKENDS:
        raise ValueError(f"unknown backend {name!r} (choose from {', '.join(BACKENDS)})")
    if name == "python":
        return PythonBackend(), []
    java = _java(str(jar) if jar else None)
    if name == "java":
        ok, reason = java.available()
        if not ok:
            raise BackendError(f"Java backend unavailable: {reason}")
        return java, []
    if find_java() is None or find_jar(jar) is None:
        why = "java not found" if find_java() is None else "Logisim jar not found"
        return PythonBackend(), [f"Java backend unavailable ({why}); using the Python backend"]
    ok, reason = java.available()
    if not ok:
        return PythonBackend(), [f"Java backend unavailable ({reason}); using the Python backend"]
    return java, []


def load_project(path: str | os.PathLike[str], backend: str = "auto",
                 jar: str | os.PathLike[str] | None = None) -> ProjectNetlist:
    """Parse a `.circ` file with the selected backend; selection warnings land in ``project.notes``."""
    chosen, warnings = select_backend(backend, jar)
    project = chosen.load(str(path))
    project.notes.extend(warnings)
    return project


def truth_table(project: ProjectNetlist, circuit: str | None = None, *, backend: str | None = None,
                max_bits: int = DEFAULT_MAX_BITS, tie_duplicate_labels: bool = False,
                jar: str | os.PathLike[str] | None = None) -> TruthTableDict:
    """Exhaustive truth table of ``circuit`` (default: main).

    Uses the backend the project was loaded with unless ``backend`` is given. With
    ``tie_duplicate_labels`` input pins sharing a raw label are merged (see :func:`tie_duplicate_inputs`).
    """
    chosen, warnings = select_backend(backend or project.backend, jar)
    table = chosen.truth_table(project, circuit, max_bits)
    table["notes"] = warnings + list(table.get("notes", []))
    return tie_duplicate_inputs(table) if tie_duplicate_labels else table


def trace(project: ProjectNetlist, steps: list[str], circuit: str | None = None, *, backend: str | None = None,
          jar: str | os.PathLike[str] | None = None) -> dict[str, object]:
    """Sequential simulation script (``"t"`` = clock tick, else comma-separated input bit strings)."""
    chosen, _ = select_backend(backend or project.backend, jar)
    return chosen.trace(project, steps, circuit)
