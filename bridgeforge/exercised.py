"""What a live probe run exercised, per mod (ROADMAP item 75 R1, "what was exercised").

The probe tallies, per mod id, how many items each stage touched and logs at the end one line per mod:
`BF-PROBE|<ver>|exercised|mod=<id>|hulls_built=3,variants_resolved=0,...,combat_ships=2`. `probe-group record` keeps the parsed map in the
run record (`exercised`). A mod whose counts are all zero ran through a PASS without anything of its own being looked at: HOLLOW, a
warning for the owner to read, never a failure. A log without exercised lines (older probe) gives no map and flags nothing.
"""
from __future__ import annotations

import re

_LINE = re.compile(r"BF-PROBE\|[^|\r\n]*\|exercised\|mod=([^|\r\n]+)\|([^|\r\n]*)")
_COUNT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(\d+)$")
HOLLOW = "HOLLOW"


def parse_exercised(log_text: str) -> dict[str, dict[str, int]]:
    """{mod id: {stage: count}}. The probe repeats the lines (campaign end, combat end); the highest count per stage wins. Malformed
    counts are skipped, never guessed."""
    found: dict[str, dict[str, int]] = {}
    for mod, body in _LINE.findall(log_text):
        stages = found.setdefault(mod.strip(), {})
        for part in body.split(","):
            match = _COUNT.match(part.strip())
            if match:
                stages[match[1]] = max(stages.get(match[1], 0), int(match[2]))
    return found


def hollow_mods(exercised: dict[str, dict[str, int]], mod_ids: list[str] | None = None) -> list[str]:
    """Mods (limited to `mod_ids` when given) with an exercised line whose counts are all zero, sorted."""
    return sorted(mod for mod, stages in exercised.items() if (mod_ids is None or mod in mod_ids) and not any(stages.values()))


def hollow_warnings(hollow: list[str]) -> list[str]:
    return [f"{HOLLOW}: {mod} passed but the probe exercised none of its content (every stage count is 0)" for mod in hollow]
