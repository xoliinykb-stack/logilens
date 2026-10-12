"""Berkeley Espresso runner: PLA writer/parser and NAND/NOR re-costing.

POS is obtained by running espresso on the complemented outputs (cubes of the OFF-set). PLAs use
``.type fd`` with '-' for don't-care outputs. ``-Dso_both`` produces mixed-phase covers and is unsupported.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from logilens.core.logic_types import CostModel, Cube, Form, MinimizationResult, MultiFunction
from logilens.env.espresso_build import ensure_espresso
from logilens.logic.cube import cube_from_str
from logilens.logic.truth_table import minterm_bits
from logilens.minimize.base import Problem, finish, make_cover, make_problem

MODES: dict[str, list[str]] = {
    "default": [],
    "exact": ["-Dexact"],
    "signature": ["-Dsignature"],
    "qm": ["-Dqm"],
    "so": ["-Dso"],
    "efast": ["-efast"],
}
UNSUPPORTED = {"so_both": "-Dso_both returns mixed-phase covers, which the two-level cost model does not support"}


class EspressoError(RuntimeError):
    """Espresso could not be run or its output could not be parsed."""


def write_pla(problem: Problem) -> str:
    """PLA (``.type fd``) of the problem's target functions: '1' target ON, '-' DC, '0' otherwise."""
    lines = [f".i {problem.n}", f".o {len(problem.outputs)}", ".type fd",
             ".ilb " + " ".join(problem.inputs), ".ob " + " ".join(problem.outputs)]
    for m in range(1 << problem.n):
        chars = []
        for name in problem.outputs:
            t = problem.targets[name]
            chars.append("1" if t.on >> m & 1 else "-" if t.dc >> m & 1 else "0")
        lines.append(f"{minterm_bits(m, problem.n)} {''.join(chars)}")
    lines.append(".e")
    return "\n".join(lines) + "\n"


def parse_pla(text: str, n: int, outputs: tuple[str, ...]) -> dict[str, list[Cube]]:
    """Cubes per output from espresso's output PLA (output char '1' = cube used by that output)."""
    terms: dict[str, list[Cube]] = {o: [] for o in outputs}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((".", "#")):
            continue
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != n or len(parts[1]) != len(outputs):
            raise EspressoError(f"unexpected espresso output line: {line!r}")
        cube = cube_from_str(parts[0])
        for k, ch in enumerate(parts[1]):
            if ch == "1":
                terms[outputs[k]].append(cube)
            elif ch not in "0-~":
                raise EspressoError(f"unexpected output character {ch!r} in {line!r}")
    return terms


def run_espresso(pla: str, mode: str, binary: Path, timeout: float = 60.0) -> str:
    """Run espresso on PLA text and return stdout."""
    try:
        proc = subprocess.run([str(binary), *MODES[mode]], input=pla, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EspressoError(f"espresso failed: {exc}") from exc
    if proc.returncode != 0:
        raise EspressoError(f"espresso exited with {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


def espresso_minimize(
    mf: MultiFunction,
    form: Form,
    mode: str = "default",
    binary: Path | None = None,
    model: CostModel | None = None,
    build: bool = True,
) -> MinimizationResult:
    """Espresso cover re-costed with the NAND/NOR cost model. Cover is None (with a note) if unavailable."""
    started = time.perf_counter()
    problem = make_problem(mf, form)
    method = f"espresso:{mode}"
    if mode in UNSUPPORTED or mode not in MODES:
        reason = UNSUPPORTED.get(mode, f"unknown espresso mode {mode!r}")
        return finish(method, problem, None, multi_output=True, model=model, started=started,
                      notes=[f"unsupported: {reason}"])
    binary = binary or ensure_espresso(build=build)
    if binary is None:
        return finish(method, problem, None, multi_output=True, model=model, started=started,
                      notes=["unsupported: espresso binary not available (run `logilens setup`)"])
    try:
        terms = parse_pla(run_espresso(write_pla(problem), mode, binary), problem.n, problem.outputs)
    except EspressoError as exc:
        return finish(method, problem, None, multi_output=True, model=model, started=started, notes=[str(exc)])
    notes = ["heuristic/cube-count minimization; cost optimality not proven"]
    return finish(method, problem, make_cover(problem, terms), multi_output=mode != "so", model=model,
                  started=started, notes=notes)
