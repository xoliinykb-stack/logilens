"""Exception hierarchy shared by parser, backends and CLI."""

from __future__ import annotations


class LogilensError(Exception):
    """Base class for all tool errors (the CLI maps these to exit codes)."""


class ParseError(LogilensError):
    """The `.circ` file could not be read or is structurally invalid."""

    def __init__(self, message: str, path: str | None = None) -> None:
        super().__init__(message if path is None else f"{path}: {message}")
        self.path = path


class UnsupportedError(LogilensError):
    """A construct cannot be handled (e.g. simulating an unknown component)."""

    def __init__(self, item: str, location: str | None = None, reason: str = "") -> None:
        text = f"unsupported: {item}"
        if location:
            text += f" at {location}"
        if reason:
            text += f" ({reason})"
        super().__init__(text)
        self.item = item
        self.location = location
        self.reason = reason


class BackendError(LogilensError):
    """A backend (Java helper, Logisim jar, ...) failed or is unavailable."""

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


class SimulationError(LogilensError):
    """The Python simulator could not evaluate the circuit."""


class NotFoundError(LogilensError, KeyError):
    """A name given by the user (circuit, output) does not exist in the file."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return repr(self.name)
