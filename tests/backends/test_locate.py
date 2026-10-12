"""Java lookup: $JAVA_HOME, PATH, then Homebrew's keg-only openjdk."""

from __future__ import annotations

from pathlib import Path

import pytest

from logilens.backends.java import locate


def _fake_jdk(root: Path) -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    for tool in ("java", "javac"):
        exe = bin_dir / tool
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
    return bin_dir


def test_java_home_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bin_dir = _fake_jdk(tmp_path / "jdk")
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "jdk"))
    monkeypatch.setattr(locate.shutil, "which", lambda tool: "/opt/other/bin/" + tool)
    assert locate.find_java() == str(bin_dir / "java")
    assert locate.find_javac() == str(bin_dir / "javac")


def test_homebrew_openjdk_beats_the_macos_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    brew_bin = _fake_jdk(tmp_path / "openjdk")
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr(locate.sys, "platform", "darwin")
    monkeypatch.setattr(locate.shutil, "which", lambda tool: "/usr/bin/" + tool)
    monkeypatch.setattr(locate, "BREW_JDK_BINS", (tmp_path / "missing", brew_bin))
    assert locate.find_java() == str(brew_bin / "java")


def test_path_java_is_used_when_it_is_not_the_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    brew_bin = _fake_jdk(tmp_path / "openjdk")
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr(locate.shutil, "which", lambda tool: "/usr/lib/jvm/bin/" + tool)
    monkeypatch.setattr(locate, "BREW_JDK_BINS", (brew_bin,))
    assert locate.find_java() == "/usr/lib/jvm/bin/java"


def test_stub_is_the_last_resort(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr(locate.sys, "platform", "darwin")
    monkeypatch.setattr(locate.shutil, "which", lambda tool: "/usr/bin/" + tool)
    monkeypatch.setattr(locate, "BREW_JDK_BINS", (tmp_path / "missing",))
    assert locate.find_java() == "/usr/bin/java"


def test_nothing_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr(locate.shutil, "which", lambda tool: None)
    monkeypatch.setattr(locate, "BREW_JDK_BINS", (tmp_path / "missing",))
    assert locate.find_java() is None
