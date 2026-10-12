"""Expression parsing/rendering and the NAND/NOR derivation."""

from __future__ import annotations

from logilens.core.logic_types import Form
from logilens.logic.cube import cube_from_str
from logilens.logic.expr import And, Nand, Not, Var, cover_to_expr, parse_expr, to_text, truth_mask
from logilens.logic.nandnor import derive, render_derivation

NAMES = ("a", "b", "c", "d")


def test_parse_and_evaluate() -> None:
    e = parse_expr("a'b + c(d + a')")
    assert to_text(e) == "a'b + c·(d + a')"
    assert truth_mask(parse_expr("x1x2"), ("x1", "x2")) == 1 << 3
    assert parse_expr("!a") == Not(Var("a"))


def test_cover_rendering_sop_pos() -> None:
    sop = cover_to_expr([cube_from_str("10--"), cube_from_str("--11")], NAMES, Form.SOP)
    assert to_text(sop) == "ab' + cd"
    pos = cover_to_expr([cube_from_str("---00"), cube_from_str("01111")], NAMES + ("e",), Form.POS)
    assert to_text(pos) == "(d + e)·(a + b' + c' + d' + e')"


def test_unicode_overline() -> None:
    assert to_text(Not(Var("a")), "unicode") == "a̅"
    assert to_text(Not(Not(Var("a"))), "unicode") == "a̿"
    assert to_text(Not(And((Var("a"), Var("b")))), "unicode") == "a̅b̅"


def test_nand_derivation_sop() -> None:
    d = derive("F", [cube_from_str("10--"), cube_from_str("--11")], NAMES, Form.SOP)
    assert render_derivation(d, "ascii") == [
        "F = ab' + cd",
        "  = NOT(NOT(ab' + cd))",
        "  = NOT(NOT(ab')·NOT(cd))",
        "  = (a↑(b↑))↑(c↑d)",
    ]
    assert d.lines[-1] == Nand((Nand((Var("a"), Nand((Var("b"),)))), Nand((Var("c"), Var("d")))))


def test_nor_derivation_pos() -> None:
    d = derive("G", [cube_from_str("00--"), cube_from_str("--1-")], NAMES, Form.POS)
    # single complemented literal c' enters the output NOR as c (no negator); positive c needs (c↓)
    assert render_derivation(d, "ascii")[-1] == "  = (a↓b)↓c"
    assert render_derivation(d, "ascii")[0] == "G = (a + b)·c'"
    d2 = derive("G", [cube_from_str("00--"), cube_from_str("--0-")], NAMES, Form.POS)
    assert render_derivation(d2, "ascii")[-1] == "  = (a↓b)↓(c↓)"


def test_single_term_and_literal_outputs() -> None:
    d = derive("F", [cube_from_str("11--")], NAMES, Form.SOP)
    assert render_derivation(d, "ascii")[-1] == "  = ((a↑b)↑)"
    lit = derive("F", [cube_from_str("1---")], NAMES, Form.SOP)
    assert render_derivation(lit, "ascii") == ["F = a"]
    neg = derive("F", [cube_from_str("0---")], NAMES, Form.SOP)
    assert render_derivation(neg, "ascii") == ["F = a'", "  = (a↑)"]
    single_in_sum = derive("F", [cube_from_str("1---"), cube_from_str("0---")], NAMES, Form.SOP)
    assert render_derivation(single_in_sum, "ascii")[-1] == "  = (a↑)↑a"
