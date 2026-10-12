"""User directories of logilens (cache, config) and cache maintenance."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from logilens.backends.java.locate import cache_dir, config_path

JAR_NAME = "logisim.jar"


def config_dir() -> Path:
    return config_path().parent


def helper_cache() -> Path:
    """Compiled Java helper builds (one directory per helper source + jar hash)."""
    return cache_dir() / "helper"


def espresso_cache() -> Path:
    """Espresso source copy and binary."""
    return cache_dir() / "espresso"


def is_writable(path: Path) -> tuple[bool, str]:
    """Create ``path`` if needed and try to write a temporary file into it."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".probe-"):
            pass
    except OSError as exc:
        return False, str(exc)
    return True, ""


def cache_entries(include_jar: bool = False) -> list[Path]:
    """Top-level cache entries that :func:`clear_cache` would remove."""
    root = cache_dir()
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if include_jar or p.name != JAR_NAME)


def clear_cache(include_jar: bool = False) -> list[Path]:
    """Delete cached builds (helper classes, Espresso); a downloaded ``logisim.jar`` is kept unless asked."""
    removed = []
    for entry in cache_entries(include_jar):
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            try:
                os.remove(entry)
            except OSError:
                continue
        removed.append(entry)
    return removed


__all__ = ["cache_dir", "cache_entries", "clear_cache", "config_dir", "config_path", "espresso_cache",
           "helper_cache", "is_writable"]
