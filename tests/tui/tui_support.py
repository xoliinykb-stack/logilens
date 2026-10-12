"""Shared helpers of the Textual pilot tests (no pytest-asyncio: every test drives its own event loop)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from logilens.tui.app import LogilensApp
from logilens.tui.screens.main import MainScreen
from logilens.tui.widgets.common import plain_text

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONVERTER = FIXTURES / "converter_nand_nor.circ"
DRAFT = FIXTURES / "converter_draft.circ"
SPEC = FIXTURES / "converter.spec.txt"
MOORE = FIXTURES / "gen" / "moore_fsm.circ"
SIZE = (100, 30)


def text_of(app: LogilensApp, selector: str) -> str:
    """Plain text of a Static's content on the current screen."""
    return plain_text(app.screen.query_one(selector).content)


async def wait_until(pilot: Any, predicate: Callable[[], bool], timeout: float = 60.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError("timed out waiting for the TUI")
        await pilot.pause(0.05)


async def wait_analysis(app: LogilensApp, pilot: Any) -> MainScreen:
    def done() -> bool:
        s = app.main_screen
        return bool(s is not None and s.is_mounted and (s.report is not None or s.error is not None)
                    and not s.query_one("#tabs").loading)

    await wait_until(pilot, done)
    await pilot.pause()
    screen = app.main_screen
    assert screen is not None
    return screen


def run_app(app: LogilensApp, body: Callable[[LogilensApp, Any], Awaitable[None]]) -> None:
    async def main() -> None:
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await body(app, pilot)

    asyncio.run(main())


