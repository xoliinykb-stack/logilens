"""Generate the two-level converter fixtures (explicitly wired, rail layout) in tests/fixtures/.

Run:  .venv/bin/python tests/fixtures/gen/converters.py [--no-validate]

Written files:
  converter.spec.txt        5-bit line code (12 valid words) -> 4-bit digit, code table
  converter_nand_nor.circ   minimal NAND-NAND (A_N..D_N) and NOR-NOR (A_R..D_R) halves, built from the ILP optimum
  converter_draft.circ      the same converter drawn badly (NOT gates, unshared terms, duplicate input pins,
                            a loose NOR input, dangling wire ends, unlabeled outputs)
  sample_bcd_excess3.circ   small BCD 8421 -> Excess-3 sample with a few stale gate inputs
  mixed_gates.circ          AND/OR/XOR/NOT multi-level circuit

Layout: every net gets one vertical rail; gates sit in columns by logic level, one horizontal band per gate;
inputs are tapped from the rails with horizontal wires that end on the rail (a wire end on the middle of another
wire connects, plain crossings do not).
"""

from __future__ import annotations

import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

from generate import Circ, Comp, project_xml

from logilens.core.logic_types import Cube, Form
from logilens.minimize.ilp import ilp_minimize
from logilens.spec.parse import load_spec, spec_function

FIXTURES = Path(__file__).resolve().parents[1]
INPUT_Y = 100
LINE_CODE = [0, 1, 6, 8, 9, 15, 20, 24, 26, 28, 29, 31]  # valid 5-bit words, digit = position in this list


@dataclass
class G:
    """Gate description: kind, input nets (None = loose, ("stale", net) = tap stops one grid step short)."""

    kind: str
    ins: list
    out: str
    tied: bool = False


@dataclass
class Layout:
    gates: list[G]
    pins: list[tuple[str, str | None]]  # (net, label) of input pins, left to right
    outs: list[tuple[str, str | None]]  # (net, label) of output pins, top to bottom
    overshoot: dict[str, int] | None = None  # net -> extra rail length (dangling end)


def _net_of(i) -> str | None:
    return i[1] if isinstance(i, tuple) else i


def draw(name: str, lay: Layout, pin_x0: int = 100, pin_pitch: int = 30) -> Circ:
    c = Circ(name)
    level: dict[str, int] = {n: 0 for n, _ in lay.pins}
    pending = list(lay.gates)
    order: list[G] = []
    while pending:
        for g in list(pending):
            nets = [_net_of(i) for i in g.ins if _net_of(i)]
            if all(n in level for n in nets):
                level[g.out] = 1 + max([level[n] for n in nets] or [0])
                order.append(g)
                pending.remove(g)
                break
        else:
            raise ValueError("combinational loop or missing net")
    order.sort(key=lambda g: level[g.out])  # stable: keeps the given order inside a level
    max_level = max(level.values())

    rail_x: dict[str, int] = {}
    for k, (net, _) in enumerate(lay.pins):
        rail_x[net] = pin_x0 + pin_pitch * k
    cursor = pin_x0 + pin_pitch * len(lay.pins)
    gate_x: dict[int, int] = {}
    for lv in range(1, max_level + 1):
        gx = cursor + 80
        for g in order:
            if level[g.out] == lv:
                gate_x[id(g)] = gx
        outs = [g.out for g in order if level[g.out] == lv]
        for k, n in enumerate(outs):
            rail_x[n] = gx + 20 + 10 * k
        cursor = gx + 20 + 10 * len(outs) + 10
    pin_out_x = cursor + 60

    spans: dict[str, list[int]] = {n: [INPUT_Y] for n, _ in lay.pins}
    y = 200
    comps: dict[int, Comp] = {}
    for g in order:
        n_in = len(g.ins)
        attrs = {} if g.kind == "NOT Gate" else {"inputs": n_in}
        probe = Circ("probe").add("#Gates", g.kind, 0, 0, **attrs)
        dys = [p.y for k, p in probe.ports.items() if k.startswith("in")]
        reach = max(abs(d) for d in dys + [10])
        y += reach + 20
        gy = (y + 9) // 10 * 10
        comp = c.add("#Gates", g.kind, gate_x[id(g)], gy, **attrs)
        comps[id(g)] = comp
        y = gy + reach + 10
        in_ports = [p for k, p in comp.ports.items() if k.startswith("in")]
        spans.setdefault(g.out, []).append(gy)
        c.wire(comp.ports["out"], (rail_x[g.out], gy))
        if g.tied:
            c.wire(in_ports[0], (in_ports[0].x, gy))  # two halves, so the tap ends on a wire end
            c.wire((in_ports[0].x, gy), in_ports[-1])
            taps = [((in_ports[0].x, gy), g.ins[0])]
        else:
            taps = [((p.x, p.y), i) for p, i in zip(in_ports, g.ins)]
        for (px, py), i in taps:
            net = _net_of(i)
            if net is None:
                continue
            stale = isinstance(i, tuple)
            c.wire((rail_x[net], py), (px - 10 if stale else px, py))
            spans[net].append(py)
    y_pin = y + 20
    for k, (net, label) in enumerate(lay.outs):
        py = y_pin + 40 * k
        kw = {"label": label} if label else {}
        pin = c.add("#Wiring", "Pin", pin_out_x, py, facing="west", output=True, **kw,
                    **({"labelloc": "east"} if label else {}))
        c.wire((rail_x[net], py), pin.loc)
        spans[net].append(py)
    for k, (net, label) in enumerate(lay.pins):
        kw = {"label": label} if label else {}
        c.add("#Wiring", "Pin", rail_x[net], INPUT_Y, facing="south", tristate=False, **kw)
    extra = lay.overshoot or {}

    def touches(x: int, yy: int) -> bool:
        for a, b in c.wires:
            if min(a.x, b.x) <= x <= max(a.x, b.x) and min(a.y, b.y) <= yy <= max(a.y, b.y):
                return True
        return False

    def rail(net: str, ys: list[int]) -> None:
        pts = sorted(set(ys))  # one wire per stretch between taps: every tap meets wire ends only
        for lo, hi in itertools.pairwise(pts):
            c.wire((rail_x[net], lo), (rail_x[net], hi))

    for net, ys in spans.items():
        if net not in extra:
            rail(net, ys)
    for net, want in extra.items():  # rails that run on past their last tap and end in the air
        end = max(spans[net]) + want
        while touches(rail_x[net], end):
            end += 10
        rail(net, spans[net] + [end])
    return c


