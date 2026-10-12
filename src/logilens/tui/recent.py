"""Recently opened circuits (``<user config dir>/logilens/recent.json``, at most 15 entries).

The file is a JSON list of ``{"path", "spec", "opened"}`` objects, newest first. A corrupt or unreadable file is
treated as empty; write errors are ignored (the list is a convenience, never a reason to fail).
``$LOGILENS_RECENT`` overrides the location (used by tests and portable setups).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from logilens.env.paths import config_dir

MAX_RECENT = 15
ENV_VAR = "LOGILENS_RECENT"


def default_path() -> Path:
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return config_dir() / "recent.json"


@dataclass(frozen=True)
class RecentEntry:
    path: str
    spec: str | None = None
    opened: str = ""

    @property
    def exists(self) -> bool:
        return Path(self.path).is_file()


def _norm(path: str | os.PathLike[str]) -> str:
    return str(Path(path).expanduser().resolve())


class RecentFiles:
    """Load / update the recent-files list."""

    def __init__(self, path: str | os.PathLike[str] | None = None, limit: int = MAX_RECENT) -> None:
        self.path = Path(path) if path is not None else default_path()
        self.limit = limit

    def load(self) -> list[RecentEntry]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        out: list[RecentEntry] = []
        seen: set[str] = set()
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            if item["path"] in seen:
                continue
            seen.add(item["path"])
            spec = item.get("spec") if isinstance(item.get("spec"), str) else None
            out.append(RecentEntry(item["path"], spec, str(item.get("opened", ""))))
        return out[: self.limit]

    def add(self, path: str | os.PathLike[str], spec: str | os.PathLike[str] | None = None) -> list[RecentEntry]:
        """Put ``path`` first (with its spec), keep at most ``limit`` entries, save; returns the new list."""
        key = _norm(path)
        opened = datetime.now(UTC).astimezone().replace(microsecond=0).isoformat()
        entry = RecentEntry(key, _norm(spec) if spec else None, opened)
        entries = [entry] + [e for e in self.load() if e.path != key]
        entries = entries[: self.limit]
        self.save(entries)
        return entries

    def save(self, entries: list[RecentEntry]) -> None:
        tmp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".recent-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump([asdict(e) for e in entries], fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            if tmp is not None:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)


__all__ = ["ENV_VAR", "MAX_RECENT", "RecentEntry", "RecentFiles", "default_path"]
