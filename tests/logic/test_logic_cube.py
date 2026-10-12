"""Cube operations and truth-table conventions."""

from __future__ import annotations

from logilens.core.logic_types import Cube
from logilens.logic.cube import (
    consensus,
    contains,
    covers_minterm,
    cube_from_str,
    cube_mask,
    cube_minterms,
    intersects,
    merge_adjacent,
    minterm_cube,
)
from logilens.logic.truth_table import input_value, minterm_bits


def test_minterm_convention_msb_first() -> None:
    assert minterm_bits(5, 5) == "00101"
    assert input_value(0b10000, 5, 0) == 1  # first input = MSB
    assert input_value(0b10000, 5, 4) == 0


def test_cube_string_roundtrip_and_bits() -> None:
    c = cube_from_str("--101")
    assert c.to_str() == "--101"
    assert c.num_literals == 3
    assert c.care == 0b00111 and c.value == 0b00101
    assert cube_minterms(c) == [5, 13, 21, 29]


def test_covers_and_mask() -> None:
    c = cube_from_str("1-0")
    assert covers_minterm(c, 0b100) and covers_minterm(c, 0b110)
    assert not covers_minterm(c, 0b101)
    assert cube_mask(c) == (1 << 4) | (1 << 6)


def test_merge_adjacent() -> None:
    a, b = cube_from_str("0101"), cube_from_str("0111")
    assert merge_adjacent(a, b) == cube_from_str("01-1")
    assert merge_adjacent(cube_from_str("0101"), cube_from_str("0110")) is None
    assert merge_adjacent(cube_from_str("01-1"), cube_from_str("0111")) is None


def test_consensus() -> None:
    assert consensus(cube_from_str("1-1"), cube_from_str("0-1")) == cube_from_str("--1")
    assert consensus(cube_from_str("11-"), cube_from_str("0-1")) == cube_from_str("-11")
    assert consensus(cube_from_str("11-"), cube_from_str("00-")) is None  # two opposed variables
    assert consensus(cube_from_str("11-"), cube_from_str("0-1"), bit=1) is None  # restricted to b


def test_contains_intersects() -> None:
    assert contains(cube_from_str("1--"), cube_from_str("1-0"))
    assert not contains(cube_from_str("1-0"), cube_from_str("1--"))
    assert intersects(cube_from_str("1--"), cube_from_str("-0-"))
    assert not intersects(cube_from_str("1--"), cube_from_str("0--"))


def test_minterm_cube() -> None:
    assert minterm_cube(3, 6) == Cube(3, 0b111, 0b110)
