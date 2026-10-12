"""`probe-group duel`: play the rig-only duel missions unattended and read what a destruction costs in frame time.

The missions live in `probe-mod/duel-mod/bf_duel` (SEEKER's Bone-Breaker, the glass sphere that fragments, against Betelgeuse, and a
pair of vanilla Onslaughts as the baseline). Their plugin logs `BF-DUEL|<label>|...` lines: one per real second with the frame
period and the field, one per destruction, and an END line. This module installs the mod into the rig, drives the missions from the
main menu with real clicks (live_run), and summarises the logs. Same rules as live_run: leave the mouse and keyboard alone.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import live_run as lr

DUEL_MOD_ID = "bf_duel"
DUEL_MISSIONS = ("seeker", "baseline", "overwhelm")
DUEL_SOURCE = Path(__file__).resolve().parent.parent / "probe-mod" / "duel-mod" / DUEL_MOD_ID
_LINE = re.compile(r"BF-DUEL\|(?P<label>[^|]+)\|(?P<what>[^|]+)\|(?P<detail>.*)$")
_FIELD = re.compile(r"(\w+)=(-?\d+(?:\.\d+)?)")


def install_duel_mod(rig: Path, source: Path = DUEL_SOURCE) -> Path:
    """Copy the duel mod into the rig's mods folder and enable it beside what is already enabled."""
    rig = Path(rig)
    if not (rig / "starsector-core").exists():
        raise lr.GameRefused(f"{rig} is not a rig")
    target = rig / "mods" / "bf-duel"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    # A mission's icon is read from its own folder. Vanilla's is copied in here, in the rig only, so no game file is ever committed.
    icon = rig / "starsector-core" / "data" / "missions" / "ambush" / "icon.jpg"
    for mission in (target / "data" / "missions").iterdir():
        if mission.is_dir() and icon.is_file():
            shutil.copy2(icon, mission / "icon.jpg")
    enabled_path = rig / "mods" / "enabled_mods.json"
    data = json.loads(enabled_path.read_text(encoding="utf-8")) if enabled_path.is_file() else {}
    enabled = [m for m in data.get("enabledMods", []) if isinstance(m, str)]
    if DUEL_MOD_ID not in enabled:
        enabled.append(DUEL_MOD_ID)
    enabled_path.write_text(json.dumps({"enabledMods": enabled}), encoding="utf-8")
    return target


def parse_duel_log(text: str) -> dict[str, dict]:
    """{label: {seconds: [...], destroyed: [...], costs: [...], end: {...}}} from BF-DUEL lines."""
    out: dict[str, dict] = {}
    for line in text.splitlines():
        match = _LINE.search(line)
        if not match:
            continue
        entry = out.setdefault(match["label"], {"seconds": [], "destroyed": [], "costs": [], "end": None, "side_gone": None, "fight": None})
        fields = {k: float(v) for k, v in _FIELD.findall(match["detail"])}
        what = match["what"]
        if what == "SECOND":
            entry["seconds"].append(fields)
        elif what == "FIGHT":
            entry["fight"] = fields
        elif what == "DESTROYED":
            hull = re.search(r"hull=(\S+)", match["detail"])
            entry["destroyed"].append({**fields, "hull": hull.group(1) if hull else None})
        elif what == "DESTRUCTION-COST":
            entry["costs"].append(fields)
        elif what == "END":
            entry["end"] = fields
        elif what == "SIDE-GONE":
            entry["side_gone"] = fields
    return out


def summarise(duels: dict[str, dict]) -> dict[str, dict]:
    """Per label: frame period before the first destruction and after it, the worst frame, peak hulks and ships on the field."""
    result: dict[str, dict] = {}
    for label, entry in duels.items():
        seconds = entry["seconds"]
        fight = entry.get("fight")
        first = fight["gameSeconds"] if fight else min((d["t"] for d in entry["destroyed"]), default=None)
        before = [s["avgMs"] for s in seconds if first is None or s["t"] < first]
        after = [s["avgMs"] for s in seconds if first is not None and s["t"] >= first]

        def mean(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 2) if values else None

        result[label] = {
            "seconds_logged": len(seconds),
            "first_destruction_t": first,
            "fight_game_seconds": fight["gameSeconds"] if fight else None,
            "fight_real_seconds": fight["realSeconds"] if fight else None,
            "final_frame_ms": seconds[-1]["maxMs"] if seconds else None,
            "seconds_since_kill_logged": max((s.get("sinceKill", 0) for s in seconds), default=0),
            "avg_ms_before": mean(before),
            "avg_ms_after": mean(after),
            "worst_frame_ms": max((s["maxMs"] for s in seconds), default=None),
            "worst_after_destruction_ms": max((c["worstFrameMs"] for c in entry["costs"]), default=None),
            "peak_hulks": max((s.get("hulks", 0) for s in seconds), default=0),
            "peak_ships": max((s.get("ships", 0) for s in seconds), default=0),
            "peak_projectiles": max((s.get("projectiles", 0) for s in seconds), default=0),
            "finished": entry["end"] is not None,
        }
    return result


STALL_SECONDS = 20  # per-second lines with an unchanged game time for this long: the combat clock is frozen


