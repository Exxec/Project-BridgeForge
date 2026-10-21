"""The probe's `salvor` profile (ROADMAP-3 item 78.5): the marker file that selects it and the log lines it emits.

Salvor's `rig-build-probe` builds this probe and drops `marker_text()` at `MARKER_RELATIVE` inside the built mod folder. The Java side
(`SalvorProfile.java`) reads the same file; `tests/test_probe_salvor_profile.py` keeps the two in step. Nothing here is written by
BridgeForge's own builds, so the profile is never active in a normal probe.
"""
from __future__ import annotations

import json
from pathlib import Path

from .safeio import atomic_write_text

PROFILE_NAME = "salvor"
PROBE_MOD_ID = "bridgeforge_probe"
MARKER_RELATIVE = "data/config/bf_probe_profile.json"
MODE_PROPERTY = "salvor.rig.mode"
DAYS_PROPERTY = "salvor.rig.days"
# The line shapes Salvor's rig_auto parses (its regexes), with <ts>/<n> standing for numbers.
LOG_LINES = (
    "salvor-rig|INFO|load|newGame=<bool>|ts=<ts>",
    "salvor-rig|INFO|days|<n>",
    "salvor-rig|INFO|save|requested",
    "salvor-rig|INFO|save|done|ts=<ts>",
    "salvor-rig|INFO|session|complete",
)


def marker_text() -> str:
    return json.dumps({"profile": PROFILE_NAME}) + "\n"


def write_marker(mod_dir: Path) -> Path:
    """Select the salvor profile in a built probe mod folder (never in the repo's own `probe-mod`)."""
    target = Path(mod_dir) / MARKER_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, marker_text())
    return target
