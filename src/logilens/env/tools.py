"""External tools: locate executables and read their versions (short timeouts, never raise)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from logilens.backends.java.locate import find_java, find_javac


@dataclass(frozen=True)
class ToolInfo:
    """An executable and its version string ('' when unknown)."""

    name: str
    path: str | None
    version: str = ""

    @property
    def found(self) -> bool:
        return self.path is not None


def run_quiet(cmd: list[str], timeout: float = 20.0) -> tuple[int, str]:
    """``(exit code, stdout + stderr)``; ``(-1, reason)`` when the command cannot run."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                              check=False)
    except subprocess.TimeoutExpired:
        return -1, f"timed out after {timeout:g} s"
    except OSError as exc:
        return -1, exc.strerror or str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _first_match(text: str, pattern: str) -> str:
    m = re.search(pattern, text)
    return m.group(1) if m else (text.strip().splitlines() or [""])[0][:80]


def java() -> ToolInfo:
    path = find_java()
    if path is None:
        return ToolInfo("java", None)
    _, out = run_quiet([path, "-version"])
    return ToolInfo("java", path, _first_match(out, r'version "([^"]+)"'))


def javac() -> ToolInfo:
    path = find_javac()
    if path is None:
        return ToolInfo("javac", None)
    _, out = run_quiet([path, "-version"])
    return ToolInfo("javac", path, _first_match(out, r"javac\s+(\S+)"))


def logisim_version(jar: Path) -> str:
    """Version printed by ``java -jar logisim.jar -version`` ('' when it cannot be determined)."""
    path = find_java()
    if path is None:
        return ""
    code, out = run_quiet([path, "-Djava.awt.headless=true", "-jar", str(jar), "-version"])
    if code != 0:
        return ""
    m = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", out)
    return m.group(1) if m else ""


def simple_tool(name: str, args: tuple[str, ...] = ("--version",), pattern: str = r"(\d+\.\d+(?:\.\d+)?)") -> ToolInfo:
    path = shutil.which(name)
    if path is None:
        return ToolInfo(name, None)
    _, out = run_quiet([path, *args])
    return ToolInfo(name, path, _first_match(out, pattern))


def graphviz() -> ToolInfo:
    return simple_tool("dot", ("-V",))


__all__ = ["ToolInfo", "graphviz", "java", "javac", "logisim_version", "run_quiet", "simple_tool"]
