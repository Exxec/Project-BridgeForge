"""Observed process exit of a live run, kept beside its log as `<rig>/logs/<TESTID>.exit.json`.

A run started with `probe-group live` writes one when it finished (`--natural-exit`: after waiting for the operator to quit; by default: after closing the game window itself once the probe's done marker appeared, see graceful_exit.py). NATURAL carries the integer return code of the
launcher process (`cmd.exe /c <bat>`, so the bat's last errorlevel; equal to Java's only when the bat ends on the java call);
KILLED means the run had to stop the process tree (timeout, taskkill) and carries no code; UNKNOWN is the absence of a file.
A code is never inferred from a clean log and never defaulted to 0.
"""
from __future__ import annotations

import json
from pathlib import Path

from .safeio import atomic_write_text

NATURAL, KILLED, UNKNOWN = "NATURAL", "KILLED", "UNKNOWN"
OBSERVATIONS = (NATURAL, KILLED, UNKNOWN)


class ExitObservationError(ValueError):
    pass


def check_observation(observed: str, code: int | None) -> None:
    """Raise unless `observed` and `code` agree: only NATURAL carries an integer code, nothing else may."""
    if observed not in OBSERVATIONS:
        raise ExitObservationError(f"process_exit_observed must be one of {', '.join(OBSERVATIONS)}")
    if observed == NATURAL:
        if not isinstance(code, int) or isinstance(code, bool):
            raise ExitObservationError("a NATURAL exit needs the observed integer return code")
    elif code is not None:
        raise ExitObservationError(f"a {observed} process has no observed exit code; it must be null")


def observed_exit(return_code: int | None, java_left: bool) -> tuple[str, int | None]:
    """(observed, code) for a process already waited on: NATURAL with its integer code only when it exited by itself and
    no java was left running; KILLED with no code when it is still running or a java was left behind."""
    if return_code is None or java_left or not isinstance(return_code, int):
        return KILLED, None
    return NATURAL, return_code


def observation_path(rig: Path, test_id: str) -> Path:
    return Path(rig) / "logs" / f"{test_id}.exit.json"


def write_exit_observation(rig: Path, test_id: str, observed: str, code: int | None) -> dict:
    check_observation(observed, code)
    record = {"process_exit_observed": observed, "process_exit_code": code}
    path = observation_path(rig, test_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(record, indent=2) + "\n")
    return record


def read_exit_observation(rig: Path, test_id: str) -> tuple[str, int | None]:
    """(observed, code) for the run; a missing file is UNKNOWN. A malformed or self-contradicting file raises."""
    path = observation_path(rig, test_id)
    if not path.is_file():
        return UNKNOWN, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        observed, code = data["process_exit_observed"], data.get("process_exit_code")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ExitObservationError(f"unreadable exit observation {path}: {exc}") from exc
    check_observation(observed, code)
    return observed, code
