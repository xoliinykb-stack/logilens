"""The install-time (Homebrew) helper is used only for the exact jar it was compiled against."""

from __future__ import annotations

from pathlib import Path

from logilens.backends.java import build


def _make_prebuilt(tmp_path: Path, jar: Path) -> Path:
    d = tmp_path / "helper"
    d.mkdir()
    (d / f"{build.HELPER}.class").write_bytes(b"\xca\xfe\xba\xbe")
    (d / build.BUILT_FOR).write_text(f"{jar.resolve()}\n")
    return d


def test_prebuilt_used_for_matching_jar(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "logisim.jar"
    jar.write_bytes(b"jar")
    d = _make_prebuilt(tmp_path, jar)
    monkeypatch.setenv(build.PREBUILT_ENV, str(d))
    assert build.prebuilt_dir(jar) == d
    assert build.is_built(jar)
    assert build.build_helper(jar) == d


def test_prebuilt_ignored_for_other_jar_or_missing_marker(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "logisim.jar"
    jar.write_bytes(b"jar")
    other = tmp_path / "other.jar"
    other.write_bytes(b"other")
    d = _make_prebuilt(tmp_path, jar)
    monkeypatch.setenv(build.PREBUILT_ENV, str(d))
    assert build.prebuilt_dir(other) is None
    (d / build.BUILT_FOR).unlink()
    assert build.prebuilt_dir(jar) is None


def test_no_env_means_no_prebuilt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(build.PREBUILT_ENV, raising=False)
    jar = tmp_path / "logisim.jar"
    jar.write_bytes(b"jar")
    assert build.prebuilt_dir(jar) is None
