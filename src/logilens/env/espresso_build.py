"""Locate or build the vendored Berkeley Espresso binary (third_party/espresso) into the user cache.

The repository is never written to: sources are copied into
``<user cache>/logilens/espresso/espresso-src`` and ``make`` puts the binary into
``.../espresso/bin/espresso`` (the vendored Makefile uses ``TARGETDIR := ../bin``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from logilens.env.paths import espresso_cache

BINARY_ENV = "LOGILENS_ESPRESSO"
SOURCE_ENV = "LOGILENS_ESPRESSO_SRC"


@dataclass(frozen=True)
class BuildResult:
    """Outcome of a build attempt."""

    ok: bool
    binary: Path | None
    log: str


def source_dir() -> Path | None:
    """Vendored espresso sources.

    Order: ``$LOGILENS_ESPRESSO_SRC``; the copy packaged inside the wheel
    (``logilens/_vendor/espresso-src``); ``<repo>/third_party/espresso/espresso-src`` in a checkout.
    """
    env = os.environ.get(SOURCE_ENV)
    candidates = [Path(env)] if env else []
    candidates.append(Path(__file__).resolve().parents[1] / "_vendor" / "espresso-src")
    candidates.append(Path(__file__).resolve().parents[3] / "third_party" / "espresso" / "espresso-src")
    for path in candidates:
        if (path / "Makefile").is_file():
            return path
    return None


def cache_dir() -> Path:
    """Directory holding the build tree and the binary."""
    return espresso_cache()


def cached_binary() -> Path:
    """Where a successful build places the binary."""
    return cache_dir() / "bin" / "espresso"


def toolchain_available() -> bool:
    """True if ``make`` and a C compiler are on PATH."""
    has_cc = any(shutil.which(cc) for cc in ("cc", "gcc", "clang"))
    return bool(shutil.which("make")) and has_cc


def find_espresso() -> Path | None:
    """Existing binary: ``$LOGILENS_ESPRESSO``, the cached build, then ``espresso`` on PATH."""
    env = os.environ.get(BINARY_ENV)
    if env and os.access(env, os.X_OK):
        return Path(env)
    cached = cached_binary()
    if cached.is_file() and os.access(cached, os.X_OK):
        return cached
    found = shutil.which("espresso")
    return Path(found) if found else None


def build_espresso(force: bool = False, timeout: float = 300.0) -> BuildResult:
    """Copy the sources into the cache and run ``make``. Returns the binary path on success."""
    src = source_dir()
    if src is None:
        return BuildResult(False, None, "espresso sources not found (third_party/espresso/espresso-src)")
    if not toolchain_available():
        return BuildResult(False, None, "make and a C compiler (cc) are required to build espresso")
    work = cache_dir() / "espresso-src"
    # Start from a clean copy so stale object files never survive; keep the rest of the cache alone.
    shutil.rmtree(work, ignore_errors=True)
    if force:
        shutil.rmtree(cached_binary().parent, ignore_errors=True)
    work.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(src, work)
    except OSError as exc:
        return BuildResult(False, None, f"cannot copy espresso sources to {work}: {exc}")
    jobs = f"-j{os.cpu_count() or 1}"
    try:
        proc = subprocess.run(["make", jobs], cwd=work, capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return BuildResult(False, None, f"make failed: {exc}")
    log = proc.stdout + proc.stderr
    binary = cached_binary()
    ok = proc.returncode == 0 and binary.is_file()
    return BuildResult(ok, binary if ok else None, log)


def ensure_espresso(build: bool = True) -> Path | None:
    """Existing binary, or build one when ``build`` is True and a toolchain is available."""
    found = find_espresso()
    if found or not build:
        return found
    return build_espresso().binary
