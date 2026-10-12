"""Compile ``LogisimBridge.java`` against the user's jar into the cache (once per source+jar)."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from importlib import resources
from pathlib import Path

from logilens.backends.java.locate import cache_dir, find_javac
from logilens.core.errors import BackendError

HELPER = "LogisimBridge"


def helper_source() -> Path:
    """The helper source: packaged copy (wheel) or ``java/LogisimBridge.java`` in a source checkout."""
    try:
        packaged = resources.files("logilens.backends.java").joinpath(f"{HELPER}.java")
        if packaged.is_file():
            return Path(str(packaged))
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    repo = Path(__file__).resolve().parents[4] / "java" / f"{HELPER}.java"
    if repo.is_file():
        return repo
    raise BackendError(f"{HELPER}.java not found (neither packaged nor in the source tree)")


def helper_key(source: Path, jar: Path) -> str:
    """Hash of helper source bytes + jar identity (path, size, mtime)."""
    h = hashlib.sha256(source.read_bytes())
    st = jar.stat()
    h.update(f"{jar.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode())
    return h.hexdigest()[:16]


PREBUILT_ENV = "LOGILENS_HELPER_DIR"
BUILT_FOR = "built-for"


def prebuilt_dir(jar: Path) -> Path | None:
    """A helper compiled at install time (Homebrew puts it in ``libexec/helper``).

    Used only if ``$LOGILENS_HELPER_DIR`` holds the class and its ``built-for`` marker names
    exactly this jar, so a different jar chosen by the user still gets its own cached build.
    """
    env = os.environ.get(PREBUILT_ENV)
    if not env:
        return None
    path = Path(env)
    marker = path / BUILT_FOR
    if not (path / f"{HELPER}.class").is_file() or not marker.is_file():
        return None
    if marker.read_text().strip() != str(jar.resolve()):
        return None
    return path


def helper_dir(jar: Path, source: Path | None = None) -> Path:
    src = source or helper_source()
    return cache_dir() / "helper" / helper_key(src, jar)


def is_built(jar: Path) -> bool:
    return prebuilt_dir(jar) is not None or (helper_dir(jar) / f"{HELPER}.class").is_file()


def build_helper(jar: Path, force: bool = False, timeout: float = 120.0) -> Path:
    """Compile the helper if needed; returns the class directory. Raises :class:`BackendError`."""
    if not force and (pre := prebuilt_dir(jar)) is not None:
        return pre
    src = helper_source()
    out = helper_dir(jar, src)
    if not force and (out / f"{HELPER}.class").is_file():
        return out
    javac = find_javac()
    if javac is None:
        raise BackendError("javac not found (install a JDK, e.g. `brew install openjdk`)")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="build-", dir=out.parent))
    try:
        cmd = [javac, "--release", "11", "-nowarn", "-cp", str(jar), "-d", str(tmp), str(src)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            raise BackendError(f"javac failed with exit code {proc.returncode}", proc.stderr)
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        try:
            os.replace(tmp, out)
        except OSError:
            # another process finished the same build first
            if not (out / f"{HELPER}.class").is_file():
                raise
    except subprocess.TimeoutExpired as exc:
        raise BackendError("javac timed out") from exc
    except OSError as exc:
        raise BackendError(f"cannot build the Java helper: {exc}") from exc
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return out
