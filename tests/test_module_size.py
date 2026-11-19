"""96.5 A6: no package module grows past the 800-line soft ceiling unless it is listed here, and a listed one never grows."""
from __future__ import annotations

import unittest
from pathlib import Path

import tests.support  # noqa: F401  installs the registry guard when this module runs alone (96.5 C4)

PACKAGE = Path(__file__).resolve().parent.parent / "bridgeforge"
CEILING = 800
# Modules over CEILING on 2026-11-18, each with the most lines it may have. Lower a number when the module shrinks and
# remove the entry once it is under CEILING; never raise one or add a module: split it instead (ROADMAP-3 96.5 A6 split
# behavior_discovery, probe_group, translation and dossier, then 1,274, 1,115, 1,086 and 1,076 lines).
OVER_CEILING = {"revive.py": 884}


def _line_counts() -> dict[str, int]:
    return {path.relative_to(PACKAGE).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
            for path in sorted(PACKAGE.rglob("*.py"))}


class ModuleSizeTests(unittest.TestCase):
    def test_no_module_grows_past_its_ceiling(self) -> None:
        over = {name: lines for name, lines in _line_counts().items() if lines > OVER_CEILING.get(name, CEILING)}
        self.assertEqual(over, {}, f"split these modules (soft ceiling {CEILING} lines; listed ones may not grow)")

    def test_a_listed_cap_follows_its_module_down(self) -> None:
        # A cap left above a module that shrank would let it grow back; so each cap is the module's current length.
        counts = _line_counts()
        under = sorted(name for name in OVER_CEILING if counts.get(name, 0) <= CEILING)
        self.assertEqual(under, [], "remove these from OVER_CEILING: they are under the ceiling now")
        stale = {name: counts[name] for name, cap in OVER_CEILING.items() if name in counts and CEILING < counts[name] < cap}
        self.assertEqual(stale, {}, "lower these caps in OVER_CEILING to the module's length")


if __name__ == "__main__":
    unittest.main()