def capture_stall(rig: Path, test_id: str, hands, tag: str) -> list[str]:
    """Evidence of a stalled combat: three JVM thread dumps a few seconds apart (jcmd from the running java's own JDK) and a
    screenshot of the game window, written beside the log. Returns what was written."""
    import subprocess
    import time

    from . import game_click
    from .boot_test import _running_java_under

    written: list[str] = []
    logs = Path(rig) / "logs"
    for java in _running_java_under(rig):
        jcmd = Path(str(java.get("exe"))).parent / "jcmd.exe"
        if not jcmd.is_file():
            continue
        for i in range(1, 4):
            out = logs / f"{test_id}-{tag}-threads-{i}.txt"
            try:
                result = subprocess.run([str(jcmd), str(java["pid"]), "Thread.print"], capture_output=True, text=True, timeout=60)
                out.write_text(result.stdout, encoding="utf-8")
                written.append(str(out))
            except Exception:
                pass
            time.sleep(4)
        break
    try:
        geometry = hands.geometry() if hands.geometry else None
    except Exception:
        geometry = None
    if geometry is not None:
        shot = logs / f"{test_id}-{tag}.png"
        if game_click.capture_client(geometry, shot):
            written.append(str(shot))
    return written


def game_time_stalled(text: str, seconds: int = STALL_SECONDS) -> bool:
    """The last `seconds` per-second lines all report the same game time: the combat clock is frozen while frames still run."""
    times = re.findall(r"BF-DUEL\|[^|]+\|SECOND\|t=([-\d.]+)", text)
    return len(times) >= seconds and len(set(times[-seconds:])) == 1


def wait_for_end(log: Path, label: str, timeout: float, hands, rig: Path, test_id: str, since: int = 0) -> tuple[bool, list[str]]:
    """Wait for the duel's END line; when the combat clock freezes for STALL_SECONDS capture evidence once, give it 30 s more, then give up."""
    import time

    marker = f"BF-DUEL|{label}|END"
    deadline = time.monotonic() + timeout
    evidence: list[str] = []
    gave_up_at = None
    last_count, last_change = -1, time.monotonic()
    while time.monotonic() < deadline:
        text = lr._log_text(log)[since:]
        if marker in text:
            return True, evidence
        count = text.count("BF-DUEL|")
        if count != last_count:
            last_count, last_change = count, time.monotonic()
        # Two ways combat stalls: the clock freezes while frames run (a pause), or the frames stop coming (the SEEKER sphere's
        # fragments, 67 hulks in a quarter second, took the game to seconds per frame, 2026-10-11).
        silent = last_count > 0 and time.monotonic() - last_change >= STALL_SECONDS
        if not evidence and (silent or game_time_stalled(text)):
            evidence = capture_stall(rig, test_id, hands, label)
            gave_up_at = time.monotonic() + 30
        if gave_up_at and time.monotonic() > gave_up_at:
            return False, evidence
        if not hands.alive():
            return False, evidence
        hands.sleep(1.0)
    return False, evidence


def run_duel(rig: Path, test_id: str, bat_name: str = "run-j25-direct.bat", combat_timeout: float = 600, only: tuple[str, ...] | None = None) -> dict:
    """Install the duel mod, start the game, play each duel mission from the main menu, stop the game, return the summary."""
    install_duel_mod(rig)
    played: list[str] = []
    problem: str | None = None
    with lr.running_game(rig, test_id, bat_name) as (log, hands, vanilla_rows):
        if not lr.wait_for(log, lr.MENU_LOADED, 240, hands):
            problem = "main-menu: the game never logged that the main menu was up"
        else:
            hands.sleep(20)
            hands.front()
            lr.click_menu(hands, "Missions", lr.MAIN_MENU_MISSIONS)
            hands.sleep(3)
            layout = lr.mission_list_layout(lr._log_text(log), vanilla_rows, DUEL_MOD_ID)
            below, total = layout if layout else (0, None)
            rows_in_mod = len(DUEL_MISSIONS)
            # The mod is named "zz ..." so the launcher lists it last and its missions sit at the bottom of the list; a mission more
            # than MAX_ROWS_REACHABLE rows up is off-screen and a click there replays whatever was selected (DUEL12-20261011).
            if below + rows_in_mod - 1 > lr.MAX_ROWS_REACHABLE:
                problem = f"the duel missions sit {below} rows above the bottom of the mission list; only {lr.MAX_ROWS_REACHABLE} are reachable"
            for position, label in enumerate(DUEL_MISSIONS if problem is None else ()):
                if only and label not in only:
                    continue
                offset = len(lr._log_text(log))
                lr.play_probe_combat(hands, below + (rows_in_mod - 1 - position), total)
                finished, evidence = wait_for_end(log, label, combat_timeout, hands, rig, test_id, since=offset)
                if not finished:
                    problem = f"{label}: no END line from the duel plugin" + (f"; stall evidence: {', '.join(evidence)}" if evidence else "")
                    break
                played.append(label)
                hands.sleep(3)
                hands.front()
                hands.click(*lr.COMBAT_CONTINUE)
                hands.sleep(4)
    duels = parse_duel_log(lr._log_text(log))
    return {"played": played, "problem": problem, "summary": summarise(duels), "log": str(log)}
