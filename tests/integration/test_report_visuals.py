"""Pictures in the HTML and Markdown reports: K-maps, timing diagram, state graph."""

from __future__ import annotations

from pathlib import Path

from cli_support import CONVERTER, SPEC, Cli

PY = ("--backend", "python")
FSM = str(Path(__file__).resolve().parents[1] / "fixtures" / "gen" / "moore_fsm.circ")


def test_html_report_draws_kmaps_as_svg(cli: Cli, tmp_path: Path) -> None:
    out = tmp_path / "r.html"
    cli(*PY, "--lang", "en", "report", CONVERTER, "--spec", SPEC, "-f", "html", "-o", str(out), "--no-image")
    html = out.read_text(encoding="utf-8")
    assert html.count('<figure class="kmap"><svg') >= 8
    assert '<aside class="toc">' in html and 'class="facts"' in html
    assert "━━" not in html  # no text-art bars left over


def test_html_report_has_timing_and_state_graph(cli: Cli, tmp_path: Path) -> None:
    out = tmp_path / "fsm.html"
    cli(*PY, "--lang", "en", "report", FSM, "--input", "0110100", "-f", "html", "-o", str(out), "--no-image")
    html = out.read_text(encoding="utf-8")
    assert '<svg class="timing"' in html and 'aria-label="state graph"' in html
    assert "<th>x=0</th><th>x=1</th>" in html


def test_markdown_report_has_mermaid_graph_and_collapsible_tables(cli: Cli, tmp_path: Path) -> None:
    out = tmp_path / "fsm.md"
    cli(*PY, "--lang", "en", "report", FSM, "--input", "0110100", "-f", "md", "-o", str(out))
    md = out.read_text(encoding="utf-8")
    assert "```mermaid\nstateDiagram-v2" in md and "[*] --> S0" in md
    assert "| State | x=0 | x=1 | Output |" in md

    out = tmp_path / "conv.md"
    cli(*PY, "--lang", "en", "report", CONVERTER, "--spec", SPEC, "-f", "md", "-o", str(out))
    md = out.read_text(encoding="utf-8")
    assert md.count("<details>") == md.count("</details>") >= 2
