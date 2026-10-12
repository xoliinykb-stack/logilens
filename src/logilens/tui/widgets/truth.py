"""«Таблица истинности» tab: one column per input / output; cells that contradict the spec are red."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from logilens.report.model import Report
from logilens.tui.i18n import tr

MAX_ROWS = 4096
VALUE_STYLE = {"1": "bold", "0": "dim", "X": "yellow", "x": "yellow", "E": "bold red", "U": "magenta"}


def mismatch_cells(report: Report) -> dict[tuple[str, str], str]:
    """``(input bits, circuit output) -> expected value`` for every spec mismatch."""
    if report.spec is None:
        return {}
    return {(str(m["inputs"]).replace(" ", ""), str(m["label"])): str(m["expected"]) for m in report.spec.mismatches}


class TruthView(Vertical):
    def __init__(self, lang: str, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.lang = lang

    def compose(self) -> ComposeResult:
        yield Static("", id="truth-info")
        yield DataTable(id="truth-table", zebra_stripes=True, cursor_type="row")

    def show(self, report: Report) -> None:
        lang = self.lang
        info = self.query_one("#truth-info", Static)
        table = self.query_one("#truth-table", DataTable)
        table.clear(columns=True)
        truth = report.truth
        if truth is None:
            info.update(Text(tr("truth.none", lang), style="yellow"))
            table.display = False
            return
        table.display = True
        bad = mismatch_cells(report)
        text = Text(tr("truth.rows", lang, rows=len(truth.rows), inputs=" ".join(truth.inputs),
                       outputs=" ".join(truth.outputs)), style="dim")
        if truth.tied:
            tied = "; ".join(f"{k} ← {', '.join(v)}" for k, v in truth.tied.items())
            text.append("\n" + tr("truth.tied", lang, tied=tied), style="dim")
        if report.spec is not None:
            ok = not report.spec.mismatches
            text.append("\n" + ("✓ " if ok else "✗ ") + tr("truth.legend", lang),
                        style="green" if ok else "bold red")
        if len(truth.rows) > MAX_ROWS:
            text.append("\n" + tr("truth.truncated", lang, shown=MAX_ROWS, total=len(truth.rows)), style="yellow")
        info.update(text)
        table.add_column("#", key="#")
        for name in truth.inputs:
            table.add_column(Text(name, style="bold cyan"), key="in:" + name)
        for name in truth.outputs:
            table.add_column(Text(name, style="bold"), key="out:" + name)
        for k, (bits, outs) in enumerate(truth.rows[:MAX_ROWS]):
            cells: list[Text] = [Text(str(k), style="dim")]
            cells += [Text(b, style="cyan") for b in bits]
            row_bad = False
            for name, value in zip(truth.outputs, outs):
                expected = bad.get((bits, name))
                if expected is not None:
                    row_bad = True
                    cells.append(Text(f"{value}≠{expected}", style="bold white on red"))
                else:
                    cells.append(Text(value, style=VALUE_STYLE.get(value, "")))
            if row_bad:
                cells[0] = Text(f"{k} ✗", style="bold red")
            table.add_row(*cells, key=str(k))


__all__ = ["TruthView", "mismatch_cells"]
