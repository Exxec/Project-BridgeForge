"""Generic New Game fallback for `live_run` (ROADMAP item 73 G1): page by page, read the screen, click, check the page changed.

The default, Ironclads and Nexerelin flows are fixed click lists measured on one layout each. A total conversion with a New Game screen
of its own stops the default flow on that page (the intended LIVE_STUCK). This loop continues from whatever page is up: it looks for a
teal confirm button in the lower right (`screen_read.confirm_button`), clicks it, and otherwise clicks the first selectable option row
(the measured positions of the first row of RC8's dialog, wide text first). A click that leaves the page unchanged moves on to the next
option row; a page that stays unchanged through every row (a loading screen, or a page this loop cannot read) ends the loop. Every page's
screenshot is kept so a stuck run can be read afterwards. Unproven in the game until a live run starts two total conversions with it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .safeio import atomic_write_bytes
from .screen_read import Bitmap, confirm_button, page_fingerprint, pages_differ

# First option row of RC8's New Game dialog: wide text (x 0.40), short text (0.30), the middle (0.50). live_run's FIRST_CHOICE,
# DIFFICULTY_NORMAL and IRONCLADS_SKILLS_AUTOMATIC, measured 2026-10-11 at y 0.618.
OPTION_ROWS: tuple[tuple[float, float], ...] = ((0.40, 0.618), (0.30, 0.618), (0.50, 0.618))
DEFAULT_MAX_PAGES = 12
PAGE_PAUSE_SECONDS = 4.0


@dataclass(frozen=True)
class PageStep:
    page: int
    action: str  # confirm | row | unreadable | stuck | done
    point: tuple[float, float] | None = None
    changed: bool | None = None  # did the previous click change the page (None on the first page)
    shot: str | None = None


def run_pages(click: Callable[[float, float], None], sleep: Callable[[float], None], capture: Callable[[], Bitmap | None],
              done: Callable[[], bool], max_pages: int = DEFAULT_MAX_PAGES, pause: float = PAGE_PAUSE_SECONDS,
              shots_dir: Path | None = None) -> list[PageStep]:
    """Click through New Game pages until `done()` (the campaign probe's log line), `max_pages`, or a page that will not change."""
    steps: list[PageStep] = []
    previous = None
    last_action = ""
    row = 0
    unchanged = 0
    for page in range(1, max_pages + 1):
        if done():
            steps.append(PageStep(page, "done"))
            break
        bitmap = capture()
        if bitmap is None:
            steps.append(PageStep(page, "unreadable"))
            break
        shot = None
        if shots_dir is not None:
            target = Path(shots_dir) / f"page-{page:02d}.bmp"
            atomic_write_bytes(target, bitmap.data)
            shot = str(target)
        fingerprint = page_fingerprint(bitmap)
        changed = None if previous is None else pages_differ(previous, fingerprint)
        previous = fingerprint
        if changed is False:
            unchanged += 1
            row = row + 1 if last_action == "row" else row
        else:
            unchanged = 0
        if unchanged > len(OPTION_ROWS):
            steps.append(PageStep(page, "stuck", None, changed, shot))
            break
        button = confirm_button(bitmap)
        if button is not None and not (changed is False and last_action == "confirm"):
            action, point = "confirm", button
        else:
            action, point = "row", OPTION_ROWS[row % len(OPTION_ROWS)]
        steps.append(PageStep(page, action, point, changed, shot))
        click(*point)
        sleep(pause)
        last_action = action
    return steps
