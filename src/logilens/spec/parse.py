"""Specification parsers: code tables, CSV/TSV/plain truth tables and Boolean expressions.

Formats
-------
* **code table** — lines ``number input output`` (or ``input output``), ``#`` comments; an optional header
  comment ``# inputs: a b c d e  outputs: A B C D`` names the signals (default ``a b c …`` / ``A B C …``).
* **truth table** — a header row of names, then rows; separators ``,`` ``;`` tab or whitespace. Inputs and
  outputs are split by a ``|`` column, by ``n_inputs``, or by case (lower-case inputs, upper-case outputs).
  A column may hold a multi-bit string when its header has one character per bit (``abcde,ABCD``).
  Output values ``0 1 X x -``; input ``-``/``X`` expands to all matching rows.
* **expressions** — lines ``A = a'b + c(d+e')`` (``'`` ``!`` ``~`` NOT, juxtaposition/``*``/``&`` AND,
  ``+``/``|`` OR, ``^`` XOR). Inputs from ``# inputs: …`` or the variables used, sorted.

Minterms absent from the spec mean ``unlisted`` ('dc' by default; 'dc'/'0'/'1').
"""

from __future__ import annotations

import re
from itertools import product
from pathlib import Path

from logilens.core.logic_types import CodeRow, MultiFunction, Spec
from logilens.logic.expr import ExprSyntaxError, parse_expr, truth_mask, variables
from logilens.logic.truth_table import multi_from_rows

_HEADER = re.compile(r"inputs?\s*[:=]\s*(?P<ins>.+?)\s+outputs?\s*[:=]\s*(?P<outs>.+)$", re.IGNORECASE)
_INPUTS_ONLY = re.compile(r"inputs?\s*[:=]\s*(?P<ins>.+)$", re.IGNORECASE)
_BITS = re.compile(r"^[01xX-]+$")
_SEPARATORS = {"|", "||", "->", "=>", ":"}


class SpecError(ValueError):
    """Malformed specification."""


def _default_names(count: int, upper: bool) -> tuple[str, ...]:
    base = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if upper else "abcdefghijklmnopqrstuvwxyz"
    if count <= len(base):
        return tuple(base[:count])
    return tuple(f"{'Y' if upper else 'x'}{i}" for i in range(count))


def _split_names(text: str) -> tuple[str, ...]:
    parts = text.replace(",", " ").split()
    if len(parts) == 1 and len(parts[0]) > 1 and parts[0].isalpha():
        return tuple(parts[0])
    return tuple(parts)


def expand_pattern(pattern: str) -> list[int]:
    """Minterms matching an input pattern with '-'/'x' wildcards (MSB first)."""
    choices = [("0", "1") if ch in "-xX" else (ch,) for ch in pattern]
    return [int("".join(bits), 2) for bits in product(*choices)]


def _norm_out(text: str) -> str:
    return "".join("-" if ch in "xX-" else ch for ch in text)


def _add_row(rows: dict[int, str], m: int, outs: str, where: str) -> None:
    old = rows.get(m)
    if old is None:
        rows[m] = outs
        return
    merged = []
    for a, b in zip(old, outs):
        if a != b and "-" not in (a, b):
            raise SpecError(f"{where}: conflicting values for minterm {m}: {old} vs {outs}")
        merged.append(b if a == "-" else a)
    rows[m] = "".join(merged)


