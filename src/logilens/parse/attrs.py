"""Attribute defaults and parsing (``XmlReader.initAttributeSet`` semantics).

Logisim omits attributes equal to the factory default when saving, so a missing attribute means
*factory default* (some defaults depend on the ``<project source>`` version). Unparseable or
out-of-range values are ignored by Logisim (the default stays); we do the same.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from importlib import resources
from types import MappingProxyType
from typing import Any

SPEC_FILE = "components_271.json"


@lru_cache(maxsize=1)
def load_spec() -> Mapping[str, Any]:
    """The machine-readable Logisim 2.7.1 component spec (``components_271.json``)."""
    text = resources.files("logilens.parse").joinpath(SPEC_FILE).read_text(encoding="utf-8")
    return MappingProxyType(json.loads(text))


@lru_cache(maxsize=1)
def reference_namespace() -> Mapping[str, Any]:
    """Executable port routines embedded in the spec (key ``python_reference``; project-owned data)."""
    ns: dict[str, Any] = {}
    exec(compile(load_spec()["python_reference"], SPEC_FILE + ":python_reference", "exec"), ns)  # noqa: S102
    return MappingProxyType(ns)


def version_tuple(source: str | None) -> tuple[int, ...]:
    """``"2.7.1"`` -> ``(2, 7, 1, 0)``; missing -> 2.7.1."""
    return tuple(reference_namespace()["version_tuple"](source))


def parse_value(atype: str, raw: str) -> Any:
    """Parse one attribute string like Logisim; raises ``ValueError`` when Logisim would reject it."""
    return reference_namespace()["parse_attr_value"](atype, raw)


def _accept(ad: Mapping[str, Any], value: Any) -> bool:
    values = ad.get("values")
    if ad["type"] in ("option", "direction") and values and value not in values:
        return False
    rng = ad.get("range")
    return not (rng and isinstance(value, int) and not rng[0] <= value <= rng[1])


def _default(ad: Mapping[str, Any], version: tuple[int, ...]) -> Any:
    dflt = ad.get("default")
    vd = ad.get("version_default")
    if vd is not None:
        dflt = vd["new"] if version >= tuple(vd["since"]) else vd["old"]
    return None if dflt is None else parse_value(ad["type"], dflt)


def resolve_attrs(spec: Mapping[str, Any], xml_attrs: Mapping[str, str], source: str | None) -> dict[str, Any]:
    """Return every static attribute of ``spec`` with XML values applied over factory defaults.

    Dynamic attributes: ``negateN`` for N < inputs (default False) and splitter ``bitN`` (only when present;
    the port routine applies the Logisim fallback).
    """
    version = version_tuple(source)
    out: dict[str, Any] = {}
    for ad in spec["attributes"]:
        if ad.get("dynamic"):
            continue
        name = ad["name"]
        value = _default(ad, version)
        if name in xml_attrs:
            try:
                parsed = parse_value(ad["type"], xml_attrs[name])
                if _accept(ad, parsed):
                    value = parsed
            except (ValueError, TypeError, KeyError):
                pass  # Logisim logs the error and keeps the default
        out[name] = value
    for ad in spec["attributes"]:
        kind = ad.get("dynamic")
        if kind == "negate":
            for i in range(int(out.get("inputs", 0) or 0)):
                key = f"negate{i}"
                out[key] = xml_attrs.get(key, "false").strip().lower() == "true"
        elif kind == "splitter_bits":
            for i in range(int(out["incoming"])):
                key = f"bit{i}"
                if key in xml_attrs:
                    try:
                        out[key] = parse_value("splitter_bit", xml_attrs[key])
                    except ValueError:
                        pass
    return out
