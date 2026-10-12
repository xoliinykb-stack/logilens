"""Find the Logisim jar and a Java runtime (lookup order in docs/USAGE.md).

Jar order: explicit argument, ``$LOGISIM_JAR``, config file (``logisim_jar = "..."`` in
``<user_config_dir>/logilens/config.toml``), ``$LOGILENS_HOME/logisim.jar``,
``/Applications/Logisim.app/Contents/Resources/Java/logisim.jar``, ``<user_cache_dir>/logilens/logisim.jar``.
"""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP = "logilens"
MAC_APP_JAR = Path("/Applications/Logisim.app/Contents/Resources/Java/logisim.jar")


@dataclass(frozen=True)
class JarCandidate:
    source: str  # "argument" | "env" | "config" | "home" | "app" | "cache"
    path: Path

    @property
    def exists(self) -> bool:
        return self.path.is_file()


def config_path() -> Path:
    return Path(platformdirs.user_config_dir(APP)) / "config.toml"


def cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir(APP))


def _config_jar() -> Path | None:
    path = config_path()
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    value = data.get("logisim_jar")
    return Path(value).expanduser() if isinstance(value, str) and value else None


def jar_candidates(explicit: str | os.PathLike[str] | None = None) -> list[JarCandidate]:
    """All candidate locations in lookup order (existing or not; useful for `doctor`)."""
    out: list[JarCandidate] = []
    if explicit:
        out.append(JarCandidate("argument", Path(explicit).expanduser()))
    if os.environ.get("LOGISIM_JAR"):
        out.append(JarCandidate("env", Path(os.environ["LOGISIM_JAR"]).expanduser()))
    cfg = _config_jar()
    if cfg is not None:
        out.append(JarCandidate("config", cfg))
    if os.environ.get("LOGILENS_HOME"):
        out.append(JarCandidate("home", Path(os.environ["LOGILENS_HOME"]).expanduser() / "logisim.jar"))
    out.append(JarCandidate("app", MAC_APP_JAR))
    out.append(JarCandidate("cache", cache_dir() / "logisim.jar"))
    return out


def find_jar(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """First existing jar. An explicit path that does not exist is NOT skipped silently: returns None."""
    for cand in jar_candidates(explicit):
        if cand.source == "argument" and not cand.exists:
            return None
        if cand.exists:
            return cand.path
    return None


# Homebrew's openjdk is keg-only: it is not linked into PATH, and macOS's /usr/bin/java stub does not see it.
BREW_JDK_BINS = (
    Path("/opt/homebrew/opt/openjdk/bin"),  # macOS, Apple silicon
    Path("/usr/local/opt/openjdk/bin"),  # macOS, Intel
    Path("/home/linuxbrew/.linuxbrew/opt/openjdk/bin"),  # Linux
)
# On macOS /usr/bin/java and /usr/bin/javac exist even without a JDK; they only print an install prompt.
MACOS_STUB_DIR = Path("/usr/bin")


def _executable(path: Path) -> str | None:
    return str(path) if path.is_file() and os.access(path, os.X_OK) else None


def _find_tool(tool: str) -> str | None:
    """``$JAVA_HOME/bin``, then ``PATH``, then Homebrew's keg-only openjdk.

    On macOS the ``/usr/bin`` stub found on ``PATH`` is used only when no Homebrew JDK exists.
    """
    home = os.environ.get("JAVA_HOME")
    if home and (exe := _executable(Path(home) / "bin" / tool)):
        return exe
    on_path = shutil.which(tool)
    is_stub = sys.platform == "darwin" and on_path is not None and Path(on_path).parent == MACOS_STUB_DIR
    if on_path and not is_stub:
        return on_path
    for bin_dir in BREW_JDK_BINS:
        if exe := _executable(bin_dir / tool):
            return exe
    return on_path


def find_java() -> str | None:
    """``java`` from ``$JAVA_HOME``, ``PATH`` or Homebrew's openjdk."""
    return _find_tool("java")


def find_javac() -> str | None:
    """``javac`` from ``$JAVA_HOME``, ``PATH`` or Homebrew's openjdk."""
    return _find_tool("javac")