def _comment_header(lines: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    for line in lines:
        if line.lstrip().startswith("#"):
            m = _HEADER.search(line.lstrip("# \t"))
            if m:
                return _split_names(m.group("ins")), _split_names(m.group("outs"))
    return None


def _content(text: str) -> list[tuple[int, str]]:
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append((no, line))
    return out


# ------------------------------------------------------------------ code tables


def parse_code_table(text: str, source: str = "", unlisted: str = "dc") -> Spec:
    """Parse ``number input output`` lines (see module doc)."""
    rows: dict[int, str] = {}
    codes: list[CodeRow] = []
    n = k = None
    for no, line in _content(text):
        tokens = line.split()
        if len(tokens) == 3 and tokens[0].isdigit():
            number, ins, outs = int(tokens[0]), tokens[1], tokens[2]
        elif len(tokens) == 2:
            number, ins, outs = None, tokens[0], tokens[1]
        else:
            raise SpecError(f"{source}:{no}: expected 'number input output', got {line!r}")
        if not _BITS.match(ins) or not _BITS.match(outs):
            raise SpecError(f"{source}:{no}: bits expected in {line!r}")
        if (n, k) != (None, None) and (len(ins), len(outs)) != (n, k):
            raise SpecError(f"{source}:{no}: inconsistent widths in {line!r}")
        n, k = len(ins), len(outs)
        codes.append(CodeRow(number, ins, _norm_out(outs)))
        for m in expand_pattern(ins):
            _add_row(rows, m, _norm_out(outs), f"{source}:{no}")
    if n is None or k is None:
        raise SpecError(f"{source}: no code rows found")
    names = _comment_header(text.splitlines())
    inputs, outputs = names if names else (_default_names(n, False), _default_names(k, True))
    if (len(inputs), len(outputs)) != (n, k):
        raise SpecError(f"{source}: header names {inputs}/{outputs} do not match widths {n}/{k}")
    return Spec(inputs, outputs, rows, unlisted, tuple(codes), source, "codes")


# ------------------------------------------------------------------ truth tables


def _cells(line: str) -> list[str]:
    for sep in ("\t", ",", ";"):
        if sep in line:
            return [c.strip() for c in line.split(sep)]
    return line.split()


def _split_columns(header: list[str], n_inputs: int | None) -> tuple[list[int], list[int]]:
    """Indices of input and output columns."""
    seps = [i for i, h in enumerate(header) if h in _SEPARATORS or h == ""]
    cols = [i for i in range(len(header)) if i not in seps]
    if seps:
        return [i for i in cols if i < seps[0]], [i for i in cols if i > seps[0]]
    if n_inputs is not None:
        return cols[:n_inputs], cols[n_inputs:]
    lower = [i for i in cols if header[i][:1].islower()]
    upper = [i for i in cols if header[i][:1].isupper()]
    if lower and upper and max(lower) < min(upper):
        return lower, upper
    raise SpecError("cannot tell inputs from outputs: add a '|' column between inputs and outputs, or name inputs in lower case and outputs in upper case")


def _names_for(header: list[str], idx: list[int], sample: list[str]) -> tuple[str, ...]:
    names: list[str] = []
    for i in idx:
        width = len(sample[i])
        if width > 1:
            if len(header[i]) != width:
                raise SpecError(f"column {header[i]!r} holds {width} bits; give one character per bit")
            names.extend(header[i])
        else:
            names.append(header[i])
    return tuple(names)


def parse_truth_table(text: str, source: str = "", unlisted: str = "dc", n_inputs: int | None = None) -> Spec:
    """Parse a CSV/TSV/plain truth table with a header row (see module doc)."""
    content = _content(text)
    if len(content) < 2:
        raise SpecError(f"{source}: header and at least one row expected")
    header = _cells(content[0][1])
    data = [(no, _cells(line)) for no, line in content[1:]]
    in_idx, out_idx = _split_columns(header, n_inputs)
    inputs = _names_for(header, in_idx, data[0][1])
    outputs = _names_for(header, out_idx, data[0][1])
    rows: dict[int, str] = {}
    for no, cells in data:
        if len(cells) != len(header):
            raise SpecError(f"{source}:{no}: expected {len(header)} columns, got {len(cells)}")
        ins = "".join(cells[i] for i in in_idx)
        outs = _norm_out("".join(cells[i] for i in out_idx))
        if len(ins) != len(inputs) or len(outs) != len(outputs) or not _BITS.match(ins + outs):
            raise SpecError(f"{source}:{no}: bad row {cells}")
        for m in expand_pattern(ins):
            _add_row(rows, m, outs, f"{source}:{no}")
    return Spec(inputs, outputs, rows, unlisted, (), source, "table")


# ------------------------------------------------------------------ expressions


def parse_expressions(text: str, source: str = "", inputs: tuple[str, ...] | None = None) -> Spec:
    """Parse ``NAME = expression`` lines into a fully specified spec."""
    if inputs is None:
        for raw in text.splitlines():
            m = _INPUTS_ONLY.search(raw.lstrip("# \t")) if raw.lstrip().startswith("#") else None
            if m:
                inputs = _split_names(m.group("ins").split("output")[0])
                break
    exprs = {}
    for no, line in _content(text):
        name, sep, body = line.partition("=")
        if not sep or not name.strip():
            raise SpecError(f"{source}:{no}: expected 'NAME = expression'")
        try:
            exprs[name.strip()] = parse_expr(body, list(inputs) if inputs else None)
        except ExprSyntaxError as exc:
            raise SpecError(f"{source}:{no}: {exc}") from exc
    if not exprs:
        raise SpecError(f"{source}: no expressions found")
    used = sorted({v for e in exprs.values() for v in variables(e)})
    ins = tuple(inputs) if inputs else tuple(used)
    unknown = [v for v in used if v not in ins]
    if unknown:
        raise SpecError(f"{source}: unknown variables {unknown}")
    masks = {name: truth_mask(e, ins) for name, e in exprs.items()}
    rows = {m: "".join("1" if masks[o] >> m & 1 else "0" for o in exprs) for m in range(1 << len(ins))}
    return Spec(ins, tuple(exprs), rows, "0", (), source, "expr")


# ------------------------------------------------------------------ dispatch


def detect_kind(text: str) -> str:
    """'expr', 'table' or 'codes' by inspecting the first content line."""
    content = _content(text)
    if not content:
        raise SpecError("empty specification")
    first = content[0][1]
    if "=" in first and not first.startswith(("=", "|")):
        return "expr"
    tokens = _cells(first)
    if all(_BITS.match(t) or t.isdigit() for t in tokens):
        return "codes"
    return "table"


def parse_spec(
    text: str, source: str = "", kind: str | None = None, unlisted: str = "dc", n_inputs: int | None = None
) -> Spec:
    """Parse a specification of any supported format (auto-detected unless ``kind`` is given)."""
    if unlisted not in ("dc", "0", "1"):
        raise SpecError(f"unlisted must be 'dc', '0' or '1', not {unlisted!r}")
    kind = kind or detect_kind(text)
    if kind == "expr":
        return parse_expressions(text, source)
    if kind == "table":
        return parse_truth_table(text, source, unlisted, n_inputs)
    if kind == "codes":
        return parse_code_table(text, source, unlisted)
    raise SpecError(f"unknown spec kind {kind!r}")


def load_spec(path: str | Path, kind: str | None = None, unlisted: str = "dc", n_inputs: int | None = None) -> Spec:
    """Read and parse a specification file."""
    p = Path(path)
    return parse_spec(p.read_text(encoding="utf-8"), str(p), kind, unlisted, n_inputs)


def spec_function(spec: Spec) -> MultiFunction:
    """The specified multi-output function (unlisted minterms per ``spec.unlisted``)."""
    return multi_from_rows(spec.inputs, spec.outputs, spec.rows, spec.unlisted)
