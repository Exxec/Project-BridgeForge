"""Raid scenario mod (ROADMAP item 73, G6): install the rig-only `bf_raid` mod, point it at a market, and read its BF-RAID lines.

The mod (`probe-mod/raid-mod/bf_raid`) is the one BridgeForge test mod allowed Nexerelin classes (it depends on `nexerelin`). It creates
one `NexRaidIntel` against the market named in its `data/config/bf_raid.json` and logs `raid-start` and `raid-end`. That turns "raid path
unobserved" (ROADMAP items 56 and 58: Avesta's raid never happened in the live runs) into a test.

Run (needs the game; nothing here starts it):
  python -c "from bridgeforge.raid_run import install_raid_mod as i; i('In operation/_rig', target_market='exipirated_avestamarket', attacker_faction='hegemony')"
then  python -m bridgeforge probe-group install <N>  (any group that enables Nexerelin) and  probe-group live <TESTID>.
Check the log:  raid_run.check_raid_log(parse_raid_log(text)).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from bridgeforge.probe.probe_mod_build import ProbeModBuildError, _core_classpath, _find_javac, _janino_check, _run_javac
from .safeio import atomic_write_text, safe_rmtree

RAID_MOD_ID = "bf_raid"
RAID_SOURCE = Path(__file__).resolve().parent.parent / "probe-mod" / "raid-mod" / RAID_MOD_ID
RAID_CONFIG_RELATIVE = Path("data") / "config" / "bf_raid.json"
RAID_CLASSES = ("data.scripts.bfraid.BfRaidPlugin", "data.scripts.bfraid.BfRaidScript")
NEXERELIN_JAR_RELATIVE = Path("jars") / "ExerelinCore.jar"
LOG_TAG = "BF-RAID|"
END_STATES = ("raid-end", "raid-timeout", "error", "idle")


def raid_config(target_market: str, from_market: str = "", attacker_faction: str = "", fleet_points: float = 120.0,
                organize_days: float = 2.0, start_after_days: float = 3.0, max_days: float = 120.0, force_spawn: bool = False) -> dict[str, object]:
    """The config the mod reads. A raid needs a target and a source: `from_market`, or an `attacker_faction` whose largest market is used."""
    if not target_market:
        raise ValueError("a raid needs a target market id")
    if not from_market and not attacker_faction:
        raise ValueError("a raid needs from_market or attacker_faction")
    return {"targetMarket": target_market, "fromMarket": from_market, "attackerFaction": attacker_faction, "fleetPoints": fleet_points,
            "organizeDays": organize_days, "startAfterDays": start_after_days, "maxDays": max_days, "forceSpawn": force_spawn}


def install_raid_mod(rig: Path | str, target_market: str, from_market: str = "", attacker_faction: str = "", source: Path = RAID_SOURCE,
                     **options: object) -> Path:
    """Copy the raid mod into the rig's mods folder, write its config, and enable it beside what is enabled. Nexerelin must be enabled too."""
    rig = Path(rig)
    if not (rig / "starsector-core").exists():
        raise ValueError(f"{rig} is not a rig")
    config = raid_config(target_market, from_market, attacker_faction, **options)  # type: ignore[arg-type]
    target = rig / "mods" / "bf-raid"
    if target.exists():
        safe_rmtree(target, [rig / "mods"])
    shutil.copytree(source, target)
    atomic_write_text(target / RAID_CONFIG_RELATIVE, json.dumps(config, indent=1))
    enabled_path = rig / "mods" / "enabled_mods.json"
    data = json.loads(enabled_path.read_text(encoding="utf-8")) if enabled_path.is_file() else {}
    enabled = [m for m in data.get("enabledMods", []) if isinstance(m, str)]
    if "nexerelin" not in enabled:
        raise ValueError("Nexerelin is not enabled in the rig; the raid mod needs it (enable the group first)")
    if RAID_MOD_ID not in enabled:
        enabled.append(RAID_MOD_ID)
    atomic_write_text(enabled_path, json.dumps({"enabledMods": enabled}))
    return target


