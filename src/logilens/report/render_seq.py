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
from logilens.report.svg import state_graph_svg, timing_svg


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
        cols = next_columns(data, lang)
        header = [t("seq.state", lang), *cols, t("seq.out", lang)]
        out += [f"#### {_cap(term('transition_table', lang))}", "", "| " + " | ".join(header) + " |",
                "|" + "---|" * len(header)]
        for r in rows:
            nxt = list(map(str, r.get("next", [])))
            cells = nxt if len(cols) == len(nxt) else [" ".join(nxt)]
            out.append(f"| **{r.get('name')}** | " + " | ".join(f"`{c}`" for c in cells)
                       + f" | `{' '.join(map(str, r.get('outputs', [])))}` |")
        out.append("")
    mermaid = mermaid_graph(data.get("fsm") or {})
    if mermaid:
        out += [f"#### {t('seq.graph', lang)}", "", "```mermaid", mermaid, "```", ""]
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
        width = len(rows[0].get("next", []))
        cols = next_columns(data, lang)
        head = "".join(f"<th>{escape(c)}</th>" for c in cols)
        body = ""
        for r in rows:
            nxt = list(map(str, r.get("next", [])))
            cells = "".join(f"<td><code>{escape(v)}</code></td>" for v in (nxt if len(cols) == width else [" ".join(nxt)]))
            body += (f"<tr><td><b>{escape(str(r.get('name')))}</b></td>{cells}"
                     f"<td><code>{escape(' '.join(map(str, r.get('outputs', []))))}</code></td></tr>")
        out.append(f"<h4>{escape(_cap(term('transition_table', lang)))}</h4><div class='scroll'><table><thead><tr>"
                   f"<th>{escape(t('seq.state', lang))}</th>{head}"
                   f"<th>{escape(t('seq.out', lang))}</th></tr></thead><tbody>{body}</tbody></table></div>")
    timing = data.get("timing") or {}
    if timing.get("states"):
        fsm = data.get("fsm") or {}
        picture = timing_svg(timing, fsm.get("inputs") or [], fsm.get("outputs") or [], t("seq.state", lang))
        out.append(f"<h4>{escape(t('seq.timing', lang))}</h4><div class='scroll'>{picture}</div>")
    graph = state_graph_svg(data.get("fsm") or {})
    if graph:
        out.append(f"<h4>{escape(t('seq.graph', lang))}</h4><div class='graph'>{graph}</div>")
    if data.get("dot"):
        out.append(f"<details><summary>Graphviz (.dot)</summary><pre>{escape(data['dot'])}</pre></details>")
    return "".join(out)


def next_columns(data: dict[str, Any], lang: str) -> list[str]:
    """Headers of the next-state columns: one per input combination (x=0, x=1, ...) when they line up."""
    rows = ((data.get("analysis") or {}).get("table") or {}).get("rows") or []
    inputs = (data.get("fsm") or {}).get("inputs") or []
    width = len(rows[0].get("next", [])) if rows else 0
    if inputs and width == 2 ** len(inputs):
        return [f"{''.join(inputs)}={k:0{len(inputs)}b}" for k in range(width)]
    return [t("seq.next", lang)] if width else []


def mermaid_graph(fsm: dict[str, Any]) -> str:
    """State graph as a Mermaid ``stateDiagram-v2`` (GitHub renders it in Markdown)."""
    transitions = fsm.get("transitions") or []
    if not transitions:
        return ""
    moore = fsm.get("kind") == "moore"
    ids = {s.get("code", ""): f"S{k}" for k, s in enumerate(fsm.get("states") or [])}
    names = {s.get("code", ""): s.get("name") or s.get("code", "") for s in fsm.get("states") or []}
    lines = ["stateDiagram-v2", "    direction LR"]
    outs: dict[str, str] = {}
    edges: dict[tuple[str, str], list[str]] = {}
    for tr in transitions:
        out = "".join(map(str, tr.get("outputs") or []))
        outs.setdefault(tr["state"], out)
        label = str(tr.get("input", "")) if moore else f"{tr.get('input', '')}/{out}"
        edges.setdefault((tr["state"], tr["next"]), []).append(label)
    for code, sid in ids.items():
        text = f"{names[code]} / {outs[code]}" if moore and code in outs else names[code]
        lines.append(f'    state "{text}" as {sid}')
    if fsm.get("initial") in ids:
        lines.append(f"    [*] --> {ids[fsm['initial']]}")
    for (a, b), labels in edges.items():
        if a in ids and b in ids:
            lines.append(f"    {ids[a]} --> {ids[b]} : {','.join(labels)}")
    return "\n".join(lines)