# ------------------------------------------------------------------ converter builder
def _literal_nets(cube: Cube, form: Form, names: tuple[str, ...], pre: str, neg_net, flip: bool = False) -> list[str]:
    nets = []
    for i, nm in enumerate(names):
        bit = 1 << (cube.n - 1 - i)
        if not cube.care & bit:
            continue
        one = bool(cube.value & bit)
        negated = (not one) if form is Form.SOP else one
        negated ^= flip
        nets.append(neg_net(pre + nm) if negated else pre + nm)
    return nets


def half_gates(cover_terms: dict[str, list[Cube]], form: Form, names: tuple[str, ...], tag: str, pre: str,
               out_names: dict[str, str], share: bool = True, not_gates: bool = False,
               loose_term: bool = False) -> tuple[list[G], dict[str, str]]:
    kind = "NAND Gate" if form is Form.SOP else "NOR Gate"
    gates: list[G] = []
    negs: dict[str, str] = {}

    def neg_net(v: str) -> str:
        if v not in negs:
            negs[v] = f"n{tag}_{v}"
            if not_gates:
                gates.append(G("NOT Gate", [v], negs[v]))
            else:
                gates.append(G(kind, [v, v], negs[v], tied=True))
        return negs[v]

    term_net: dict[tuple, str] = {}
    alias: dict[str, str] = {}
    loose_done = not loose_term
    for out, cubes in cover_terms.items():
        if len(cubes) == 1 and cubes[0].num_literals == 1:
            alias[out_names[out]] = _literal_nets(cubes[0], form, names, pre, neg_net)[0]  # output = one literal
            continue
        ins = []
        for cube in cubes:
            key = cube.key if share else (out, cube.key)
            if key not in term_net:
                lits = _literal_nets(cube, form, names, pre, neg_net)
                if len(lits) == 1:  # a one-literal term feeds the output gate with the opposite literal
                    term_net[key] = _literal_nets(cube, form, names, pre, neg_net, flip=True)[0]
                else:
                    t = f"t{tag}{len(term_net)}"
                    row = list(lits)
                    if not loose_done and kind == "NOR Gate" and len(lits) >= 2:
                        row.append(None)
                        loose_done = True
                    gates.append(G(kind, row, t))
                    term_net[key] = t
            ins.append(term_net[key])
        if len(ins) > 1:
            gates.append(G(kind, ins, out_names[out]))
        else:  # a single product: invert its term
            gates.append(G(kind, [ins[0], ins[0]], out_names[out], tied=True))
    return gates, alias


