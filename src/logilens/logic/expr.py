"""Boolean expression trees: construction from cubes, parsing, evaluation and text rendering.

Rendering styles:

* ``'ascii'``: complemented variable ``a'``, complemented sub-expression ``NOT(...)``;
* ``'unicode'``: overline via combining U+0305 over every character of the negated text.

NAND/NOR are rendered in textbook style: ``x↑y↑z`` (n-ary), a one-input (tied) gate as ``(x↑)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from logilens.core.logic_types import Cube, Form
from logilens.logic.cube import literal_positions

OVERLINE = "̅"
DOUBLE_OVERLINE = "̿"


@dataclass(frozen=True)
class Var:
    """Input variable."""

    name: str


@dataclass(frozen=True)
class Const:
    """Constant 0 or 1."""

    value: int


@dataclass(frozen=True)
class Not:
    """Negation."""

    arg: Expr


@dataclass(frozen=True)
class And:
    """Conjunction."""

    args: tuple[Expr, ...]


@dataclass(frozen=True)
class Or:
    """Disjunction."""

    args: tuple[Expr, ...]


@dataclass(frozen=True)
class Xor:
    """Exclusive or."""

    args: tuple[Expr, ...]


@dataclass(frozen=True)
class Nand:
    """NAND gate (one argument = tied inputs = NOT)."""

    args: tuple[Expr, ...]


@dataclass(frozen=True)
class Nor:
    """NOR gate (one argument = tied inputs = NOT)."""

    args: tuple[Expr, ...]


Expr = Var | Const | Not | And | Or | Xor | Nand | Nor


# ---------------------------------------------------------------- evaluation


def evaluate(e: Expr, env: dict[str, int]) -> int:
    """Evaluate ``e`` with variable values from ``env`` (0/1)."""
    if isinstance(e, Var):
        return env[e.name] & 1
    if isinstance(e, Const):
        return e.value
    if isinstance(e, Not):
        return 1 - evaluate(e.arg, env)
    vals = [evaluate(a, env) for a in e.args]
    if isinstance(e, And):
        return int(all(vals))
    if isinstance(e, Or):
        return int(any(vals))
    if isinstance(e, Xor):
        return sum(vals) & 1
    if isinstance(e, Nand):
        return 1 - int(all(vals))
    return 1 - int(any(vals))  # Nor


def variables(e: Expr) -> list[str]:
    """Variable names in order of first appearance."""
    seen: dict[str, None] = {}
    stack = [e]
    while stack:
        x = stack.pop()
        if isinstance(x, Var):
            seen.setdefault(x.name, None)
        elif isinstance(x, Not):
            stack.append(x.arg)
        elif not isinstance(x, Const):
            stack.extend(reversed(x.args))
    return list(seen)


def truth_mask(e: Expr, inputs: tuple[str, ...] | list[str]) -> int:
    """Bitmask of minterms (inputs MSB-first) where ``e`` is 1."""
    n = len(inputs)
    mask = 0
    for m in range(1 << n):
        env = {name: (m >> (n - 1 - i)) & 1 for i, name in enumerate(inputs)}
        if evaluate(e, env):
            mask |= 1 << m
    return mask


# ---------------------------------------------------------------- from cubes


def cube_to_expr(c: Cube, names: tuple[str, ...] | list[str], form: Form) -> Expr:
    """SOP: product of literals ('0' -> x'). POS: clause (sum) where '0' -> x and '1' -> x'."""
    lits: list[Expr] = []
    for i, v in literal_positions(c):
        negated = (v == 0) if form is Form.SOP else (v == 1)
        lits.append(Not(Var(names[i])) if negated else Var(names[i]))
    if not lits:
        return Const(1 if form is Form.SOP else 0)
    if len(lits) == 1:
        return lits[0]
    return And(tuple(lits)) if form is Form.SOP else Or(tuple(lits))


def cover_to_expr(cubes: tuple[Cube, ...] | list[Cube], names: tuple[str, ...] | list[str], form: Form) -> Expr:
    """Two-level expression of one output's cover (SOP sum of products / POS product of sums)."""
    parts = [cube_to_expr(c, names, form) for c in cubes]
    if not parts:
        return Const(0 if form is Form.SOP else 1)
    if len(parts) == 1:
        return parts[0]
    return Or(tuple(parts)) if form is Form.SOP else And(tuple(parts))


# ---------------------------------------------------------------- rendering


def _overline(text: str) -> str:
    """Add one overline level to every base character (U+0305, then U+033F double, then stacked)."""
    out: list[str] = []
    for ch in text:
        if ch in (OVERLINE, DOUBLE_OVERLINE):
            continue
        out.append(ch)
    marks = _mark_levels(text)
    result = []
    for ch, level in zip(out, marks):
        level += 1
        result.append(ch + (DOUBLE_OVERLINE * (level // 2)) + (OVERLINE * (level % 2)))
    return "".join(result)


def _mark_levels(text: str) -> list[int]:
    """Overline nesting level already present on each base character of ``text``."""
    levels: list[int] = []
    for ch in text:
        if ch == OVERLINE and levels:
            levels[-1] += 1
        elif ch == DOUBLE_OVERLINE and levels:
            levels[-1] += 2
        else:
            levels.append(0)
    return levels


def _is_atom(e: Expr) -> bool:
    return isinstance(e, (Var, Const)) or (isinstance(e, Not) and isinstance(e.arg, Var))


def _names_single_char(e: Expr) -> bool:
    return all(len(v) == 1 for v in variables(e))


def to_text(e: Expr, style: str = "ascii") -> str:
    """Render ``e`` as text (``style`` = 'ascii' or 'unicode')."""
    return _render(e, style, _names_single_char(e))


def _render(e: Expr, style: str, compact: bool) -> str:
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Const):
        return str(e.value)
    if isinstance(e, Not):
        return _render_not(e, style, compact)
    if isinstance(e, And):
        sep = "" if compact and all(_is_atom(a) for a in e.args) else "·"
        return sep.join(_wrap(a, style, compact, (Or, Xor, Nand, Nor)) for a in e.args)
    if isinstance(e, Or):
        return " + ".join(_wrap(a, style, compact, (Nand, Nor)) for a in e.args)
    if isinstance(e, Xor):
        return " ⊕ ".join(_wrap(a, style, compact, (Or, And, Nand, Nor)) for a in e.args)
    op = "↑" if isinstance(e, Nand) else "↓"
    if len(e.args) == 1:
        return f"({_gate_arg(e.args[0], style, compact)}{op})"
    return op.join(_gate_arg(a, style, compact) for a in e.args)


def _render_not(e: Not, style: str, compact: bool) -> str:
    inner = e.arg
    if style == "unicode":
        return _overline(_render(inner, style, compact))
    if isinstance(inner, Var):
        return inner.name + "'"
    return f"NOT({_render(inner, style, compact)})"


def _wrap(e: Expr, style: str, compact: bool, kinds: tuple[type, ...]) -> str:
    text = _render(e, style, compact)
    return f"({text})" if isinstance(e, kinds) and len(getattr(e, "args", ())) > 1 else text


def _gate_arg(e: Expr, style: str, compact: bool) -> str:
    text = _render(e, style, compact)
    if isinstance(e, (Var, Const)):
        return text
    if isinstance(e, (Nand, Nor)) and len(e.args) == 1:
        return text  # already "(x↑)"
    return f"({text})"


# ---------------------------------------------------------------- parsing

_TOKEN = re.compile(r"\s*(?:(?P<name>[A-Za-z_][0-9_]*)|(?P<const>[01])|(?P<op>[+|*&·^'!~()¬]))")


class ExprSyntaxError(ValueError):
    """Raised for malformed Boolean expressions."""


def _tokenize(text: str, names: list[str] | None) -> list[str]:
    tokens: list[str] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        if names:
            hit = next((nm for nm in names if text.startswith(nm, pos)), None)
            if hit:
                tokens.append("$" + hit)
                pos += len(hit)
                continue
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ExprSyntaxError(f"unexpected character {text[pos]!r} at {pos} in {text!r}")
        if m.group("name"):
            tokens.append("$" + m.group("name"))
        else:
            tokens.append(m.group("const") or m.group("op"))
        pos = m.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.toks = tokens
        self.i = 0

    def peek(self) -> str | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> str:
        tok = self.peek()
        if tok is None:
            raise ExprSyntaxError("unexpected end of expression")
        self.i += 1
        return tok

    def parse(self) -> Expr:
        e = self.parse_or()
        if self.peek() is not None:
            raise ExprSyntaxError(f"unexpected token {self.peek()!r}")
        return e

    def parse_or(self) -> Expr:
        args = [self.parse_xor()]
        while self.peek() in ("+", "|"):
            self.take()
            args.append(self.parse_xor())
        return args[0] if len(args) == 1 else Or(tuple(args))

    def parse_xor(self) -> Expr:
        args = [self.parse_and()]
        while self.peek() == "^":
            self.take()
            args.append(self.parse_and())
        return args[0] if len(args) == 1 else Xor(tuple(args))

    def parse_and(self) -> Expr:
        args = [self.parse_unary()]
        while True:
            tok = self.peek()
            if tok in ("*", "&", "·"):
                self.take()
                args.append(self.parse_unary())
            elif tok is not None and (tok[0] == "$" or tok in ("(", "!", "~", "¬", "0", "1")):
                args.append(self.parse_unary())  # juxtaposition
            else:
                break
        return args[0] if len(args) == 1 else And(tuple(args))

    def parse_unary(self) -> Expr:
        if self.peek() in ("!", "~", "¬"):
            self.take()
            return Not(self.parse_unary())
        e = self.parse_atom()
        while self.peek() == "'":
            self.take()
            e = Not(e)
        return e

    def parse_atom(self) -> Expr:
        tok = self.take()
        if tok == "(":
            e = self.parse_or()
            if self.take() != ")":
                raise ExprSyntaxError("missing ')'")
            return e
        if tok in ("0", "1"):
            return Const(int(tok))
        if tok.startswith("$"):
            return Var(tok[1:])
        raise ExprSyntaxError(f"unexpected token {tok!r}")


def parse_expr(text: str, names: list[str] | tuple[str, ...] | None = None) -> Expr:
    """Parse ``a'b + c(d+e')`` style text. Operators: ``+ |`` OR, ``* & ·``/juxtaposition AND, ``^`` XOR,
    postfix ``'`` and prefix ``! ~ ¬`` NOT. Without ``names`` a variable is one letter followed by optional
    digits/underscores (``x1x2`` = x1·x2); with ``names`` the longest known name is matched first."""
    known = sorted(names, key=len, reverse=True) if names else None
    return _Parser(_tokenize(text, known)).parse()