def parse_raid_log(text: str) -> list[dict[str, str]]:
    """One dict per BF-RAID line: `event` (the first field) and every key=value after it; a free-text field lands in `detail`."""
    rows = []
    for line in text.splitlines():
        if LOG_TAG not in line:
            continue
        parts = line.split(LOG_TAG, 1)[1].strip().split("|")
        row = {"event": parts[0]}
        for item in parts[1:]:
            key, sep, value = item.partition("=")
            if sep:
                row[key] = value
            else:
                row["detail"] = item
        rows.append(row)
    return rows


def check_raid_log(rows: list[dict[str, str]]) -> tuple[str, str]:
    """(verdict, reason): RAID_OBSERVED when a raid started and ended, RAID_STARTED when it started but did not end in the run,
    RAID_NOT_STARTED with the mod's own reason otherwise. A raid that ended with an error is RAID_NOT_STARTED."""
    start = next((r for r in rows if r["event"] == "raid-start"), None)
    if start is None:
        why = next((r.get("detail", r["event"]) for r in rows if r["event"] in ("error", "idle")), "no BF-RAID line in the log")
        return "RAID_NOT_STARTED", why
    end = next((r for r in rows if r["event"] in ("raid-end", "raid-timeout")), None)
    if end is None:
        return "RAID_STARTED", f"raid on {start.get('target', '?')} started and the log stops before it ended"
    if end["event"] == "raid-timeout":
        return "RAID_STARTED", f"raid on {start.get('target', '?')} did not end within the mod's maxDays (outcome {end.get('outcome', '?')})"
    return "RAID_OBSERVED", f"raid on {start.get('target', '?')} ended: {end.get('outcome', '?')} after {end.get('days', '?')} days"


def nexerelin_jar(mods_dir: Path | str) -> Path | None:
    """The newest Nexerelin jar under a mods folder (read-only use as a compile classpath entry), or None."""
    found = sorted(Path(mods_dir).glob("Nexerelin*/" + NEXERELIN_JAR_RELATIVE.as_posix()))
    return found[-1] if found else None


def check_raid_mod(jdk_dir: Path | str, core_dir: Path | str, nexerelin: Path | str, work_dir: Path, source: Path = RAID_SOURCE) -> dict[str, object]:
    """Compile the mod's scripts with javac (API mistakes) and with the game's Janino (what the game does) against RC8 core plus
    Nexerelin's jar. Nothing is written beside the sources. Result: {'javac': 'PASS', 'janino': 'PASS' | 'FAIL' | 'UNAVAILABLE', 'error': ...}."""
    nexerelin = Path(nexerelin)
    if not nexerelin.is_file():
        raise ProbeModBuildError(f"{nexerelin} not found; pass Nexerelin's jars/ExerelinCore.jar")
    javac = _find_javac(Path(jdk_dir))
    classpath = f"{_core_classpath(Path(core_dir))};{nexerelin}"
    scripts_root = Path(source) / "data" / "scripts" / "bfraid"
    sources = sorted(scripts_root.glob("*.java"))
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        _run_javac(javac, classpath, sources, work_dir / "classes")
    except ProbeModBuildError as exc:
        return {"javac": "FAIL", "janino": "SKIPPED", "error": str(exc)}
    status, error = _janino_check(javac, Path(core_dir), classpath, Path(source), ",".join(RAID_CLASSES), work_dir)
    return {"javac": "PASS", "janino": status, "error": error}


def main_check(jdk_dir: str, core_dir: str, mods_dir: str, work_dir: str) -> int:  # pragma: no cover - thin CLI for local builds
    jar = nexerelin_jar(mods_dir)
    if jar is None:
        print(f"no Nexerelin jar under {mods_dir}")
        return 2
    result = check_raid_mod(jdk_dir, core_dir, jar, Path(work_dir))
    print(json.dumps(result, indent=1))
    return 0 if result["javac"] == "PASS" and result["janino"] == "PASS" else 1


__all__ = ["RAID_MOD_ID", "RAID_SOURCE", "check_raid_log", "check_raid_mod", "install_raid_mod", "nexerelin_jar", "parse_raid_log", "raid_config"]
_ = subprocess  # keep the import local to this module's build helpers
