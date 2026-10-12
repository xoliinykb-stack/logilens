"""Backend B: pure-Python parser + simulator (no Java needed)."""

from __future__ import annotations

from logilens.backends.base import DEFAULT_MAX_BITS, TraceDict, TruthTableDict, pin_header
from logilens.core.errors import UnsupportedError
from logilens.core.netlist import ProjectNetlist
from logilens.parse.hierarchy import flatten, parse_project
from logilens.sim.combinational import Simulator, evaluate_row
from logilens.sim.models import SimContext
from logilens.sim.sequential import run_trace


class PythonBackend:
    """Own geometric parser and simulator (Logisim 2.7.1 semantics, cross-validated against Java)."""

    name = "python"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def load(self, path: str) -> ProjectNetlist:
        project = parse_project(path)
        project.backend = self.name
        return project

    def _simulator(self, project: ProjectNetlist, circuit: str | None) -> tuple[Simulator, list[str]]:
        flat = flatten(project, circuit)
        sim = Simulator(flat, SimContext(project.gate_undefined_error),
                        int(project.options.get("simlimit", "1000") or 1000))
        notes = [f"not simulated: {u.name} at {u.loc} in {u.circuit} — outputs treated as floating"
                 for u in sim.unsupported]
        return sim, notes

    def truth_table(self, project: ProjectNetlist, circuit: str | None = None,
                    max_bits: int = DEFAULT_MAX_BITS) -> TruthTableDict:
        circ = project.circuit(circuit)
        ins, outs = pin_header(circ)
        widths = [c["width"] for c in ins]
        if sum(widths) > max_bits:
            raise UnsupportedError("truth table", circ.name, f"too many input bits: {sum(widths)} > {max_bits}")
        sim, notes = self._simulator(project, circuit)
        rows = []
        for r in range(1 << sum(widths)):
            in_bits, out_bits, osc = evaluate_row(sim, r, widths)
            rows.append({"in": in_bits, "out": out_bits, "osc": osc})
        return {"circuit": circ.name, "backend": self.name, "inputs": ins, "outputs": outs, "rows": rows,
                "notes": notes}

    def trace(self, project: ProjectNetlist, steps: list[str], circuit: str | None = None) -> TraceDict:
        circ = project.circuit(circuit)
        ins, outs = pin_header(circ)
        flat = flatten(project, circuit)
        rows = run_trace(flat, steps, SimContext(project.gate_undefined_error))
        return {"circuit": circ.name, "backend": self.name, "inputs": ins, "outputs": outs,
                "rows": [{"op": r.op, "out": r.outputs, "state": r.state} for r in rows]}
