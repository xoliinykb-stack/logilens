"""Backend A: the real Logisim 2.7.1 engine through ``LogisimBridge`` (one JVM per call).

Loading = Python XML parse (raw wires are kept for structural lint) + Logisim ``dump``; every component's
ports are replaced by Logisim's own ``getEnds()``, so port geometry is authoritative. Truth tables and traces
come from Logisim's simulator.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from logilens.backends.base import DEFAULT_MAX_BITS, TraceDict, TruthTableDict, pin_header
from logilens.backends.java.build import HELPER, build_helper
from logilens.backends.java.locate import find_jar, find_java
from logilens.core.errors import BackendError
from logilens.core.geometry import Point
from logilens.core.netlist import Component, Port, ProjectNetlist
from logilens.parse.circ_xml import read_circ
from logilens.parse.hierarchy import parse_project

DEFAULT_TIMEOUT = 300.0


class JavaBridge:
    """Thin subprocess wrapper around the compiled helper."""

    def __init__(self, jar: str | os.PathLike[str] | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.jar_arg = jar
        self.timeout = timeout
        self._jar: Path | None = None
        self._classes: Path | None = None

    def jar(self) -> Path:
        if self._jar is None:
            found = find_jar(self.jar_arg)
            if found is None:
                raise BackendError("Logisim jar not found (use --logisim-jar or $LOGISIM_JAR)")
            self._jar = found
        return self._jar

    def classes(self) -> Path:
        if self._classes is None:
            self._classes = build_helper(self.jar())
        return self._classes

    def run(self, command: str, *args: str) -> dict[str, Any]:
        """Run ``LogisimBridge <command> args...`` and return its JSON (errors -> :class:`BackendError`)."""
        java = find_java()
        if java is None:
            raise BackendError("java not found (install a JRE/JDK, e.g. `brew install openjdk`)")
        cp = os.pathsep.join([str(self.jar()), str(self.classes())])
        cmd = [java, "-Djava.awt.headless=true", "-cp", cp, HELPER, command, *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"Logisim helper timed out after {self.timeout:.0f}s ({command})") from exc
        except OSError as exc:
            raise BackendError(f"cannot start java: {exc}") from exc
        data = _last_json(proc.stdout)
        if data is None:
            raise BackendError(f"Logisim helper produced no JSON (exit {proc.returncode})", proc.stderr)
        if "error" in data:
            raise BackendError(f"Logisim helper: {data['error']}", proc.stderr)
        if proc.returncode != 0:
            raise BackendError(f"Logisim helper exited with {proc.returncode}", proc.stderr)
        return data

    def dump(self, path: str) -> dict[str, Any]:
        return self.run("dump", str(path))

    def table(self, path: str, circuit: str | None = None, max_bits: int = DEFAULT_MAX_BITS) -> dict[str, Any]:
        return self.run("table", str(path), circuit or "-", str(max_bits))

    def trace(self, path: str, steps: list[str], circuit: str | None = None) -> dict[str, Any]:
        return self.run("trace", str(path), circuit or "-", ";".join(steps))

    def render(self, path: str, png: str, scale: float = 2.0, circuit: str | None = None) -> dict[str, Any]:
        return self.run("render", str(path), str(png), str(scale), circuit or "-")


def _last_json(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    return None


def java_ports(entry: dict[str, Any], template: list[Port]) -> list[Port]:
    """Ports from a dump entry; names come from the Python spec when the port count agrees."""
    ends = entry["ends"]
    same = len(ends) == len(template)
    out = []
    for e in ends:
        name = template[e["i"]].name if same else f"p{e['i']}"
        direction = template[e["i"]].direction if same else e["type"]
        out.append(Port(e["i"], name, direction, e["width"] or None, Point(e["x"], e["y"])))
    return out


def index_dump(dump: dict[str, Any]) -> dict[str, dict[tuple[str, Point], list[dict[str, Any]]]]:
    """circuit -> (component name, loc) -> dump entries."""
    out: dict[str, dict[tuple[str, Point], list[dict[str, Any]]]] = {}
    for circ in dump["circuits"]:
        idx: dict[tuple[str, Point], list[dict[str, Any]]] = {}
        for entry in circ["components"]:
            idx.setdefault((entry["name"], Point(*entry["loc"])), []).append(entry)
        out[circ["name"]] = idx
    return out


class JavaBackend:
    """Logisim engine backend."""

    name = "java"

    def __init__(self, jar: str | os.PathLike[str] | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.bridge = JavaBridge(jar, timeout)

    def available(self) -> tuple[bool, str]:
        if find_java() is None:
            return False, "java not found"
        try:
            self.bridge.classes()
        except BackendError as exc:
            return False, str(exc)
        return True, ""

    def load(self, path: str) -> ProjectNetlist:
        read_circ(path)  # rejects DTDs before Logisim's XML parser sees the file
        index = index_dump(self.bridge.dump(path))
        missing: list[str] = []

        def override(circuit: str, comp: Component) -> list[Port] | None:
            entries = index.get(circuit, {}).get((comp.name, comp.loc))
            if not entries:
                if comp.kind != "text" and comp.supported:
                    missing.append(f"{circuit}: {comp.describe()}")
                return None
            return java_ports(entries.pop(0), comp.ports)

        project = parse_project(path, port_override=override)
        project.backend = self.name
        if missing:
            project.notes.append("components not reported by Logisim: " + ", ".join(missing))
        return project

    def truth_table(self, project: ProjectNetlist, circuit: str | None = None,
                    max_bits: int = DEFAULT_MAX_BITS) -> TruthTableDict:
        circ = project.circuit(circuit)
        data = self.bridge.table(project.path, circ.name, max_bits)
        ins, outs = pin_header(circ)
        notes: list[str] = []
        java_ins = [c["label"] for c in data["inputs"]]
        java_outs = [c["label"] for c in data["outputs"]]
        if java_ins != [c["name"] for c in ins] or java_outs != [c["name"] for c in outs]:
            notes.append("pin naming differs between Logisim and the Python parser; Logisim's names are used")
            ins = [{"name": c["label"], "label": c["label"], "width": c["width"]} for c in data["inputs"]]
            outs = [{"name": c["label"], "label": c["label"], "width": c["width"]} for c in data["outputs"]]
        rows = [{"in": r["in"].split(" ") if r["in"] else [], "out": list(r["out"]), "osc": bool(r["osc"])}
                for r in data["rows"]]
        return {"circuit": circ.name, "backend": self.name, "inputs": ins, "outputs": outs, "rows": rows,
                "notes": notes}

    def trace(self, project: ProjectNetlist, steps: list[str], circuit: str | None = None) -> TraceDict:
        circ = project.circuit(circuit)
        data = self.bridge.trace(project.path, steps, circ.name)
        ins, outs = pin_header(circ)
        return {"circuit": circ.name, "backend": self.name, "inputs": ins, "outputs": outs,
                "rows": [{"op": r["op"], "out": list(r["out"]), "osc": bool(r["osc"])} for r in data["rows"]]}
