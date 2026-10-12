"""Per-output-group analysis: recover the implemented cover, count it, minimize, compare and decide the verdict."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from logilens.analysis.options import Options
from logilens.analysis.tables import TableView, circuit_functions, multi, spec_functions
from logilens.core.logic_types import BoolFunction, Form, MultiFunction, Spec
from logilens.core.netlist import CircuitNetlist
from logilens.graph.classify import Classification
from logilens.kmap.groups import views_for_cover
from logilens.logic.cost import nandnor_cost
from logilens.logic.recover import RecoveredCover, StructuralCost, recover_group, structural_cost
from logilens.minimize.compare import DEFAULT_METHODS, Comparison, compare_methods
from logilens.minimize.robustness import robustness
from logilens.report.model import CostPair, FormResult, GroupReport, MethodRow, Msg, Verdict
from logilens.spec.mapping import OutputMapping

SOP_TECH = frozenset({"nand", "and-or"})
POS_TECH = frozenset({"nor", "or-and"})
KMAP_VARS = range(2, 7)


@dataclass
class GroupContext:
    """Everything shared by the groups of one circuit."""

    circ: CircuitNetlist
    classification: Classification
    view: TableView
    alias: Mapping[str, str]  # input pin analysis name -> table input name (tied duplicates)
    spec: Spec | None
    mapping: OutputMapping | None


def group_variables(ctx: GroupContext, outputs: list[str]) -> tuple[tuple[str, ...], bool]:
    """Variables of a group (table order) and whether the spec inputs can be used for it.

    With a spec whose inputs all exist in the table and cover the group's support, the spec inputs are the
    variables; otherwise the structural support of the group.
    """
    support = {ctx.alias.get(s, s) for o in outputs for s in ctx.classification.supports.get(o, [])}
    if ctx.spec is not None:
        spec_vars = {v for v in ctx.view.inputs if v.lower() in {s.lower() for s in ctx.spec.inputs}}
        if len(spec_vars) == len(ctx.spec.inputs) and support <= spec_vars:
            return tuple(v for v in ctx.view.inputs if v in spec_vars), True
    return tuple(v for v in ctx.view.inputs if v in support), False


def _var_of_pin(ctx: GroupContext, variables: tuple[str, ...]) -> dict[int, int]:
    out = {}
    for pin in ctx.circ.inputs:
        name = ctx.alias.get(pin.name, pin.name)
        if name in variables:
            out[pin.comp_id] = variables.index(name)
    return out


def _forms(options: Options, recovered: RecoveredCover) -> tuple[Form, ...]:
    if options.forms == "sop":
        chosen: tuple[Form, ...] = (Form.SOP,)
    elif options.forms == "pos":
        chosen = (Form.POS,)
    elif options.forms == "both" or recovered.technology not in SOP_TECH | POS_TECH:
        chosen = (Form.SOP, Form.POS)
    else:
        chosen = (Form.SOP,) if recovered.technology in SOP_TECH else (Form.POS,)
    if recovered.ok and recovered.form is not None and recovered.form not in chosen:
        chosen = (recovered.form, *chosen)
    return chosen


def _methods(options: Options) -> tuple[str, ...]:
    methods = tuple(options.methods) if options.methods else DEFAULT_METHODS
    return methods if "ilp" in methods else (*methods, "ilp")


def _pair(gates: int | None, inputs: int | None) -> CostPair | None:
    return CostPair(gates, inputs) if gates is not None and inputs is not None else None


def _form_result(comp: Comparison, form: Form, mf: MultiFunction, options: Options) -> FormResult:
    ref = comp.reference.get(form)
    agreeing = set(comp.agreeing_with_reference(form))
    rows = [MethodRow(r.method, r.form, r.gates, r.inputs, r.proof, r.verified, r.runtime_s, r.note,
                      r.method in agreeing) for r in comp.rows if r.form is form]
    fr = FormResult(form, rows, CostPair(*ref) if ref else None)
    ilp = comp.results.get(("ilp", form))
    if ref is not None and ilp is not None and ilp.cover is not None:
        fr.best_cover, fr.best_cost, fr.best_method, fr.proven = ilp.cover, CostPair(*ref), "ilp", True
    else:
        candidates = [res for (m, f), res in comp.results.items()
                      if f is form and res.cover is not None and res.verified and res.cost is not None]
        if candidates:
            best = min(candidates, key=lambda r: (r.cost.gates, r.cost.inputs))  # type: ignore[union-attr]
            fr.best_cover, fr.best_method = best.cover, best.method
            fr.best_cost = CostPair(best.cost.gates, best.cost.inputs)  # type: ignore[union-attr]
    if options.robustness and fr.proven:
        rep = robustness(mf, form)
        fr.robustness, fr.robust_identical, fr.min_negators = rep.summary(), rep.identical, rep.min_negators
    if options.kmaps and fr.best_cover is not None and mf.n in KMAP_VARS:
        fr.kmaps = views_for_cover(mf, fr.best_cover)
    return fr


def _verdict(group: GroupReport, recovered: RecoveredCover, structural: StructuralCost) -> None:
    if not recovered.ok:
        group.verdict = Verdict.BEYOND_TWO_LEVEL
        group.notes.append(Msg("note.beyond_two_level"))
        return
    group.verdict_form = recovered.form
    fr = group.form_result(recovered.form)
    if fr is None or fr.reference is None:
        group.verdict = Verdict.UNPROVEN
        group.notes.append(Msg("note.unproven"))
        return
    drawn = (structural.nandnor_gates, structural.nandnor_inputs)
    ref = (fr.reference.gates, fr.reference.inputs)
    group.delta = CostPair(drawn[0] - ref[0], drawn[1] - ref[1])
    if drawn > ref:
        group.verdict = Verdict.IMPROVABLE
        return
    group.verdict = Verdict.OPTIMAL
    if drawn < ref:
        group.notes.append(Msg("note.cheaper_than_nandnor", {"technology": recovered.technology}))


def _structure_notes(group: GroupReport, recovered: RecoveredCover, structural: StructuralCost) -> None:
    if structural.not_gates:
        group.notes.append(Msg("note.not_gates_counted", {"count": structural.not_gates,
                                                          "drawn": structural.short(),
                                                          "nandnor": structural.nandnor_short()}))
    if structural.unconnected_inputs:
        group.notes.append(Msg("note.unconnected_not_counted", {"count": structural.unconnected_inputs}))
    if structural.negated_inputs:
        group.notes.append(Msg("note.negated_inputs", {"count": structural.negated_inputs}))
    if recovered.ok and group.implemented_cost is not None and structural.gates > group.implemented_cost.gates:
        extra = structural.gates - group.implemented_cost.gates
        group.notes.append(Msg("note.redundant_gates", {"count": extra}))
    if recovered.technology in ("and-or", "or-and"):
        group.notes.append(Msg("note.and_or_compared", {"technology": recovered.technology.upper()}))


def analyze_group(ctx: GroupContext, index: int, outputs: list[str], options: Options) -> GroupReport:
    """Full analysis of one output group."""
    variables, spec_vars = group_variables(ctx, outputs)
    circuit_f = circuit_functions(ctx.view, outputs, variables)
    spec_f = spec_functions(ctx.spec, ctx.mapping, outputs, variables) if ctx.spec and ctx.mapping and spec_vars \
        else None
    functions: dict[str, BoolFunction] = {o: (spec_f or {}).get(o, circuit_f[o]) for o in outputs}
    group = GroupReport(index, outputs, list(variables), "spec" if spec_f else "circuit",
                        {o: f.dc.bit_count() for o, f in functions.items()})
    if ctx.spec is not None and not spec_f:
        group.notes.append(Msg("note.spec_not_applicable"))
    elif ctx.spec is not None and spec_f is not None and len(spec_f) < len(outputs):
        group.notes.append(Msg("note.spec_partial", {"outputs": ", ".join(o for o in outputs if o not in spec_f)}))
    if not variables:
        group.notes.append(Msg("note.constant_group"))
        return group
    comps = set().union(*(ctx.classification.cones.get(o, set()) for o in outputs))
    structural = structural_cost(ctx.circ, comps)
    recovered = recover_group(ctx.circ, ctx.classification.graph, outputs, variables, _var_of_pin(ctx, variables),
                              circuit_f)
    _fill_recovered(group, recovered, structural, functions, variables, options)
    if len(variables) > options.max_minimize_vars:
        group.notes.append(Msg("note.too_many_vars", {"n": len(variables), "max": options.max_minimize_vars}))
        return group
    if not options.minimize:
        return group
    mf = multi(variables, functions)
    comp = compare_methods(mf, forms=_forms(options, recovered), methods=_methods(options))
    group.forms = [_form_result(comp, f, mf, options) for f in _forms(options, recovered)]
    _verdict(group, recovered, structural)
    return group


def _fill_recovered(group: GroupReport, recovered: RecoveredCover, structural: StructuralCost,
                    functions: dict[str, BoolFunction], variables: tuple[str, ...], options: Options) -> None:
    group.structural = structural
    group.technology = recovered.technology
    group.recovered = recovered.status.value
    group.recover_reasons = list(recovered.reasons)
    if recovered.ok and recovered.cover is not None:
        group.implemented_form = recovered.form
        group.implemented_cover = recovered.cover
        cost = nandnor_cost(recovered.cover)
        group.implemented_cost = CostPair(cost.gates, cost.inputs)
        if options.kmaps and len(variables) in KMAP_VARS:
            group.implemented_kmaps = views_for_cover(multi(variables, functions), recovered.cover)
    _structure_notes(group, recovered, structural)


