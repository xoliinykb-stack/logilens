"""Pure-Python `.circ` parser (backend B): XML -> components -> nets."""

from logilens.parse.hierarchy import FlatCircuit, build_project, flatten, parse_project

__all__ = ["FlatCircuit", "build_project", "flatten", "parse_project"]
