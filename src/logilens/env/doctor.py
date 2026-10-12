"""Environment checks (``logilens doctor``) and setup actions (``logilens setup``)."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from logilens.backends.java.build import build_helper, helper_dir, is_built, prebuilt_dir
from logilens.backends.java.locate import find_jar, jar_candidates
from logilens.core.errors import BackendError
from logilens.env import tools
from logilens.env.espresso_build import build_espresso, ensure_espresso, find_espresso, toolchain_available
from logilens.env.paths import cache_dir, is_writable

PLA_PROBE = ".i 2\n.o 1\n11 1\n10 1\n.e\n"


class Status(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    INFO = "info"


@dataclass(frozen=True)
class Check:
    """One doctor line. ``name``/``fix`` are i18n keys (``doctor.check.*`` / ``doctor.fix.*``).

    ``detail`` is plain English (JSON output); ``note`` is an optional i18n key used for display instead, with
    ``extra`` filled into its ``{extra}`` field.
    """

    name: str
    status: Status
    detail: str
    fix: str | None = None
    required: bool = False
    note: str | None = None
    extra: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status.value, "detail": self.detail, "fix": self.fix,
                "required": self.required}


def check_python() -> Check:
    ok = sys.version_info >= (3, 11)
    return Check("python", Status.OK if ok else Status.FAIL, f"{platform.python_version()} ({sys.executable})",
                 None if ok else "doctor.fix.python", required=True)


def check_java() -> list[Check]:
    java, javac = tools.java(), tools.javac()
    return [
        Check("java", Status.OK if java.found else Status.WARN,
              f"{java.version} ({java.path})" if java.found else "not found", None if java.found else "doctor.fix.java",
              note=None if java.found else "doctor.note.not_found"),
        Check("javac", Status.OK if javac.found else Status.WARN,
              f"{javac.version} ({javac.path})" if javac.found else "not found",
              None if javac.found else "doctor.fix.javac", note=None if javac.found else "doctor.note.not_found"),
    ]


def check_jar(explicit: str | None) -> tuple[Check, Path | None]:
    jar = find_jar(explicit)
    if jar is None:
        tried = ", ".join(str(c.path) for c in jar_candidates(explicit))
        return Check("jar", Status.WARN, f"not found (tried: {tried})", "doctor.fix.jar",
                     note="doctor.note.jar_missing", extra=tried), None
    version = tools.logisim_version(jar)
    status = Status.OK if version.startswith("2.7") else (Status.WARN if version else Status.INFO)
    detail = f"{jar} (Logisim {version or 'version unknown'})"
    return Check("jar", status, detail, None if status is Status.OK else "doctor.fix.jar_version"), jar


def check_helper(jar: Path | None, fix: bool) -> Check:
    if jar is None:
        return Check("helper", Status.WARN, "needs the Logisim jar", "doctor.fix.jar", note="doctor.note.needs_jar")
    if fix and not is_built(jar):
        try:
            build_helper(jar)
        except BackendError as exc:
            return Check("helper", Status.FAIL, f"build failed: {exc}", "doctor.fix.javac",
                         note="doctor.note.build_failed", extra=str(exc))
    if is_built(jar):
        return Check("helper", Status.OK, str(prebuilt_dir(jar) or helper_dir(jar)))
    return Check("helper", Status.WARN, "not built yet (compiled automatically on first use)", "doctor.fix.setup",
                 note="doctor.note.helper_later")


def check_espresso(fix: bool) -> Check:
    from logilens.minimize.espresso import EspressoError, run_espresso

    binary = ensure_espresso(build=fix)
    if binary is None:
        hint = "doctor.fix.setup" if toolchain_available() else "doctor.fix.cc"
        return Check("espresso", Status.WARN, "not built (Espresso columns will be empty)", hint,
                     note="doctor.note.espresso_missing")
    try:
        out = run_espresso(PLA_PROBE, "default", binary, timeout=20)
    except (EspressoError, OSError) as exc:
        return Check("espresso", Status.FAIL, f"{binary}: run failed ({exc})", "doctor.fix.setup")
    ok = ".e" in out or ".p" in out
    return Check("espresso", Status.OK if ok else Status.FAIL, str(binary), None if ok else "doctor.fix.setup")


def check_graphviz() -> Check:
    info = tools.graphviz()
    if info.found:
        return Check(info.name, Status.OK, f"{info.version} ({info.path})")
    return Check(info.name, Status.INFO, "not installed (optional)", "doctor.fix.graphviz",
                 note="doctor.note.not_installed")


def check_cache() -> Check:
    ok, why = is_writable(cache_dir())
    return Check("cache", Status.OK if ok else Status.FAIL, str(cache_dir()) + ("" if ok else f": {why}"),
                 None if ok else "doctor.fix.cache", required=True)


def run_checks(jar: str | None = None, fix: bool = False) -> list[Check]:
    """All checks in display order (``fix`` builds the helper and Espresso when possible)."""
    checks = [check_python(), *check_java()]
    jar_check, jar_path = check_jar(jar)
    checks += [jar_check, check_helper(jar_path, fix), check_espresso(fix), check_graphviz(), check_cache()]
    return checks


def healthy(checks: list[Check]) -> bool:
    """False when a check failed (required checks or broken builds)."""
    return not any(c.status is Status.FAIL for c in checks)


@dataclass(frozen=True)
class SetupStep:
    name: str
    ok: bool
    detail: str
    note: str | None = None  # i18n key shown instead of ``detail``


def setup(jar: str | None = None, force: bool = False) -> list[SetupStep]:
    """Build the Java helper (when a jar and javac exist) and Espresso."""
    steps = []
    jar_path = find_jar(jar)
    if jar_path is None:
        steps.append(SetupStep("helper", False, "Logisim jar not found; the Python backend will be used",
                               note="setup.no_jar"))
    else:
        try:
            steps.append(SetupStep("helper", True, str(build_helper(jar_path, force=force))))
        except BackendError as exc:
            steps.append(SetupStep("helper", False, f"{exc} {exc.stderr[:400]}".strip()))
    binary = None if force else find_espresso()
    log = ""
    if binary is None:
        result = build_espresso(force=force)
        binary, log = result.binary, result.log.strip()
    if binary is not None:
        steps.append(SetupStep("espresso", True, str(binary)))
    else:
        steps.append(SetupStep("espresso", False, log.splitlines()[-1] if log else "build failed"))
    return steps


__all__ = ["Check", "SetupStep", "Status", "healthy", "run_checks", "setup"]
