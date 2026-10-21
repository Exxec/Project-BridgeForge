"""The probe's startup echo of the run's manifest id (ROADMAP item 75 R1, "startup-marker echo").

The harness writes `<rig>/saves/common/bf_probe_run.data` (JSON with manifest_id and run_id) once the pre-launch manifest exists. The
probe logs `BF-PROBE|<ver>|run|manifest_id=<id>` right after the rig gate. The id is not part of `bf_probe_config` because the manifest
hashes that file. A log without any `run` line comes from a probe that predates the echo: LEGACY, provenance as before, not a failure.
A probe that echoes but found no file says `manifest_id=NONE`: NOT_ECHOED. A different id: MISMATCH.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .safeio import atomic_write_text

RUN_FILE = "bf_probe_run.data"  # SettingsAPI appends ".data" to the name the probe reads ("bf_probe_run")
MATCH, MISMATCH, NOT_ECHOED, LEGACY = "MATCH", "MISMATCH", "NOT_ECHOED", "LEGACY"
_ECHO = re.compile(r"BF-PROBE\|[^|\r\n]*\|run\|manifest_id=([^|\s]*)")
NONE_ID = "NONE"


def write_run_file(rig: Path, run_id: str, manifest_id: str) -> Path:
    path = Path(rig) / "saves" / "common" / RUN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps({"manifest_id": manifest_id, "run_id": run_id}, sort_keys=True))
    return path


def echoed_ids(log_text: str) -> list[str]:
    return _ECHO.findall(log_text)


def echo_state(log_text: str, manifest_id: str) -> tuple[str, str | None]:
    """(state, problem or None). A problem is set for MISMATCH and NOT_ECHOED only."""
    ids = echoed_ids(log_text)
    if not ids:
        return LEGACY, None
    wrong = sorted({i for i in ids if i not in (manifest_id, NONE_ID, "")})
    if wrong:
        return MISMATCH, f"MANIFEST_MISMATCH: the probe echoed manifest id {wrong[0][:16]}, this run's is {manifest_id[:16]}: the log is from another run"
    if all(i in (NONE_ID, "") for i in ids):
        return NOT_ECHOED, "MANIFEST_NOT_ECHOED: the probe logged its run line but found no manifest id (bf_probe_run missing or unreadable)"
    return MATCH, None
