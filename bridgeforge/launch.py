"""The one place the rig game is started, watched and stopped (ROADMAP-3 item 79.7).

`probe-group live` (live_run.running_game) and `boot-test` (boot_test.run_boot_test) both go through here: the launch from the
rig's bat with stdout/stderr in `<rig>/logs/<TESTID>.{stdout,stderr}.log`, the run manifest prepare/release, the launch watchdog,
the launcher Play click, the exit observation (NATURAL / KILLED), the graceful close on the probe's done marker, and the stop of
the rig's java and the launcher's whole tree. `tools/bf-test.ps1 launch` calls those two commands instead of launching itself.

The process helpers (`_running_java_under`, `_terminate_tree`, `java_started`) and the watchdog bound are looked up in `boot_test`
when used, so a test that replaces them there replaces them for every caller.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable


class GameRefused(RuntimeError):
    """The rig is not safe or ready to run a game (shared install, a game already running, no launcher)."""


class LaunchNoProcess(GameRefused):
    """The launch watchdog fired: no java process appeared (ROADMAP item 73 G4). The live result stage is LAUNCH_NO_PROCESS."""


EXIT_POLL_SECONDS = 2.0


def settle_exit(process, wait: float, *, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                java_left: Callable[[], bool] = lambda: False) -> tuple[str, int | None]:
    """Wait up to `wait` seconds for the launched process to exit by itself: (NATURAL, its integer return code), or (KILLED, None)
    when it is still running at the bound or left a java process behind. Never returns a code for a process that was not seen to exit."""
    from .exit_observation import KILLED, observed_exit

    deadline = clock() + wait
    while process.poll() is None:
        if clock() >= deadline:
            return KILLED, None
        sleep(EXIT_POLL_SECONDS)
    return observed_exit(process.poll(), java_left())


def command_line(bat: Path, log: Path, err: Path) -> str:
    # A raw command-line string, not a list: the leading-quote + redirection form only works verbatim (list2cmdline would corrupt it).
    return f'cmd.exe /c ""{bat}" > "{log}" 2> "{err}""'


def start_game(rig: Path, bat: Path, log: Path, err: Path):
    """Start the rig's launcher bat with its output in `log` / `err`. The only place the game process is created."""
    return subprocess.Popen(command_line(bat, log, err), cwd=str(rig))


def prepare_manifest(rig: Path, test_id: str, kind: str, *, targets: list[str], expected: list[str], scenario: str, bat: Path) -> dict:
    """R1: record what is staged before anything starts. Raises run_manifest.ManifestError."""
    from .run_manifest import prepare_run

    return prepare_run(rig, test_id, kind, targets=targets, expected=expected, scenario=scenario, launcher=bat)


def release_manifest(rig: Path, test_id: str, bat: Path) -> None:
    """The run ended: re-hash the staged files and give the rig back. A failure here is left visible (no completion record means the
    evaluator refuses the run), never swallowed into a pass."""
    from .run_manifest import ManifestError, release_run

    try:
        release_run(rig, test_id, bat)
    except (ManifestError, OSError):
        pass


def watchdog_tripped(rig: Path, process, launched_at: float, state: dict) -> bool:
    """Launch watchdog (ROADMAP 60f): True when no java process has appeared LAUNCH_WATCHDOG_SECONDS after launch. `state` keeps
    whether java was ever seen."""
    from . import boot_test

    if not state.get("seen"):
        state["seen"] = boot_test.java_started(rig, process.pid)
        if not state["seen"] and time.monotonic() - launched_at >= boot_test.LAUNCH_WATCHDOG_SECONDS:
            return True
    return False


def click_launcher(rig: Path, process) -> str | None:
    """One attempt to press Play in the launcher window (it waits for a click before the game logs anything, owner 2026-10-11)."""
    from . import boot_test
    from .launcher_click import click_launcher_once, descendant_pids

    pids = {item["pid"] for item in boot_test._running_java_under(rig) if isinstance(item.get("pid"), int)} | descendant_pids(process.pid)
    return click_launcher_once(pids)


def stop_game(rig: Path, test_id: str, process, *, record_exit: bool = False, await_exit: bool = False, exit_wait: float = 0,
              graceful: bool = False, manifest_id: str | None = None) -> None:
    """Observe the exit before anything is killed, then stop the rig's java and the launcher's tree.

    `record_exit` (natural exit): when `await_exit`, wait up to `exit_wait` seconds for the game to quit by itself and write
    <rig>/logs/<TESTID>.exit.json (NATURAL with the code, else KILLED); a run that did not finish records KILLED.
    `graceful` (without `record_exit`): a finished run (`await_exit`) closes the game through the probe's done marker first."""
    from . import boot_test
    from .exit_observation import KILLED, write_exit_observation

    def java_left() -> bool:
        return bool(boot_test._running_java_under(rig))

    if record_exit:
        observed, code = KILLED, None
        if await_exit:
            observed, code = settle_exit(process, exit_wait, java_left=java_left)
        write_exit_observation(rig, test_id, observed, code)
    elif graceful and await_exit and manifest_id:
        from .graceful_exit import graceful_close
        from .launcher_click import descendant_pids

        observed, code = graceful_close(rig, manifest_id, process, settle=settle_exit,
                                        pids=lambda: {j["pid"] for j in boot_test._running_java_under(rig) if isinstance(j.get("pid"), int)} | descendant_pids(process.pid),
                                        java_left=java_left)
        write_exit_observation(rig, test_id, observed, code)
    for java in boot_test._running_java_under(rig):
        if isinstance(java.get("pid"), int):
            boot_test._terminate_tree(java["pid"])
    if process.poll() is None:
        boot_test._terminate_tree(process.pid)
    try:
        process.wait(timeout=10)
    except Exception:
        pass
