"""Read the game window's pixels to find buttons, so clicks do not depend on one measured layout (ROADMAP 65m).

One 2026-10-11 session found the main menu laid out with rows 28 px apart where earlier sessions had 23, and a fixed click at the
measured "Missions" position fell between two buttons (DUEL14-20261011). The capture covers only the game window's client area
(game_click.capture_client), is saved as a BMP and parsed here without any imaging library.
"""
from __future__ import annotations

import struct
from pathlib import Path


class Bitmap:
    """A 24- or 32-bit uncompressed BMP, as System.Drawing writes it."""

    def __init__(self, data: bytes) -> None:
        if data[:2] != b"BM":
            raise ValueError("not a BMP")
        offset = struct.unpack_from("<I", data, 10)[0]
        width, height = struct.unpack_from("<ii", data, 18)
        bpp = struct.unpack_from("<H", data, 28)[0]
        if bpp not in (24, 32):
            raise ValueError(f"unsupported BMP depth {bpp}")
        self.width, self.height = width, abs(height)
        self.bottom_up = height > 0
        self.step = bpp // 8
        self.row = (width * self.step + 3) & ~3
        self.data = data
        self.offset = offset

    @classmethod
    def load(cls, path: Path) -> "Bitmap":
        return cls(Path(path).read_bytes())

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        """(r, g, b) at x, y counted from the top left."""
        row = (self.height - 1 - y) if self.bottom_up else y
        i = self.offset + row * self.row + x * self.step
        b, g, r = self.data[i], self.data[i + 1], self.data[i + 2]
        return r, g, b


def is_button_fill(r: int, g: int, b: int) -> bool:
    """RC8's teal button fill (main menu, mission list buttons): blue and green well above red, mid brightness."""
    return b >= 70 and g >= 55 and b - r >= 35 and g - r >= 20 and r <= 110 and (r + g + b) <= 520


def bands(flags: list[bool], min_len: int, max_gap: int = 1) -> list[tuple[int, int]]:
    """Runs of True at least `min_len` long, bridging gaps of up to `max_gap` (text inside a button breaks the fill)."""
    found: list[tuple[int, int]] = []
    start = None
    gap = 0
    for i, flag in enumerate(flags + [False] * (max_gap + 1)):
        if flag:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > max_gap:
                end = i - gap
                if end - start + 1 >= min_len:
                    found.append((start, end))
                start, gap = None, 0
    return found


def main_menu_buttons(bitmap: Bitmap) -> list[tuple[float, float]]:
    """Centres of the main menu's buttons as client fractions, top to bottom. The menu sits right of centre; a few columns are sampled
    and the column with the most button rows wins."""
    best: list[tuple[int, int]] = []
    best_x = 0
    for fx in (0.66, 0.68, 0.70, 0.72):
        x = int(bitmap.width * fx)
        flags = [is_button_fill(*bitmap.pixel(x, y)) for y in range(int(bitmap.height * 0.25), int(bitmap.height * 0.80))]
        found = [(s + int(bitmap.height * 0.25), e + int(bitmap.height * 0.25)) for s, e in bands(flags, max(4, bitmap.height // 120), 3)]
        if len(found) > len(best):
            best, best_x = found, x
    return [(best_x / bitmap.width, (s + e) / 2 / bitmap.height) for s, e in best]


def main_menu_target(buttons: list[tuple[float, float]], name: str) -> tuple[float, float] | None:
    """The button by name from the RC8 main menu order: [Continue,] Tutorials, Missions, New Game, Load Game, Codex, Settings,
    Credits, Quit. Continue is only there with a save, so the list is read from the bottom."""
    order = ["Tutorials", "Missions", "New Game", "Load Game", "Codex", "Settings", "Credits", "Quit"]
    if len(buttons) < len(order):
        return None
    tail = buttons[-len(order):]
    return tail[order.index(name)]


def _is_icon_pixel(r: int, g: int, b: int) -> bool:
    """Anything clearly brighter than the list's dark background: the mission thumbnails."""
    return r + g + b >= 90


def list_rows(bitmap: Bitmap, x_from: float = 0.235, x_to: float = 0.28, y_from: float = 0.2, y_to: float = 0.8) -> list[float]:
    """Centres (client fractions) of the mission list's rows, read from the column of thumbnails on the left of each row."""
    best: list[tuple[int, int]] = []
    top = int(bitmap.height * y_from)
    for step in range(6):
        x = int(bitmap.width * (x_from + (x_to - x_from) * step / 5))
        flags = [_is_icon_pixel(*bitmap.pixel(x, y)) for y in range(top, int(bitmap.height * y_to))]
        found = bands(flags, max(6, bitmap.height // 40), 2)
        if len(found) > len(best):
            best = found
    return [((s + e) / 2 + top) / bitmap.height for s, e in best]
