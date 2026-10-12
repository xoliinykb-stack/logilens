"""Fixtures for the sequential-analysis tests: generated fixture files and small circuits built on the fly."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

GEN = Path(__file__).resolve().parents[1] / "fixtures" / "gen"


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_seq_fixture_generator", GEN / "generate.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def gen() -> ModuleType:
    return _generator()


def _write(gen: ModuleType, tmp: Path, name: str, circ: object) -> Path:
    path = tmp / f"{name}.circ"
    path.write_text(gen.project_xml([circ]), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def mealy_circ(gen: ModuleType, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """D flip-flop q <- x, Mealy output y = x AND q (detects two 1s in a row)."""
    c = gen.Circ("main")
    x = gen.in_pin(c, 100, 100, "x")
    clk = c.add("#Wiring", "Clock", 100, 300, label="clk")
    ff = c.add("#Memory", "D Flip-Flop", 400, 100)
    g = c.add("#Gates", "AND Gate", 600, 300, inputs=2)
    y = gen.out_pin(c, 900, 100, "y")
    c.tunnel(x, "pin", "x")
    c.tunnel(clk, "out", "clk")
    c.tunnel(ff, "d", "x")
    c.tunnel(ff, "clock", "clk")
    c.tunnel(ff, "q", "q")
    c.tunnel(g, "in0", "x")
    c.tunnel(g, "in1", "q")
    c.tunnel(g, "out", "yv")
    c.tunnel(y, "pin", "yv")
    return _write(gen, tmp_path_factory.mktemp("seq"), "mealy", c)


@pytest.fixture(scope="session")
def t_counter_circ(gen: ModuleType, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Autonomous 2-bit counter from labelled T flip-flops a (MSB, T = b) and b (LSB, T = 1)."""
    c = gen.Circ("main")
    clk = c.add("#Wiring", "Clock", 100, 300, label="clk")
    one = c.add("#Wiring", "Constant", 100, 500)
    fa = c.add("#Memory", "T Flip-Flop", 400, 100, label="a")
    fb = c.add("#Memory", "T Flip-Flop", 400, 300, label="b")
    pa = gen.out_pin(c, 800, 100, "A")
    pb = gen.out_pin(c, 800, 300, "B")
    c.tunnel(clk, "out", "clk")
    c.tunnel(one, "out", "one")
    for ff, t, q in ((fa, "qb", "qa"), (fb, "one", "qb")):
        c.tunnel(ff, "t", t)
        c.tunnel(ff, "clock", "clk")
        c.tunnel(ff, "q", q)
    c.tunnel(pa, "pin", "qa")
    c.tunnel(pb, "pin", "qb")
    return _write(gen, tmp_path_factory.mktemp("seq"), "t_counter", c)


@pytest.fixture(scope="session")
def register_circ(gen: ModuleType, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """2-bit register loading a 2-bit input every clock; output = register contents."""
    c = gen.Circ("main")
    d = gen.in_pin(c, 100, 100, "d", width=2)
    clk = c.add("#Wiring", "Clock", 100, 300, label="clk")
    reg = c.add("#Memory", "Register", 400, 100, width=2, label="r")
    q = gen.out_pin(c, 800, 100, "q", width=2)
    c.tunnel(d, "pin", "D")
    c.tunnel(clk, "out", "clk")
    c.tunnel(reg, "d", "D")
    c.tunnel(reg, "clock", "clk", side="south")
    c.tunnel(reg, "q", "Q")
    c.tunnel(q, "pin", "Q")
    return _write(gen, tmp_path_factory.mktemp("seq"), "register", c)
