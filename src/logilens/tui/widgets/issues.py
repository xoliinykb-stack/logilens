"""«Проблемы» tab: gate-set selector, lint issues table (severity colors) and a detail panel."""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import DataTable, Label, Select, Static

from logilens.i18n import issue_fix, issue_message, t
from logilens.lint.issue import LintIssue
from logilens.report.model import Report
from logilens.report.text import SEVERITY_STYLE
from logilens.tui.i18n import tr

GATE_SETS = (("", "issues.gate_any"), ("nand", "issues.gate_nand"), ("nor", "issues.gate_nor"),
             ("nand,nor", "issues.gate_both"))


def _where(issue: LintIssue) -> str:
    return issue.component or (str(issue.loc) if issue.loc else issue.circuit)


def issue_detail(issue: LintIssue, lang: str) -> Group:
    sev = issue.severity.value
    head = Text.assemble((f" {t(f'severity.{sev}', lang)} ", SEVERITY_STYLE[sev] + " reverse"), " ",
                         (issue.rule, "bold"), ("  ·  " + _where(issue), "cyan"))
    body = Text(issue_message(issue, lang), style="bold")
    fix = Text.assemble(("→ ", "green"), (issue_fix(issue, lang), "green"))
    where = Text(style="dim")
    if issue.loc is not None:
        where.append(f"{tr('issues.location', lang)}: {issue.loc}   ")
    if issue.component:
        where.append(f"{tr('issues.component', lang)}: {issue.component}   ")
    where.append(f"{tr('issues.circuit', lang)}: {issue.circuit}")
    if issue.related:
        where.append(f"   {tr('issues.related', lang)}: " + ", ".join(str(p) for p in issue.related[:8]))
    return Group(head, body, fix, where)


class IssuesView(Vertical):
    """Lint issues of the current report."""

    class GateSetChanged(Message):
        def __init__(self, only: str | None) -> None:
            super().__init__()
            self.only = only

    def __init__(self, lang: str, only: str | None, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.lang = lang
        self.only = only or None
        self.issues: list[LintIssue] = []

    def compose(self) -> ComposeResult:
        with Horizontal(classes="controls"):
            yield Label(tr("issues.gate_set", self.lang), classes="control-label")
            yield Select([(tr(key, self.lang), value) for value, key in GATE_SETS], value=self.only or "",
                         allow_blank=False, id="gate-set")
            yield Static("", id="issues-count")
        yield Static("", id="issues-empty", classes="empty-state")
        yield DataTable(id="issues-table", cursor_type="row", zebra_stripes=True)
        yield Static(Text(tr("issues.hint", self.lang), style="dim"), id="issue-detail")

    def show(self, report: Report) -> None:
        lang = self.lang
        self.only = report.lint.only or None
        self.issues = sorted(report.lint.issues, key=lambda i: i.severity.rank)
        empty = self.query_one("#issues-empty", Static)
        table = self.query_one("#issues-table", DataTable)
        detail = self.query_one("#issue-detail", Static)
        counts = self.query_one("#issues-count", Static)
        table.clear(columns=True)
        if not self.issues:
            empty.update(Text(tr("issues.empty", lang)))
            empty.display = True
            table.display = False
            detail.display = False
            counts.update("")
            return
        empty.display = False
        table.display = True
        detail.display = True
        problems = [i for i in self.issues if i.is_problem]
        counts.update(Text(("✗ " if problems else "✓ ") + t(
            "ui.lint_counts", lang, errors=sum(i.severity.value == "error" for i in self.issues),
            warnings=sum(i.severity.value == "warning" for i in self.issues),
            infos=len(self.issues) - len(problems)), style="bold red" if problems else "bold green"))
        msg_width = max(30, (self.size.width or 100) - 44)
        table.add_column(t("ui.severity", lang), key="sev", width=9)
        table.add_column(t("ui.rule", lang), key="rule", width=5)
        table.add_column(t("ui.where", lang), key="where", width=22)
        table.add_column(t("ui.problem", lang), key="msg", width=msg_width)
        for k, issue in enumerate(self.issues):
            sev = issue.severity.value
            table.add_row(Text(t(f"severity.{sev}", lang), style=SEVERITY_STYLE[sev]), Text(issue.rule, style="bold"),
                          Text(_where(issue), style="cyan"), issue_message(issue, lang), key=str(k))
        table.move_cursor(row=0)
        detail.update(issue_detail(self.issues[0], lang))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "issues-table" or event.row_key is None or event.row_key.value is None:
            return
        issue = self.issues[int(event.row_key.value)]
        self.query_one("#issue-detail", Static).update(issue_detail(issue, self.lang))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "gate-set":
            return
        event.stop()
        value = event.value if isinstance(event.value, str) and event.value else None
        if value != self.only:
            self.only = value
            self.post_message(self.GateSetChanged(value))


__all__ = ["IssuesView", "issue_detail"]
