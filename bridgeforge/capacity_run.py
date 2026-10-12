"""Capacity-overage evidence (ROADMAP item 57): install the rig-only capacity mod, read its BF-CAP lines, and check the rules they showed.

The mod (`probe-mod/capacity-mod/bf_capacity`) walks three player fleets through cargo, fuel and crew at 0 to 2 times capacity and logs the
fleet's travel speed and daily supplies. The rules below were read from the 2026-10-12 run (CAP2-20261012, docs/RC8_BEHAVIOUR.md RC8-34
to RC8-36); `check_rules` holds any later log, for example on another game build, to them.

Run:  python -c "from bridgeforge.capacity_run import install_capacity_mod as i; i('In operation/_rig')"
then  python -m bridgeforge probe-group install <N>  (any group, for the probe and the rig marker) and  probe-group live <TESTID>.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .safeio import atomic_write_text, safe_rmtree

CAPACITY_MOD_ID = "bf_capacity"
CAPACITY_SOURCE = Path(__file__).resolve().parent.parent / "probe-mod" / "capacity-mod" / CAPACITY_MOD_ID

EXCESS_COST_PER_UNIT = 0.1  # supplies per day per unit over capacity, for cargo space, fuel and personnel separately
EXCESS_COST_CAP = 50.0      # per resource
SPEED_PER_BURN_LEVEL = 20.0
MIN_BURN_LEVEL = 1


def install_capacity_mod(rig: Path | str, source: Path = CAPACITY_SOURCE) -> Path:
    """Copy the capacity mod into the rig's mods folder and enable it beside what is enabled."""
    rig = Path(rig)
    if not (rig / "starsector-core").exists():
        raise ValueError(f"{rig} is not a rig")
    target = rig / "mods" / "bf-capacity"
    if target.exists():
        safe_rmtree(target, [rig / "mods"])
    shutil.copytree(source, target)
    enabled_path = rig / "mods" / "enabled_mods.json"
    data = json.loads(enabled_path.read_text(encoding="utf-8")) if enabled_path.is_file() else {}
    enabled = [m for m in data.get("enabledMods", []) if isinstance(m, str)]
    if CAPACITY_MOD_ID not in enabled:
        enabled.append(CAPACITY_MOD_ID)
    atomic_write_text(enabled_path, json.dumps({"enabledMods": enabled}))
    return target


def parse_capacity_log(text: str) -> list[dict[str, str]]:
    """One dict per fleet state: fleet, state and every key=value the mod logged. START, END and SAVE lines are not states."""
    rows = []
    for line in text.splitlines():
        if "BF-CAP|" not in line:
            continue
        parts = line.split("BF-CAP|", 1)[1].strip().split("|")
        if parts[0] in ("START", "END", "SAVE") or len(parts) < 3:
            continue
        row = {"fleet": parts[0], "state": parts[1]}
        for item in parts[2:]:
            key, _, value = item.partition("=")
            row[key] = value
        rows.append(row)
    return rows


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def check_rules(rows: list[dict[str, str]]) -> list[str]:
    """Every state that breaks a rule, as text; empty when all hold.

    1. Excess supply cost per resource = min(50, 0.1 x units over capacity); suppliesPerDay = the fleet's base + the three costs.
    2. Travel speed = 20 x max(1, round(base burn x (2 - r))), r the largest of used/capacity over cargo, fuel and personnel when above 1.
    """
    problems = []
    base_speed: dict[str, float] = {}
    for row in rows:
        if row["state"].startswith("built"):
            base_speed[row["fleet"]] = float(row["travelSpeed"])
    for row in rows:
        if row["state"].startswith("built") or row["fleet"] not in base_speed:
            continue
        used = (float(row["spaceUsed"]), float(row["fuel"]), float(row["crew"]))
        capacity = (float(row["maxCargo"]), float(row["maxFuel"]), float(row["maxPersonnel"]))
        costs = (float(row["excessCargoCost"]), float(row["excessFuelCost"]), float(row["excessPersonnelCost"]))
        label = f'{row["fleet"]} {row["state"]}'
        for name, u, c, cost in zip(("cargo", "fuel", "personnel"), used, capacity, costs):
            expected = min(EXCESS_COST_CAP, EXCESS_COST_PER_UNIT * max(0.0, u - c))
            if abs(cost - expected) > 0.011:
                problems.append(f"{label}: {name} excess cost {cost} but {expected:.2f} expected")
        ratio = max(u / c for u, c in zip(used, capacity) if c > 0)
        base_burn = base_speed[row["fleet"]] / SPEED_PER_BURN_LEVEL
        burn = base_burn if ratio <= 1.0 else max(MIN_BURN_LEVEL, _round_half_up(base_burn * (2.0 - ratio)))
        expected_speed = burn * SPEED_PER_BURN_LEVEL
        if abs(float(row["travelSpeed"]) - expected_speed) > 0.5:
            problems.append(f"{label}: speed {row['travelSpeed']} but {expected_speed:.0f} expected (ratio {ratio:.2f})")
    return problems
