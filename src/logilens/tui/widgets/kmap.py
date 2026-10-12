"""«Карты Карно» tab: output selector, MDNF / MKNF / as-drawn toggle, colored K-map with a legend."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Label, RadioButton, RadioSet, Select, Static

from logilens.core.logic_types import Cover, Form, KMapView
from logilens.i18n.glossary import form_term, term
from logilens.kmap.render_text import render_rich as kmap_table
from logilens.logic.expr import cube_to_expr, to_text
from logilens.report.model import GroupReport, Report
from logilens.report.text import cover_formulas, form_label
from logilens.tui.i18n import tr

MODES = ("sop", "pos", "impl")


def legend(view: KMapView, others: list[KMapView], lang: str) -> Text:
    """Colored legend: label chip, cube, expression and the other outputs sharing the same term."""
    text = Text(tr("kmap.legend", lang) + "\n", style="bold")
    for g in view.groups:
        shared = [o.output for o in others if o.output != view.output and any(h.cube == g.cube for h in o.groups)]
        expr = to_text(cube_to_expr(g.cube, view.variables, view.form), "unicode")
        text.append(f" {g.label} ", style=f"bold reverse {g.color}")
        text.append(f"  {g.cube}  ", style="dim")
        text.append(expr, style=g.color)
        if shared:
            text.append(f"   ↔ {', '.join(shared)}", style="italic")
        text.append("\n")
    if not view.groups:
        text.append("—\n", style="dim")
    return text


def kmap_renderable(view: KMapView, cover: Cover | None, others: list[KMapView], caption: str,
                    lang: str) -> RenderableType:
    formula = dict(cover_formulas(cover)).get(view.output, "")
    head = Text.assemble((view.output, "bold"), (" = " + formula if formula else "", "bold cyan"))
    table = kmap_table(view)
    table.caption = None
    table.title = None
    return Group(head, Text(caption, style="dim"), table, legend(view, others, lang))


class KMapPanel(Vertical):
    def __init__(self, lang: str, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.lang = lang
        self.report: Report | None = None
        self.mode = "sop"

    def compose(self) -> ComposeResult:
        lang = self.lang
        with Horizontal(classes="controls"):
            yield Label(tr("kmap.output", lang), classes="control-label")
            yield Select([], id="kmap-output", allow_blank=True, prompt="—")
            yield Label(tr("kmap.form", lang), classes="control-label")
            with RadioSet(id="kmap-form"):
                yield RadioButton(term(form_term("SOP"), lang), id="form-sop", value=True)
                yield RadioButton(term(form_term("POS"), lang), id="form-pos")
                yield RadioButton(tr("kmap.implemented", lang), id="form-impl")
        with VerticalScroll(classes="pane-scroll"):
            yield Static("", id="kmap-body")

    # ------------------------------------------------------------- data
    def _group_of(self, output: str) -> GroupReport | None:
        if self.report is None:
            return None
        return next((g for g in self.report.groups if output in g.outputs), None)

    def outputs(self) -> list[tuple[str, str]]:
        if self.report is None:
            return []
        return [(f"{o}  · {tr('kmap.group_of', self.lang, index=g.index)}", o)
                for g in self.report.groups for o in g.outputs]

    def show(self, report: Report) -> None:
        self.report = report
        select = self.query_one("#kmap-output", Select)
        options = self.outputs()
        select.set_options(options)
        if not options:
            self.query_one("#kmap-body", Static).update(Text(tr("kmap.none", self.lang), style="yellow"))
            return
        first = options[0][1]
        g = self._group_of(first)
        mode = "pos" if g is not None and g.verdict_form is Form.POS else "sop"
        self.set_mode(mode, refresh=False)
        select.value = first
        self.refresh_map()

    def set_mode(self, mode: str, refresh: bool = True) -> None:
        self.mode = mode
        button = self.query_one(f"#form-{mode}", RadioButton)
        if not button.value:
            button.value = True
        if refresh:
            self.refresh_map()

    def current(self) -> tuple[KMapView | None, Cover | None, list[KMapView], str]:
        select = self.query_one("#kmap-output", Select)
        output = select.value if isinstance(select.value, str) else None
        g = self._group_of(output) if output else None
        if g is None or output is None:
            return None, None, [], ""
        if self.mode == "impl":
            views, cover = list(g.implemented_kmaps), g.implemented_cover
            caption = f"{tr('kmap.implemented', self.lang)} · {form_label(g.implemented_form, self.lang)}"
            if g.implemented_cost is not None:
                caption += f" · {g.implemented_cost.short()}"
        else:
            fr = g.form_result(Form.SOP if self.mode == "sop" else Form.POS)
            if fr is None:
                return None, None, [], ""
            views, cover = list(fr.kmaps), fr.best_cover
            key = "ui.optimal_cover" if fr.proven else "ui.best_cover"
            caption = tr(key, self.lang, form=form_label(fr.form, self.lang),
                         cost=fr.best_cost.short() if fr.best_cost else "?", method=fr.best_method or "?")
        view = next((v for v in views if v.output == output), None)
        return view, cover, views, caption

    def refresh_map(self) -> None:
        body = self.query_one("#kmap-body", Static)
        if self.report is None:
            return
        if not self.report.groups:
            body.update(Text(tr("kmap.none", self.lang), style="yellow"))
            return
        view, cover, views, caption = self.current()
        if view is None:
            body.update(Text(tr("kmap.missing", self.lang), style="yellow"))
            return
        body.update(kmap_renderable(view, cover, views, caption, self.lang))

    # ------------------------------------------------------------- events
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "kmap-output":
            event.stop()
            self.refresh_map()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id != "kmap-form":
            return
        event.stop()
        button_id = event.pressed.id or "form-sop"
        mode = button_id.removeprefix("form-")
        if mode in MODES and mode != self.mode:
            self.mode = mode
            self.refresh_map()


__all__ = ["KMapPanel", "kmap_renderable", "legend"]
