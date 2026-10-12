"""Pilot tests of the interactive TUI (Python backend unless marked ``java``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import DataTable, Input, OptionList, Select
from tui_support import CONVERTER, DRAFT, MOORE, SPEC, run_app, text_of, wait_analysis, wait_until

from logilens.tui.app import LogilensApp
from logilens.tui.i18n import STRINGS, tr
from logilens.tui.recent import MAX_RECENT, RecentFiles
from logilens.tui.screens.help import HelpScreen
from logilens.tui.screens.main import TAB_IDS, MainScreen
from logilens.tui.screens.picker import CircTree, PickerScreen, find_specs
from logilens.tui.widgets import export as export_mod
from logilens.tui.widgets.fsm import FsmView

# ------------------------------------------------------------------ pure helpers


def test_strings_have_same_keys_in_every_language() -> None:
    keys = set(STRINGS["en"])
    assert set(STRINGS["ru"]) == keys and set(STRINGS["sk"]) == keys


def test_tr_falls_back_to_shared_catalog() -> None:
    assert tr("tab.issues", "ru") == "Проблемы"
    assert tr("verdict.optimal", "en") == "OPTIMAL"  # from the shared TOML catalog


def test_recent_files_dedupe_limit_and_corruption(tmp_path: Path) -> None:
    store = RecentFiles(tmp_path / "cfg" / "recent.json")
    assert store.load() == []
    for k in range(MAX_RECENT + 5):
        f = tmp_path / f"c{k}.circ"
        f.write_text("x")
        store.add(f)
    store.add(tmp_path / "c3.circ", tmp_path / "s.spec.txt")
    entries = store.load()
    assert len(entries) == MAX_RECENT
    assert Path(entries[0].path).name == "c3.circ" and entries[0].spec and entries[0].spec.endswith("s.spec.txt")
    assert sum(Path(e.path).name == "c3.circ" for e in entries) == 1
    store.path.write_text("{not json", encoding="utf-8")
    assert store.load() == []


def test_find_specs(tmp_path: Path) -> None:
    (tmp_path / "a.spec.txt").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "t.csv").write_text("")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "h.tsv").write_text("")
    names = {p.name for p in find_specs(tmp_path)}
    assert names == {"a.spec.txt", "t.csv"}


# ------------------------------------------------------------------ main screen


def test_converter_optimal_tabs_and_empty_issues(make_app: Any) -> None:
    app = make_app(CONVERTER, SPEC)

    async def body(app: LogilensApp, pilot: Any) -> None:
        screen = await wait_analysis(app, pilot)
        assert screen.error is None
        assert "ОПТИМАЛЬНО" in text_of(app, "#verdict-badge")
        assert "converter.spec.txt" in text_of(app, "#file-info")
        assert "19/48" in text_of(app, "#overview-body") and "18/45" in text_of(app, "#overview-body")
        tabs = screen.query_one("#tabs")
        for k, tab_id in enumerate(TAB_IDS, 1):
            await pilot.press(str(k))
            await pilot.pause()
            expected = "minimize" if tab_id == "fsm" else tab_id  # combinational: FSM tab hidden
            assert tabs.active == expected
        await pilot.press("2")
        await pilot.pause()
        empty = screen.query_one("#issues-empty")
        assert empty.display and text_of(app, "#issues-empty").strip() == tr("issues.empty", "ru")
        assert not screen.query_one("#issues-table", DataTable).display
        truth = screen.query_one("#truth-table", DataTable)
        assert truth.row_count == 32 and len(truth.columns) == 1 + 5 + 8
        kmap = text_of(app, "#kmap-body")
        assert "A_N" in kmap and "ilp" in kmap
        assert "ilp" in text_of(app, "#minimize-body")
        # SOP/POS toggle switches the map of the same output
        await pilot.press("4")
        await pilot.pause()
        panel = screen.query_one("#kmap-panel")
        panel.set_mode("pos")
        await pilot.pause()
        assert "(POS)" in text_of(app, "#kmap-body") or "МКНФ" in text_of(app, "#kmap-body")

    run_app(app, body)
    entries = RecentFiles(app.recent.path).load()
    assert entries and Path(entries[0].path).name == CONVERTER.name and entries[0].spec


def test_draft_issues_table_has_l011_and_l001(make_app: Any) -> None:
    app = make_app(DRAFT, only="nand,nor")

    async def body(app: LogilensApp, pilot: Any) -> None:
        screen = await wait_analysis(app, pilot)
        await pilot.press("2")
        await pilot.pause()
        table = screen.query_one("#issues-table", DataTable)
        assert table.display and table.row_count > 0
        rules = {str(table.get_row_at(r)[1]) for r in range(table.row_count)}
        assert {"L011", "L001"} <= rules
        assert sum(str(table.get_row_at(r)[1]) == "L011" for r in range(table.row_count)) == 10
        assert "МОЖНО ЛУЧШЕ" in text_of(app, "#verdict-badge")
        # the detail panel follows the cursor
        table.focus()
        l001 = next(r for r in range(table.row_count) if str(table.get_row_at(r)[1]) == "L001")
        table.move_cursor(row=l001)
        await pilot.pause()
        detail = text_of(app, "#issue-detail")
        assert "L001" in detail and "(420,770)" in detail and "→" in detail
        # gate set "any" -> re-run without L011
        screen.query_one("#gate-set", Select).value = ""
        await wait_until(pilot, lambda: screen.only is None and screen.report is not None
                         and not screen.query_one("#tabs").loading)
        rules = {i.rule for i in screen.report.lint.issues}
        assert "L011" not in rules and "L001" in rules

    run_app(app, body)


def test_moore_fsm_tab_and_timing_resimulation(make_app: Any) -> None:
    app = make_app(MOORE)

    async def body(app: LogilensApp, pilot: Any) -> None:
        screen = await wait_analysis(app, pilot)
        assert screen.report.is_sequential
        await pilot.press("6")
        await pilot.pause()
        assert screen.query_one("#tabs").active == "fsm"
        data = screen.report.seq.data
        assert len(data["fsm"]["states"]) == 4
        fsm_text = text_of(app, "#fsm-body")
        for code in ("00", "01", "10", "11"):
            assert f"→ {code}" in fsm_text or f"  {code}" in fsm_text
        assert "──1──▶" in fsm_text  # state graph
        inp = screen.query_one("#timing-input", Input)
        inp.focus()
        await pilot.press(*"0110100")
        await pilot.press("enter")
        view = screen.query_one(FsmView)
        await wait_until(pilot, lambda: view.timing is not None or view.timing_error is not None)
        await pilot.pause()
        assert view.timing_error is None
        # default naming = state codes; S0=10, S1=00, S2=01, S3=11 (see tests/seq/test_seq_moore.py)
        assert view.timing.trace == "00 00 01 11 11 10 10 10"
        names = {"10": "S0", "00": "S1", "01": "S2", "11": "S3"}
        assert " ".join(names[s] for s in view.timing.trace.split()) == "S1 S1 S2 S3 S3 S0 S0 S0"
        assert "trace" in text_of(app, "#timing-body")
        view.simulate("01x")
        await wait_until(pilot, lambda: view.timing_error is not None)
        await pilot.pause()
        assert "bad input step" in text_of(app, "#timing-body") and view.timing is None

    run_app(app, body)


def test_export_md_html_json_next_to_circuit(make_app: Any, workdir: Path, monkeypatch: Any) -> None:
    opened: list[Path] = []
    monkeypatch.setattr(export_mod, "open_in_browser", opened.append)
    circ = workdir / CONVERTER.name
    app = make_app(circ, workdir / SPEC.name)

    async def body(app: LogilensApp, pilot: Any) -> None:
        screen = await wait_analysis(app, pilot)
        await pilot.press("7")
        await pilot.pause()
        await pilot.click("#export-md")
        await pilot.pause()
        md = workdir / "converter_nand_nor.report.md"
        assert md.is_file() and "converter_nand_nor.circ" in md.read_text(encoding="utf-8")
        assert str(md) in text_of(app, "#export-log")
        await pilot.click("#export-json")
        await pilot.pause()
        data = json.loads((workdir / "converter_nand_nor.report.json").read_text(encoding="utf-8"))
        assert data["schema"].startswith("logilens/report")
        await pilot.press("1")
        await pilot.press("e")  # export HTML from any tab
        await pilot.pause()
        html = workdir / "converter_nand_nor.report.html"
        assert html.is_file() and screen.query_one("#tabs").active == "report"
        await pilot.click("#export-open")
        await pilot.pause()
        assert opened == [html]

    run_app(app, body)


def test_broken_file_shows_friendly_error(make_app: Any, tmp_path: Path) -> None:
    bad = tmp_path / "broken.circ"
    bad.write_text("<project><circuit name='main'><comp", encoding="utf-8")
    app = make_app(bad, lang="en")

    async def body(app: LogilensApp, pilot: Any) -> None:
        screen = await wait_analysis(app, pilot)
        assert screen.error is not None and screen.report is None
        panel = screen.query_one("#error-panel")
        assert panel.display and not screen.query_one("#tabs").display
        text = text_of(app, "#error-panel")
        assert "broken.circ" in text and "Traceback" not in text and tr("error.hint", "en") in text
        await pilot.press("o")  # back to the picker
        await pilot.pause()
        assert isinstance(app.screen, PickerScreen)

    run_app(app, body)


def test_help_theme_and_quit(make_app: Any) -> None:
    app = make_app(CONVERTER, lang="en")

    async def body(app: LogilensApp, pilot: Any) -> None:
        await wait_analysis(app, pilot)
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        assert "switch tab" in text_of(app, "#help-body")
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)
        theme = app.theme
        await pilot.press("t")
        await pilot.pause()
        assert app.theme != theme
        await pilot.press("q")
        await pilot.pause()

    run_app(app, body)
    assert app.return_code == 0


# ------------------------------------------------------------------ picker


def test_picker_recent_filter_spec_and_open(make_app: Any, workdir: Path, tmp_path: Path) -> None:
    recent = RecentFiles(tmp_path / "config" / "recent.json")
    recent.add(workdir / DRAFT.name)
    app = make_app(cwd=workdir)

    async def body(app: LogilensApp, pilot: Any) -> None:
        assert isinstance(app.screen, PickerScreen)
        picker = app.screen
        options = picker.query_one("#recent-list", OptionList)
        assert options.option_count == 1
        spec_select = picker.query_one("#spec", Select)
        assert str(workdir / SPEC.name) in [v for _, v in spec_select._options]  # discovered in cwd
        tree = picker.query_one("#tree", CircTree)
        picker.query_one("#filter", Input).value = "nand_nor"
        await pilot.pause(0.3)
        assert tree.filter_text == "nand_nor"
        names = [p.name for p in tree.filter_paths(workdir.iterdir())]
        assert names == [CONVERTER.name]
        spec_select.value = str((workdir / SPEC.name).resolve())
        picker.open_path(workdir / CONVERTER.name)
        screen = await wait_analysis(app, pilot)
        assert screen.spec and screen.spec.endswith(SPEC.name)
        assert screen.report.spec is not None and screen.report.spec.passed
        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, PickerScreen)
        assert picker.query_one("#recent-list", OptionList).option_count == 2
        # Enter on a recent entry opens it
        options = picker.query_one("#recent-list", OptionList)
        options.focus()
        options.highlighted = 1
        await pilot.press("enter")
        screen = await wait_analysis(app, pilot)
        assert screen.path.name == DRAFT.name

    run_app(app, body)


# ------------------------------------------------------------------ CLI entry point


def test_cli_launches_tui_only_on_a_terminal(monkeypatch: Any) -> None:
    from typer.testing import CliRunner

    from logilens.cli import app as cli_app

    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr("logilens.tui.run_tui",
                        lambda *a, **kw: calls.append((a, kw)))
    runner = CliRunner()
    result = runner.invoke(cli_app.app, ["--lang", "en", "--no-tui"])
    assert result.exit_code == 0 and "doctor" in result.stdout and not calls
    monkeypatch.setattr(cli_app, "interactive", lambda: True)
    result = runner.invoke(cli_app.app, ["--lang", "sk", "--backend", "python", str(CONVERTER), "--spec", str(SPEC),
                                         "--only", "nand,nor"])
    assert result.exit_code == 0, result.output
    (args, kw), = calls
    assert args == (str(CONVERTER), str(SPEC)) and kw == {"lang": "sk", "backend": "python", "jar": None,
                                                         "only": "nand,nor"}
    result = runner.invoke(cli_app.app, [])
    assert result.exit_code == 0 and calls[-1][0] == (None, None)


@pytest.mark.java
def test_java_backend_converter_optimal(make_app: Any) -> None:
    app = make_app(CONVERTER, SPEC, backend="java", lang="en")

    async def body(app: LogilensApp, pilot: Any) -> None:
        screen = await wait_analysis(app, pilot)
        assert screen.report is not None and screen.report.backend == "java"
        assert "OPTIMAL" in text_of(app, "#verdict-badge")

    run_app(app, body)