def build_converter(spec_path: Path, draft: bool) -> Circ:
    spec = load_spec(spec_path)
    mf = spec_function(spec)
    names = mf.inputs
    covers = {}
    for form in (Form.SOP, Form.POS):
        res = ilp_minimize(mf, form)
        assert res.proof is not None and res.proof.status == "Optimal"
        covers[form] = {o: list(cs) for o, cs in res.cover.terms.items()}
    gates: list[G] = []
    pins: list[tuple[str, str | None]] = []
    outs: list[tuple[str, str | None]] = []
    for form, suffix, tag in ((Form.SOP, "N", "n"), (Form.POS, "R", "r")):
        pre = f"{tag}." if draft else ""
        if draft or form is Form.SOP:
            pins += [(pre + nm, nm) for nm in names]
        onames = {o: f"{o}_{suffix}" for o in mf.outputs}
        g, alias = half_gates(covers[form], form, names, tag, pre, onames, share=not draft, not_gates=draft,
                              loose_term=draft and form is Form.POS)
        gates += g
        if draft:  # the draft routes "output = input" through two inverters instead of a plain wire
            for k, v in list(alias.items()):
                gates += [G("NOT Gate", [v], f"{v}_i{k}"), G("NOT Gate", [f"{v}_i{k}"], f"{k}_b")]
                alias[k] = f"{k}_b"
        outs += [(alias.get(onames[o], onames[o]), None if draft else onames[o]) for o in mf.outputs]
    overshoot = {pins[1][0]: 40, pins[-1][0]: 30} if draft else None
    return draw("main", Layout(gates, pins, outs, overshoot))


def sample() -> Circ:
    # BCD 8421 -> Excess-3, NAND-NAND, with a few gate inputs whose wire stops one grid step short
    from logilens.spec.parse import parse_spec

    text = "\n".join(f"{n} {n:04b} {n + 3:04b}" for n in range(10))
    mf = spec_function(parse_spec(text))
    res = ilp_minimize(mf, Form.SOP)
    onames = {o: f"{o}_xs3" for o in mf.outputs}
    gates, alias = half_gates({o: list(cs) for o, cs in res.cover.terms.items()}, Form.SOP, mf.inputs, "s", "",
                              onames)
    # make three multi-input first-level gates and one output gate carry a stale extra input
    stale_targets = [g for g in gates if g.kind == "NAND Gate" and not g.tied and len(g.ins) >= 2]
    chosen = [stale_targets[0], stale_targets[1], stale_targets[-1], stale_targets[-2]]
    for g in chosen:
        g.ins.append(("stale", g.ins[0]))
    return draw("main", Layout(gates, [(n, n) for n in mf.inputs], [(alias.get(onames[o], onames[o]), onames[o]) for o in mf.outputs]))


def mixed() -> Circ:
    gates = [
        G("XOR Gate", ["P", "Q"], "pq"),
        G("NOT Gate", ["P"], "np"),
        G("NOT Gate", ["R"], "nr"),
        G("AND Gate", ["pq", "R"], "t1"),
        G("AND Gate", ["np", "nr"], "t2"),
        G("OR Gate", ["t1", "t2"], "x"),
        G("NOT Gate", ["P"], "np2"),
        G("NOT Gate", ["Q"], "nq2"),
        G("NOT Gate", ["R"], "nr2"),
        G("AND Gate", ["np2", "Q"], "u1"),
        G("AND Gate", ["P", "nr2"], "u2"),
        G("AND Gate", ["nq2", "R"], "u3"),
        G("OR Gate", ["u1", "u2", "u3"], "y"),
    ]
    return draw("main", Layout(gates, [("P", "P"), ("Q", "Q"), ("R", "R")], [("x", None), ("y", None)]))


def main(argv: list[str]) -> int:
    spec_text = (
        "# code table: number  input(abcde)  output(ABCD); unlisted inputs = dont care\n"
        "# 5-bit line code (12 valid words) to a 4-bit binary digit\n"
        "# inputs: a b c d e   outputs: A B C D\n"
        + "".join(f"{n:<2} {w:05b} {n:04b}\n" for n, w in enumerate(LINE_CODE))
    )
    spec = FIXTURES / "converter.spec.txt"
    spec.write_text(spec_text, encoding="utf-8")
    files = {
        "converter_nand_nor.circ": build_converter(spec, draft=False),
        "converter_draft.circ": build_converter(spec, draft=True),
        "sample_bcd_excess3.circ": sample(),
        "mixed_gates.circ": mixed(),
    }
    bridge = None
    if "--no-validate" not in argv:
        from logilens.backends.java.backend import JavaBridge

        bridge = JavaBridge()
    for fname, circ in files.items():
        path = FIXTURES / fname
        path.write_text(project_xml([circ], "main"), encoding="utf-8")
        if bridge is not None:
            dump = bridge.dump(str(path))
            n = sum(len(x["components"]) for x in dump["circuits"])
            print(f"{fname}: Logisim loaded, {n} components")
        else:
            print(f"{fname}: written (not validated)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
