"""Automation tiers: how far each scan finding can go without a person or an AI (ROADMAP P15, 2026-09-26).

The tiers live in `automation_tiers.json`, one per finding id. `finding-stats` uses them to say how many
mods could be revived unattended; `revive` uses them to decide what it applies and what it turns into
an escalation packet. The hardest tier among a mod's findings is the mod's bucket.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

TIERS_PATH = Path(__file__).with_name("automation_tiers.json")
# Easiest first. A mod's bucket is the hardest tier among its findings.
TIER_ORDER = ("none", "auto", "mechanical", "input", "decision", "inspect", "code", "unclassified")
ACTIONABLE = frozenset(TIER_ORDER) - {"none"}


@lru_cache(maxsize=1)
def _table() -> tuple[dict[str, str], tuple[tuple[re.Pattern, str], ...]]:
    data = json.loads(TIERS_PATH.read_text(encoding="utf-8"))
    exact, patterns = {}, []
    for key, tier in data["findings"].items():
        if tier not in TIER_ORDER:
            raise ValueError(f"automation_tiers.json: '{key}' has unknown tier '{tier}'")
        if "{...}" in key:
            patterns.append((re.compile("^" + ".+".join(map(re.escape, key.split("{...}"))) + "$"), tier))
        else:
            exact[key] = tier
    return exact, tuple(patterns)


def tier_descriptions() -> dict[str, str]:
    return json.loads(TIERS_PATH.read_text(encoding="utf-8"))["tiers"]


def tier_for(finding_id: str) -> str:
    exact, patterns = _table()
    if finding_id in exact:
        return exact[finding_id]
    for pattern, tier in patterns:
        if pattern.match(finding_id):
            return tier
    return "unclassified"


def tiered_ids() -> set[str]:
    """Every id key in the table, `{...}` patterns included (for the completeness test)."""
    return set(json.loads(TIERS_PATH.read_text(encoding="utf-8"))["findings"])


def bucket(tiers: list[str]) -> str:
    """The hardest tier present, or 'none' when nothing needs doing."""
    return max(tiers, key=TIER_ORDER.index, default="none")
