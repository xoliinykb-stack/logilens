"""Read a `.circ` file into raw, uninterpreted records (``file/XmlReader`` structure).

Nothing here knows about component semantics; attribute values stay strings.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from logilens.core.errors import ParseError
from logilens.core.geometry import Point, parse_point

MAX_FILE_SIZE = 64 * 2**20


@dataclass
class RawComp:
    lib: str | None  # library descriptor ("#Gates", "file#x.circ", ...); None = circuit of this file
    name: str
    loc: Point
    attrs: dict[str, str]
    order: int


@dataclass
class RawCircuit:
    name: str
    attrs: dict[str, str]
    wires: list[tuple[Point, Point]]
    comps: list[RawComp]
    appear: ET.Element | None = None


@dataclass
class RawProject:
    path: str
    source: str
    version: str
    format: str
    libs: dict[str, str]  # lib name ("0") -> descriptor ("#Wiring")
    main: str
    options: dict[str, str]
    circuits: list[RawCircuit] = field(default_factory=list)


def _attrs(elt: ET.Element) -> dict[str, str]:
    """``<a name val>`` children; a missing ``val`` means the text content is the value."""
    out: dict[str, str] = {}
    for a in elt.findall("a"):
        name = a.get("name")
        if name is None:
            continue
        val = a.get("val")
        out[name] = val if val is not None else (a.text or "")
    return out


def detect_format(source: str) -> str:
    """``logisim-evolution`` for sources >= 3, else ``logisim-2.7.1``."""
    head = source.split(".", 1)[0] if source else "2"
    return "logisim-evolution" if head.isdigit() and int(head) >= 3 else "logisim-2.7.1"


def _circuit(elt: ET.Element, libs: dict[str, str], path: str) -> RawCircuit:
    name = elt.get("name")
    if name is None:
        raise ParseError("<circuit> without a name", path)
    wires: list[tuple[Point, Point]] = []
    comps: list[RawComp] = []
    for i, child in enumerate(elt):
        if child.tag == "wire":
            try:
                wires.append((parse_point(child.get("from", "")), parse_point(child.get("to", ""))))
            except (ValueError, TypeError) as exc:
                raise ParseError(f"bad wire in circuit {name!r}: {exc}", path) from exc
        elif child.tag == "comp":
            lib_name = child.get("lib")
            lib = None if not lib_name else libs.get(lib_name, f"?{lib_name}")
            try:
                loc = parse_point(child.get("loc", ""))
            except (ValueError, TypeError) as exc:
                raise ParseError(f"component {child.get('name')!r} without a valid loc", path) from exc
            comps.append(RawComp(lib, child.get("name", ""), loc, _attrs(child), i))
    return RawCircuit(name, _attrs(elt), wires, comps, elt.find("appear"))


def read_circ(path: str | os.PathLike[str]) -> RawProject:
    """Parse the XML of a `.circ` file. Raises :class:`ParseError`."""
    p = str(path)
    try:
        data = Path(p).read_bytes()
    except OSError as exc:
        raise ParseError(f"cannot read file: {exc.strerror or exc}", p) from exc
    if len(data) > MAX_FILE_SIZE:
        raise ParseError(f"file is too large for a Logisim circuit ({len(data) // 2**20} MiB)", p)
    # Logisim never writes a DTD; refusing one rules out entity-expansion bombs.
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ParseError("DTD / entity declarations are not allowed in .circ files", p)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"not a valid XML file: {exc}", p) from exc
    if root.tag != "project":
        raise ParseError(f"root element is <{root.tag}>, expected <project>", p)
    libs = {lib.get("name", ""): lib.get("desc", "") for lib in root.findall("lib")}
    source = root.get("source") or "2.7.1"
    main_elt = root.find("main")
    options_elt = root.find("options")
    circuits = [_circuit(c, libs, p) for c in root.findall("circuit")]
    if not circuits:
        raise ParseError("no <circuit> in project", p)
    main = (main_elt.get("name") if main_elt is not None else None) or circuits[0].name
    return RawProject(
        path=p,
        source=source,
        version=root.get("version", ""),
        format=detect_format(source),
        libs=libs,
        main=main,
        options=_attrs(options_elt) if options_elt is not None else {},
        circuits=circuits,
    )
