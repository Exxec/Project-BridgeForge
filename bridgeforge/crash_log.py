"""JVM fatal-error logs (`hs_err_pid*.log`) for `log-triage` (ROADMAP 35.10, 2026-10-04).

Ported from SPW's `spw/crash_log.py` (Exxec/SPW, f368ef5): the sister programs share no runtime code, so this is
a copy with its own tests. A JVM crash (native code, out of memory, a VM assertion) never reaches
`starsector.log`'s exception handler; the JVM writes `hs_err_pid<PID>.log` to its working directory, the game's
`starsector-core/` for a normal launch (one sat in this checkout on 2026-10-04). Only the fields that stay stable
across crash types are read: pid/tid, the `#` problem summary, the JRE/VM/command/host/time lines and the Java
frames at the crash. BridgeForge adds which mod owns each Java frame, using `log_triage.class_owner_index`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PID_TID_PATTERN = re.compile(r"pid=(\d+),\s*tid=(\d+)")
_ELAPSED_SECONDS_PATTERN = re.compile(r"elapsed time:\s*([0-9.]+)\s*seconds")
_JAVA_FRAMES_HEADER = "Java frames:"
_KEY_LINES = {
    "JRE version:": "jre_version",
    "Java VM:": "java_vm",
    "Command Line:": "command_line",
    "Host:": "host",
    "Time:": "crash_time_raw",
}
# "j  com.foo.Bar.method(I)V+12", "J 1234 c2 com.foo.Bar.method(I)V (45 bytes) @ ...", "v  ~StubRoutines::..."
_FRAME_METHOD = re.compile(r"^[jJ]\s+(?:\d+\s+(?:c1|c2|jvmci)?\s*)?(?P<qualified>[\w$.]+)\(")


def find_crash_logs(directory: Path) -> list[Path]:
    """`hs_err_pid*.log` directly in `directory`: the JVM writes them to its working directory, not a subfolder."""
    try:
        return sorted(Path(directory).glob("hs_err_pid*.log"))
    except OSError:
        return []


def parse_crash_log(path: Path) -> dict[str, Any]:
    """The small, stable, high-value fields of one hs_err log (see the module docstring)."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"path": str(path), "parse_status": "UNREADABLE"}
    result: dict[str, Any] = {
        "path": str(path), "parse_status": "PARSED", "pid": None, "tid": None, "problem_summary": [],
        "jre_version": None, "java_vm": None, "command_line": None, "host": None, "crash_time_raw": None,
        "elapsed_seconds": None, "java_frames": [],
    }
    match = _PID_TID_PATTERN.search(text)
    if match:
        result["pid"], result["tid"] = int(match.group(1)), int(match.group(2))
    lines = text.splitlines()
    in_problem = False
    for line in lines:
        if "A fatal error has been detected" in line:
            in_problem = True
            continue
        if not in_problem:
            continue
        stripped = line.strip()
        if not stripped.startswith("#"):
            break
        content = stripped.lstrip("#").strip()
        if content:
            result["problem_summary"].append(content)
    if not result["problem_summary"]:
        # A native out-of-memory log opens with its own "#" block and no "fatal error" line (BridgeForge's AST
        # helper, hs_err_pid35148.log, 2026-09-28): keep that block up to its "Possible reasons" advice.
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("#"):
                break
            content = stripped.lstrip("#").strip()
            if content.startswith("Possible reasons"):
                break
            if content:
                result["problem_summary"].append(content)
    for line in lines:
        unboxed = line.strip().lstrip("#").strip()
        for prefix, key in _KEY_LINES.items():
            if unboxed.startswith(prefix):
                result[key] = unboxed[len(prefix):].strip()
                if key == "crash_time_raw":
                    elapsed = _ELAPSED_SECONDS_PATTERN.search(unboxed)
                    if elapsed:
                        result["elapsed_seconds"] = float(elapsed.group(1))
    in_frames = False
    for line in lines:
        if line.strip().startswith(_JAVA_FRAMES_HEADER):
            in_frames = True
            continue
        if in_frames:
            stripped = line.strip()
            if not stripped or stripped[0] not in "jJvV":
                break
            result["java_frames"].append(stripped)
    return result


def frame_class(frame: str) -> str | None:
    """The class of a Java frame line (`j`/`J` frames; `v` VM frames have none)."""
    match = _FRAME_METHOD.match(frame)
    if not match:
        return None
    parts = match.group("qualified").split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else None


def attribute_frames(crash: dict[str, Any], owner_index: dict[str, str]) -> dict[str, Any]:
    """Which mods own the crash's Java frames, nearest the crash first; `top_mod` is the first owned frame's mod."""
    from .log_triage import _frame_owner

    owners: list[dict[str, str]] = []
    for frame in crash.get("java_frames") or []:
        cls = frame_class(frame)
        owner = _frame_owner(f"\tat {cls}.m(X)", owner_index) if cls else None
        if owner:
            owners.append({"frame": frame, "class": cls, "mod": owner})
    return {"mod_frames": owners, "top_mod": owners[0]["mod"] if owners else None}
