"""Probe 0.3.2 inputs: MagicLib bounties to spawn and entity state to confirm (2026-10-22).

- `bounty_ids`: every bounty id in the mod's `data/config/modFiles/magicBounty_data.json` (MagicLib's file; top-level keys),
  capped, for the probe's `bounty` stage. EPTA's narcepolis faction exists for the Artifact 667 bounty; its generic patrol is
  empty by design, so the bounty fleet is what shows the faction works.
- `entity_checks`: owner-approved expectations from the candidate workspace's `PROBE_EXPECTATIONS.json`
  (`{"entity_checks": [{"entity": id, "expect": {...}} | {"custom_entity_spec": id, "expect": {...}}]}`), for the probe's
  `entity-state` stage: what a person would otherwise check by eye (Zorg's planets not hidden, EPTA's station sprite).
"""
from __future__ import annotations

from pathlib import Path

from bridgeforge.scanner import _load_lenient_json_file

BOUNTY_FILE = Path("data") / "config" / "modFiles" / "magicBounty_data.json"
EXPECTATIONS_FILE = "PROBE_EXPECTATIONS.json"
MAX_BOUNTIES = 20
ENTITY_KEYS = {"discoverable", "has_sensor_profile", "detected_range_bonuses", "market_hidden", "market_size", "market_faction"}
SPEC_KEYS = {"sprite", "sprite_width", "sprite_height"}


def bounty_ids(mod_root: Path) -> list[str]:
    data = _load_lenient_json_file(Path(mod_root) / BOUNTY_FILE) if (Path(mod_root) / BOUNTY_FILE).is_file() else None
    if not isinstance(data, dict):
        return []
    return sorted(key for key, value in data.items() if isinstance(value, dict))[:MAX_BOUNTIES]


def expectations_path(mod_root: Path) -> Path:
    """The workspace's file (beside working/), never inside the shipped mod."""
    mod_root = Path(mod_root)
    return (mod_root.parent if mod_root.name == "working" else mod_root) / EXPECTATIONS_FILE


def entity_checks(mod_root: Path) -> list[dict]:
    """Validated checks; raises ValueError naming the first malformed one (a typo must not pass silently)."""
    path = expectations_path(mod_root)
    if not path.is_file():
        return []
    data = _load_lenient_json_file(path)
    checks = data.get("entity_checks") if isinstance(data, dict) else None
    if not isinstance(checks, list):
        raise ValueError(f"{path}: expected {{\"entity_checks\": [...]}}")
    for index, check in enumerate(checks):
        kind = "entity" if isinstance(check, dict) and "entity" in check else "custom_entity_spec"
        allowed = ENTITY_KEYS if kind == "entity" else SPEC_KEYS
        expect = check.get("expect") if isinstance(check, dict) else None
        if not isinstance(check, dict) or not isinstance(check.get(kind), str) or not isinstance(expect, dict) or not expect:
            raise ValueError(f"{path}: entity_checks[{index}] needs a string 'entity' or 'custom_entity_spec' and a non-empty 'expect'")
        unknown = sorted(set(expect) - allowed)
        if unknown:
            raise ValueError(f"{path}: entity_checks[{index}] has unknown expect keys {unknown}; allowed {sorted(allowed)}")
    return checks
