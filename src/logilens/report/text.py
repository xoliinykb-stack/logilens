"""Renderer-independent text helpers: translated messages, verdict labels, cover formulas, derivations."""

from __future__ import annotations

from logilens.core.logic_types import Cover, Form
from logilens.i18n import t, template
from logilens.i18n.glossary import form_term, term
from logilens.logic.expr import cover_to_expr, to_text
from logilens.logic.nandnor import derive_cover, render_derivation
from logilens.report.model import FormResult, GroupReport, Msg, Report, Verdict

VERDICT_STYLE = {
    Verdict.OPTIMAL: "bold green",
    Verdict.IMPROVABLE: "bold yellow",
    Verdict.BEYOND_TWO_LEVEL: "bold magenta",
    Verdict.UNPROVEN: "bold cyan",
    Verdict.NOT_APPLICABLE: "dim",
}
VERDICT_ICON = {
    Verdict.OPTIMAL: "✓",
    Verdict.IMPROVABLE: "▲",
    Verdict.BEYOND_TWO_LEVEL: "◆",
    Verdict.UNPROVEN: "?",
    Verdict.NOT_APPLICABLE: "–",
}
SEVERITY_STYLE = {"error": "bold red", "warning": "yellow", "info": "cyan"}


def msg(m: Msg, lang: str) -> str:
    return t(m.key, lang, **m.params)


def verdict_label(v: Verdict, lang: str) -> str:
    return t(f"verdict.{v.value}", lang)


def form_label(form: Form | None, lang: str) -> str:
    """'МДНФ · NAND-NAND' style label."""
    if form is None:
        return "—"
    tech = "NAND-NAND" if form is Form.SOP else "NOR-NOR"
    return f"{term(form_term(form.value), lang)} · {tech}"


def tech_label(tech: str | None, lang: str) -> str:
    if not tech:
        return "—"
    return t(f"tech.{tech}", lang)


def cover_formulas(cover: Cover | None, style: str = "unicode") -> list[tuple[str, str]]:
    """``[(output, formula), ...]``."""
    if cover is None:
        return []
    return [(o, to_text(cover_to_expr(cubes, cover.inputs, cover.form), style)) for o, cubes in cover.terms.items()]


def derivations(cover: Cover | None, style: str = "ascii") -> list[list[str]]:
    """NAND/NOR derivation lines per output."""
    if cover is None:
        return []
    return [render_derivation(d, style) for d in derive_cover(cover)]


def verdict_sentence(g: GroupReport, lang: str) -> str:
    """One sentence explaining the verdict of a group with its numbers."""
    fr = g.form_result(g.verdict_form)
    ref = fr.reference.short() if fr and fr.reference else "?"
    drawn = g.structural.short() if g.structural else "?"
    nandnor = g.structural.nandnor_short() if g.structural else "?"
    s, o = g.structural, fr.reference if fr else None
    params = {"drawn": drawn, "nandnor": nandnor, "optimum": ref, "form": form_label(g.verdict_form, lang),
              "gates": g.delta.gates if g.delta else 0, "inputs": g.delta.inputs if g.delta else 0,
              "cg": s.nandnor_gates if s else "?", "ci": s.nandnor_inputs if s else "?",
              "og": o.gates if o else "?", "oi": o.inputs if o else "?"}
    return t(f"verdict.{g.verdict.value}.explain", lang, **params)


def derivation_legend(form: Form, lang: str) -> str:
    """What ↑ / ↓ mean in the rewritten formulas."""
    return t("ui.legend.sop" if form is Form.SOP else "ui.legend.pos", lang)


def robustness_text(fr: FormResult, lang: str) -> str:
    """Plain-language summary of the robustness check (empty when it was not run)."""
    if not fr.robustness:
        return ""
    if fr.robust_identical:
        parts = [t("rob.identical", lang)]
    else:
        items = []
        for line in fr.robustness:
            name, _, value = line.partition(": ")
            key = f"rob.obj.{name}"
            if template(key, lang) != key:
                items.append(f"{t(key, lang)} {value}")
        parts = [t("rob.differs", lang) + (": " + ", ".join(items) if items else "")]
    if fr.min_negators:
        parts.append(t("rob.min_negators", lang, count=fr.min_negators))
    return "; ".join(parts)


def best_form(g: GroupReport) -> FormResult | None:
    """FormResult to present: the verdict form, else the cheapest proven form."""
    fr = g.form_result(g.verdict_form)
    if fr is not None:
        return fr
    proven = [f for f in g.forms if f.reference is not None]
    pool = proven or [f for f in g.forms if f.best_cost is not None]
    return min(pool, key=lambda f: (f.best_cost.gates, f.best_cost.inputs)) if pool else None  # type: ignore[union-attr]


def overall_line(report: Report, lang: str) -> str:
    v = report.overall
    return f"{VERDICT_ICON[v]} {verdict_label(v, lang)}"


__all__ = [
    "SEVERITY_STYLE",
    "VERDICT_ICON",
    "VERDICT_STYLE",
    "best_form",
    "cover_formulas",
    "derivation_legend",
    "derivations",
    "form_label",
    "msg",
    "overall_line",
    "robustness_text",
    "tech_label",
    "verdict_label",
    "verdict_sentence",
]
