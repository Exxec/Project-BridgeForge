"""Prepatcher's own account of one live run (ROADMAP-3 98.18).

StarsectorPrepatcher's javaagent writes `logs/prepatcher.log` in its mod folder at each game start, one line per event:
`2026-11-27T05:43:06.500912300Z [INFO] StarsectorPrepatcher 0.18.9 javaagent starting`. The 98.14 proof run on RC9 was judged
from that file by hand (63 patches applied on 40 classes, no WARN or ERROR). `summary` reads the lines written since a run
began, so a log left from an earlier start never passes for this one: an enabled Prepatcher with no line in the window means
the agent did not start (a launcher without `-javaagent`, or a crash before it ran).

The wording counted below is the agent's own (strings in StarsectorPrepatcherAgent.jar, checked 2026-11-27): "APPLIED <patch>
to <class>:", "Patched <class> structurally", "... rolled back ...", "... failed open ..." (the original game code runs
unpatched).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

PREPATCHER_ID = "starsector_prepatcher"
LOG_PARTS = ("logs", "prepatcher.log")
MAX_LOG_BYTES = 20 * 1024 * 1024  # a few hundred lines per start (124 on RC9, 2026-11-26); more is not a Prepatcher log
MAX_PROBLEM_LINES = 5

_LINE = re.compile(r"^(?P<at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?Z \[(?P<level>[A-Z]+)\] (?P<text>.*)$")
_STARTING = re.compile(r"\bStarsectorPrepatcher (?P<version>\S+) javaagent starting\b")
_APPLIED = re.compile(r"\bAPPLIED \S+ to (?P<cls>[^\s:]+)")
_PATCHED = re.compile(r"\bPatched (?P<cls>\S+) structurally\b")


def run_started() -> datetime:
    """The moment a run begins, in the agent's clock (UTC, whole seconds: the log is compared at that precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def _prepatcher_folder(rig: Path) -> Path | None:
    """The rig's Prepatcher folder when Prepatcher is enabled and installed once; None otherwise."""
    from bridgeforge.run_manifest import ManifestError, _enabled_ids, _rig_folders

    try:
        enabled = _enabled_ids(rig)
    except ManifestError:
        return None
    if PREPATCHER_ID not in enabled:
        return None
    folders = _rig_folders(rig).get(PREPATCHER_ID, [])
    return folders[0] if len(folders) == 1 else None


def _read(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            return handle.read(MAX_LOG_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return None


def summarise(text: str, since: datetime) -> dict:
    """Counts over the log lines stamped at or after `since` (lines without a stamp continue the line before them)."""
    keep, kept = False, []
    for line in text.splitlines():
        match = _LINE.match(line)
        if match:
            at = datetime.strptime(match["at"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            keep = at >= since
            if keep:
                kept.append((match["level"], match["text"]))
        elif keep and kept:
            kept[-1] = (kept[-1][0], f"{kept[-1][1]} {line.strip()}")
    versions = sorted({m["version"] for _level, text in kept if (m := _STARTING.search(text))})
    classes = {m["cls"] for _level, text in kept if (m := _APPLIED.search(text) or _PATCHED.search(text))}
    errors = [text for level, text in kept if level in ("ERROR", "FATAL")]
    warnings = [text for level, text in kept if level == "WARN"]
    rolled_back = [text for _level, text in kept if "rolled back" in text]
    failed_open = [text for _level, text in kept if "failed open" in text]
    problems = list(dict.fromkeys(errors + rolled_back + failed_open))
    if not kept:
        verdict = "NO_LOG"
    elif problems:
        verdict = "PROBLEMS"
    elif warnings:
        verdict = "WARNINGS"
    else:
        verdict = "CLEAN"
    return {"verdict": verdict, "version": ", ".join(versions) or None, "starts": sum(1 for _level, text in kept if _STARTING.search(text)),
            "lines": len(kept), "applied": sum(1 for _level, text in kept if _APPLIED.search(text)), "classes": len(classes),
            "warnings": len(warnings), "errors": len(errors), "rolled_back": len(rolled_back), "failed_open": len(failed_open),
            "problem_lines": [text[:300] for text in (problems or warnings)[:MAX_PROBLEM_LINES]]}


def summary(rig: Path, since: datetime) -> dict | None:
    """Prepatcher's summary of the run that began at `since`, or None when the rig does not enable Prepatcher."""
    folder = _prepatcher_folder(Path(rig))
    if folder is None:
        return None
    path = folder.joinpath(*LOG_PARTS)
    text = _read(path) if path.is_file() else ""
    if text is None:
        return {"verdict": "UNREADABLE", "log": str(path)}
    return {**summarise(text, since), "log": str(path)}


def describe(found: dict | None) -> str | None:
    """One line for a live run's printout, or None when there is no summary."""
    if not found:
        return None
    if found["verdict"] == "UNREADABLE":
        return f"prepatcher: UNREADABLE ({found['log']})"
    if found["verdict"] == "NO_LOG":
        return "prepatcher: NO_LOG: enabled, and wrote no line during this run (was the agent on the java line?)"
    return (f"prepatcher {found['version'] or '?'}: {found['verdict']}; applied {found['applied']} on {found['classes']} classes; "
            f"WARN {found['warnings']}, ERROR {found['errors']}, rolled back {found['rolled_back']}, failed open {found['failed_open']}")
