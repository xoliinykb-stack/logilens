"""Rendering of the sequential-analysis section from its JSON-like dict (``SeqResult.to_dict()``).

Works on plain data so the report model stays serializable; unknown/missing keys are skipped gracefully.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from html import escape
from typing import Any

from rich import box
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from logilens.i18n import t
from logilens.i18n.glossary import term


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _join(items: Any) -> str:
    if isinstance(items, (list, tuple)):
        return ", ".join(str(x) for x in items) or "—"
    return "—" if items in (None, "") else str(items)


def _ff_counts(kinds: Any) -> str:
    """``['D', 'D', 'JK']`` -> ``'D ×2, JK'`` (one entry per state variable in the data)."""
    if not isinstance(kinds, (list, tuple)) or not kinds:
        return _join(kinds)
    counts = Counter(str(k) for k in kinds)
    return ", ".join(k if n == 1 else f"{k} ×{n}" for k, n in counts.items())


def summary_rows(data: dict[str, Any], lang: str) -> list[tuple[str, str]]:
    fsm = data.get("fsm") or {}
    an = data.get("analysis") or {}
    mini = data.get("minimization") or {}
    kind = fsm.get("kind", "")
    rows = [
        (t("seq.kind", lang), term(kind, lang) if kind in ("moore", "mealy") else _join(kind)),
        (_cap(term("flip_flop", lang)), (f"{_ff_counts(fsm.get('ff_kinds'))} · {t('seq.state_vars', lang)}: "
                                  f"{_join(fsm.get('state_vars'))}")),
        (t("seq.io", lang), f"{_join(fsm.get('inputs'))} → {_join(fsm.get('outputs'))}"),
        (t("seq.clock", lang), _join(fsm.get("clock_sources"))),
        (t("seq.initial", lang), _join(fsm.get("initial_name") or fsm.get("initial"))),
        (t("seq.reachable", lang), (f"{len(an.get('reachable') or [])} · {t('seq.unreachable', lang)}: "
                                   f"{_join(an.get('unreachable'))}")),
    ]
    if an.get("dead_ends") or an.get("traps"):
        rows.append((t("seq.dead_ends", lang), f"{_join(an.get('dead_ends'))} / {_join(an.get('traps'))}"))
    if mini:
        key = "seq.minimal" if mini.get("is_minimal") else "seq.not_minimal"
        rows.append((t("seq.minimization", lang), t(key, lang, original=mini.get("original_count"),
                                                    minimal=mini.get("minimal_count"))))
    return rows


def transition_table(data: dict[str, Any], lang: str) -> Table | None:
    fsm = data.get("fsm") or {}
    table_data = (data.get("analysis") or {}).get("table") or {}
    rows = table_data.get("rows") or []
    if not rows:
        return None
    cols = table_data.get("columns") or []
    xname = "".join(fsm.get("inputs") or []) or "x"
    title = f"{_cap(term('transition_table', lang))} ({term(fsm.get('kind', ''), lang)})"
    table = Table(title=title, title_justify="left", title_style="bold", box=box.ROUNDED, min_width=len(title) + 2)
    table.add_column(t("seq.state", lang), style="bold")
    for x in cols:
        table.add_column(f"{xname}={x}" if x else t("seq.next", lang), justify="center")
    yname = ",".join(fsm.get("outputs") or []) or "y"
    mealy = fsm.get("kind") == "mealy"
    for x in (cols if mealy else [None]):
        table.add_column(f"{yname} ({xname}={x})" if x is not None else yname, justify="center", style="green")
    for r in rows:
        label = ("→ " if r.get("state") == fsm.get("initial") else "  ") + str(r.get("name", r.get("state")))
        cells = [Text(label, style="" if r.get("reachable", True) else "dim")]
        cells += [str(v) for v in r.get("next", [])] + [str(v) for v in r.get("outputs", [])]
        table.add_row(*cells)
    return table


def encodings_table(data: dict[str, Any], lang: str) -> Table | None:
    encs = data.get("encodings") or []
    if not encs:
        return None
    table = Table(title=t("seq.encodings", lang), title_justify="left", title_style="bold", box=box.SIMPLE_HEAD)
    table.add_column(t("seq.encoding", lang), style="bold")
    table.add_column(t("seq.codes", lang))
    table.add_column(t("seq.cost", lang))
    table.add_column(t("ui.note", lang), style="dim")
    for e in encs:
        codes = ", ".join(f"{k}→{v}" for k, v in (e.get("codes") or {}).items())
        costs = "; ".join(f"{c.get('ff')}: {c.get('gates')}/{c.get('inputs')}{'' if c.get('proven') else '?'}"
                          for c in e.get("costs") or [] if c.get("gates") is not None)
        table.add_row(str(e.get("name")), codes, costs or e.get("skipped") or "—", _join(e.get("notes")))
    return table


def renderables(data: dict[str, Any] | None, lang: str) -> Iterator[RenderableType]:
    """Rich renderables of the sequential section."""
    if not data:
        return
    if not data.get("applicable", True):
        yield Text(t("seq.not_applicable", lang, reason=data.get("reason", "")), style="yellow")
        return
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column()
    for k, v in summary_rows(data, lang):
        grid.add_row(k, v)
    yield Panel(grid, border_style="cyan", box=box.ROUNDED)
    for part in (transition_table(data, lang), encodings_table(data, lang)):
        if part is not None:
            yield part
    timing = data.get("timing") or {}
    if timing.get("diagram"):
        yield Panel(Text(timing["diagram"]), title=t("seq.timing", lang), title_align="left", border_style="grey50")
    notes = list((data.get("analysis") or {}).get("notes") or []) + list(data.get("warnings") or [])
    if notes:
        yield Text("\n".join("• " + n for n in notes), style="dim")


def markdown(data: dict[str, Any] | None, lang: str) -> list[str]:
    if not data:
        return []
    if not data.get("applicable", True):
        return [t("seq.not_applicable", lang, reason=data.get("reason", "")), ""]
    out = [f"- **{k}**: {v}" for k, v in summary_rows(data, lang)] + [""]
    rows = ((data.get("analysis") or {}).get("table") or {}).get("rows") or []
    if rows:
        out += [f"#### {_cap(term('transition_table', lang))}", "", "| " + t("seq.state", lang) + " | "
                + t("seq.next", lang) + " | " + t("seq.out", lang) + " |", "|---|---|---|"]
        out += [f"| {r.get('name')} | {' '.join(map(str, r.get('next', [])))} | "
                f"{' '.join(map(str, r.get('outputs', [])))} |" for r in rows]
        out.append("")
    timing = data.get("timing") or {}
    if timing.get("diagram"):
        out += [f"#### {t('seq.timing', lang)}", "", "```", timing["diagram"], "```", ""]
    return out


def html(data: dict[str, Any] | None, lang: str) -> str:
    if not data:
        return ""
    if not data.get("applicable", True):
        return f"<p class='muted'>{escape(t('seq.not_applicable', lang, reason=data.get('reason', '')))}</p>"
    kv = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in summary_rows(data, lang))
    out = [f"<dl class='kv'>{kv}</dl>"]
    rows = ((data.get("analysis") or {}).get("table") or {}).get("rows") or []
    if rows:
        body = "".join(f"<tr><td>{escape(str(r.get('name')))}</td><td>{escape(' '.join(map(str, r.get('next', []))))}"
                       f"</td><td>{escape(' '.join(map(str, r.get('outputs', []))))}</td></tr>" for r in rows)
        out.append(f"<h4>{escape(_cap(term('transition_table', lang)))}</h4><table><thead><tr>"
                   f"<th>{escape(t('seq.state', lang))}</th><th>{escape(t('seq.next', lang))}</th>"
                   f"<th>{escape(t('seq.out', lang))}</th></tr></thead><tbody>{body}</tbody></table>")
    timing = data.get("timing") or {}
    if timing.get("diagram"):
        out.append(f"<h4>{escape(t('seq.timing', lang))}</h4><pre>{escape(timing['diagram'])}</pre>")
    if data.get("dot"):
        out.append(f"<details><summary>Graphviz</summary><pre>{escape(data['dot'])}</pre></details>")
    return "".join(out)
