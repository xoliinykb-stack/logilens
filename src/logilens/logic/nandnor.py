"""NAND (↑) / NOR (↓) rewriting of two-level covers with step-by-step derivations.

SOP (NAND-NAND)::

    F = t1 + t2 + ...
      = overline(overline(t1 + t2 + ...))          double negation
      = overline(overline(t1) · overline(t2) ...)  De Morgan
      = (t1↑)↑(t2↑)...  i.e. NAND of NANDs, a negated literal x' written as (x↑)

POS (NOR-NOR) is the dual with ↓.
"""

from __future__ import annotations

from dataclasses import dataclass

from logilens.core.logic_types import Cover, Cube, Form
from logilens.logic.cube import literal_positions
from logilens.logic.expr import (
    And,
    Expr,
    Nand,
    Nor,
    Not,
    Or,
    Var,
    cover_to_expr,
    cube_to_expr,
    to_text,
)


@dataclass(frozen=True)
class Derivation:
    """Derivation of one output: ``lines[0]`` is the two-level form, the last line is pure NAND/NOR."""

    output: str
    form: Form
    lines: tuple[Expr, ...]
    rules: tuple[str, ...]


def _gate(form: Form, args: tuple[Expr, ...]) -> Expr:
    return Nand(args) if form is Form.SOP else Nor(args)


def _gate_literal(c: Cube, i: int, v: int, names: tuple[str, ...], form: Form) -> Expr:
    """Literal as gate input: negated literal x' -> (x↑) / (x↓); positive literal -> x."""
    negated = (v == 0) if form is Form.SOP else (v == 1)
    return _gate(form, (Var(names[i]),)) if negated else Var(names[i])


def _first_level(c: Cube, names: tuple[str, ...], form: Form) -> Expr:
    """What the output gate receives for cube ``c``: the term gate, or the complemented single literal."""
    lits = [_gate_literal(c, i, v, names, form) for i, v in literal_positions(c)]
    if len(lits) >= 2:
        return _gate(form, tuple(lits))
    (i, v), = literal_positions(c)
    negated = (v == 0) if form is Form.SOP else (v == 1)
    # the output gate needs the complement of the literal
    return Var(names[i]) if negated else _gate(form, (Var(names[i]),))


def _gate_form(cubes: tuple[Cube, ...], names: tuple[str, ...], form: Form) -> Expr:
    if len(cubes) == 1 and cubes[0].num_literals == 1:
        return _gate_literal(cubes[0], *literal_positions(cubes[0])[0], names, form)
    return _gate(form, tuple(_first_level(c, names, form) for c in cubes))


def derive(output: str, cubes: tuple[Cube, ...] | list[Cube], names: tuple[str, ...], form: Form) -> Derivation:
    """Derivation lines for one output's cover."""
    cubes = tuple(cubes)
    base = cover_to_expr(cubes, names, form)
    if not cubes or any(c.num_literals == 0 for c in cubes):
        return Derivation(output, form, (base,), ("constant",))
    if len(cubes) == 1 and cubes[0].num_literals == 1:
        last = _gate_form(cubes, names, form)
        if last == base:
            return Derivation(output, form, (base,), ("single literal, no gate",))
        return Derivation(output, form, (base, last), ("form", "NOT as tied gate"))
    double = Not(Not(base))
    parts = tuple(Not(cube_to_expr(c, names, form)) for c in cubes)
    if len(cubes) == 1:
        de_morgan: Expr = Not(parts[0])
    else:
        de_morgan = Not(And(parts) if form is Form.SOP else Or(parts))
    rules = ("form", "double negation", "De Morgan", "NAND" if form is Form.SOP else "NOR")
    return Derivation(output, form, (base, double, de_morgan, _gate_form(cubes, names, form)), rules)


def derive_cover(cover: Cover) -> list[Derivation]:
    """Derivations for every output of a cover."""
    return [derive(name, cubes, cover.inputs, cover.form) for name, cubes in cover.terms.items()]


def render_derivation(d: Derivation, style: str = "unicode") -> list[str]:
    """``['F = ...', '  = ...', ...]``; ``style`` 'unicode' (overlines) or 'ascii' (x', NOT(...))."""
    out = []
    pad = " " * len(d.output)
    for k, e in enumerate(d.lines):
        prefix = f"{d.output} = " if k == 0 else f"{pad} = "
        out.append(prefix + to_text(e, style))
    return out


def gate_expression(d: Derivation) -> Expr:
    """The final pure-NAND/NOR expression (or the literal/constant itself)."""
    return d.lines[-1]


__all__ = ["Derivation", "derive", "derive_cover", "gate_expression", "render_derivation"]
