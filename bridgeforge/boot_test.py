from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from .log_triage import triage_log
from .scanner import _load_lenient_json_file

# Overridable by tests: point at a fake launcher .bat and shrink the poll interval so a boot test
# runs in seconds instead of minutes. Production code should never need to change these.
BAT_NAME = "run-java25.bat"
POLL_INTERVAL_SECONDS = 1.0

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
MAIN_MENU_MARKER = "Playing music with id [miscallenous_main_menu.ogg]"

FATAL_DIALOG_REASON = (
    "Starsector shows a Java Fatal Error only as a modal dialog; it is never written to stdout/stderr. "
    "The process is still running with no main-menu marker at timeout, which is consistent with a stuck "
    "fatal-error dialog (or a very slow boot). Inspect the process manually before trusting this result."
)


def _is_link(path: Path) -> bool:
    """True for a symlink or an NTFS junction (junctions do not satisfy Path.is_symlink())."""
    try:
        if path.is_symlink():
            return True
    except OSError:
        pass
    try:
        st = path.lstat()
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def _running_java_under(runtime_dir: Path) -> list[dict[str, object]]:
    """Java.exe processes whose EXECUTABLE PATH is under runtime_dir (matched by path, not name).

    A java.exe running elsewhere (e.g. VS Code's Java language server) must never trigger a refusal.
    """
    runtime_str = str(runtime_dir.resolve()).lower()
    matches: list[dict[str, object]] = []
    try:
        import psutil  # type: ignore

        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                exe = proc.info.get("exe") or ""
            except Exception:
                continue
            if exe and exe.lower().startswith(runtime_str):
                matches.append({"pid": proc.info.get("pid"), "exe": exe})
        return matches
    except ImportError:
        pass
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | "
                "Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        raw = (completed.stdout or "").strip()
        if not raw:
            return matches
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        for item in data:
            exe = str(item.get("ExecutablePath") or "")
            if exe and exe.lower().startswith(runtime_str):
                matches.append({"pid": item.get("ProcessId"), "exe": exe})
    except Exception:
        pass
    return matches


def _terminate_tree(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=30, check=False)
    except Exception:
        pass


def _result(status: str, reason: str | None, log: Path | None = None, errlog: Path | None = None, elapsed: float | None = None, triage: dict | None = None, restored: bool = False) -> dict[str, object]:
    return {
        "status": status,
        "reason": reason,
        "log": str(log) if log is not None else None,
        "errlog": str(errlog) if errlog is not None else None,
        "elapsed_seconds": elapsed,
        "triage": triage,
        "restored": restored,
    }


def run_boot_test(runtime_dir: Path, mods: list[str], timeout: int = 240, log_name: str | None = None, keep_mods: bool = False) -> dict:
    """Launch an isolated Starsector runtime rig headlessly and watch its log for a boot milestone.

    NEVER call this against a real/shared install: runtime_dir must be a disposable rig whose
    starsector-core is a junction/symlink to the real install (so saves/screenshots/mods write only
    into the rig, never into a real player's save). This function refuses to run otherwise, and also
    refuses if a java.exe already runs from under runtime_dir (stale process from a previous test).
    """
    runtime_dir = Path(runtime_dir).expanduser().resolve()

    core_path = runtime_dir / "starsector-core"
    if not _is_link(core_path):
        return _result(
            "REFUSED",
            f"{core_path} is not a junction/symlink. run_boot_test refuses to launch against a "
            "non-isolated starsector-core to avoid writing into a real save.",
        )

    already_running = _running_java_under(runtime_dir)
    if already_running:
        pids = ", ".join(str(item.get("pid")) for item in already_running)
        return _result(
            "REFUSED",
            f"java.exe already running under {runtime_dir} (pid {pids}). Terminate it before starting "
            "a new boot test; two overlapping runs would corrupt the shared log/mods rig.",
        )

    bat_path = runtime_dir / BAT_NAME
    if not bat_path.is_file():
        return _result("REFUSED", f"Launcher not found: {bat_path}")

    mods_dir = runtime_dir / "mods"
    enabled_mods_path = mods_dir / "enabled_mods.json"
    original_text: str | None = None
    if enabled_mods_path.is_file():
        original_text = enabled_mods_path.read_text(encoding="utf-8")
    backup_path = enabled_mods_path.with_suffix(".json.bootbak")
    if original_text is not None:
        backup_path.write_text(original_text, encoding="utf-8")
    mods_dir.mkdir(parents=True, exist_ok=True)
    enabled_mods_path.write_text(json.dumps({"enabledMods": list(mods)}), encoding="utf-8")

    def _restore(keep: bool) -> bool:
        if keep:
            try:
                backup_path.unlink()
            except OSError:
                pass
            return False
        try:
            if original_text is not None:
                enabled_mods_path.write_text(original_text, encoding="utf-8")
            else:
                enabled_mods_path.unlink(missing_ok=True)
        finally:
            try:
                backup_path.unlink()
            except OSError:
                pass
        return True

    logs_dir = runtime_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    name = log_name or f"boot-test-{int(time.time())}"
    log_path = logs_dir / f"{name}.stdout.log"
    err_path = logs_dir / f"{name}.stderr.log"

    command_line = f'cmd.exe /c ""{bat_path}" > "{log_path}" 2> "{err_path}""'
    started = time.monotonic()
    try:
        # Passed as a raw command-line string (not a list): on Windows, subprocess uses a string
        # args verbatim as the CreateProcess command line when shell=False, which is required here
        # because the leading-quote + redirection trick below only works as a single literal string
        # (Python's list2cmdline re-quoting would corrupt it).
        process = subprocess.Popen(command_line, cwd=str(runtime_dir))
    except OSError as exc:
        restored = _restore(keep_mods)
        return _result("FAIL", f"Failed to launch {bat_path}: {exc}", log_path, err_path, 0.0, None, restored)

    status = "FAIL"
    reason: str | None = None
    try:
        while True:
            elapsed = time.monotonic() - started
            marker_found = False
            if log_path.is_file():
                try:
                    text = log_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                marker_found = MAIN_MENU_MARKER in text
            if marker_found:
                status = "PASS"
                reason = "Main-menu music marker observed in the boot log."
                break
            if process.poll() is not None:
                status = "FAIL"
                reason = f"Process exited (code {process.returncode}) before the main-menu marker appeared."
                break
            if elapsed >= timeout:
                if process.poll() is None:
                    status = "SUSPECT_FATAL_DIALOG"
                    reason = FATAL_DIALOG_REASON
                else:
                    status = "FAIL"
                    reason = f"Process exited (code {process.returncode}) before the main-menu marker appeared."
                break
            time.sleep(POLL_INTERVAL_SECONDS)
    finally:
        elapsed = time.monotonic() - started
        if process.poll() is None:
            _terminate_tree(process.pid)
            for java in _running_java_under(runtime_dir):
                pid = java.get("pid")
                if isinstance(pid, int):
                    _terminate_tree(pid)
        try:
            process.wait(timeout=10)
        except Exception:
            pass

    triage_summary = None
    if log_path.is_file():
        try:
            triage_summary = triage_log(log_path)
        except ValueError:
            triage_summary = None

    restored = _restore(keep_mods)

    return _result(status, reason, log_path, err_path, elapsed, triage_summary, restored)


def _find_mod_id(runtime_dir: Path, mod_id: str) -> dict | None:
    """Read mod_info.json for a mod already present under <runtime_dir>/mods/ whose declared id matches."""
    mods_dir = runtime_dir / "mods"
    if not mods_dir.is_dir():
        return None
    for child in sorted(p for p in mods_dir.iterdir() if p.is_dir()):
        info = _load_lenient_json_file(child / "mod_info.json")
        if isinstance(info, dict) and info.get("id") == mod_id:
            return info
    return None


def _libs_needed_by_targets(runtime_dir: Path, target_mods: list[str], lib_ids: list[str]) -> list[str]:
    """Libs (from lib_ids) that any target mod declares as a dependency in its own mod_info.json.

    Falls back to every lib in lib_ids for a target whose mod_info.json can't be found or declares no
    dependencies, so run (a) of the matrix stays a safe "boots with what it needs" check rather than
    silently dropping a library the target actually requires.
    """
    lib_id_set = set(lib_ids)
    needed: set[str] = set()
    for target in target_mods:
        info = _find_mod_id(runtime_dir, target)
        dependencies = info.get("dependencies") if isinstance(info, dict) else None
        if not isinstance(dependencies, list):
            needed |= lib_id_set
            continue
        declared = {dep.get("id") for dep in dependencies if isinstance(dep, dict)}
        needed |= declared & lib_id_set
    return sorted(needed)


def _matrix_verdict(result_a: dict, result_b: dict) -> str:
    status_a, status_b = result_a.get("status"), result_b.get("status")
    if status_a == "REFUSED" or status_b == "REFUSED":
        return "REFUSED"
    if status_a == "SUSPECT_FATAL_DIALOG" or status_b == "SUSPECT_FATAL_DIALOG":
        return "SUSPECT_FATAL_DIALOG"
    if status_a != "PASS":
        return "FAIL_ALONE"
    if status_b != "PASS":
        return "FAIL_WITH_PACK_ONLY"
    return "PASS"


def _triage_counts(result: dict) -> dict | None:
    triage = result.get("triage")
    return triage.get("counts") if isinstance(triage, dict) else None


def run_boot_matrix(
    runtime_dir: Path,
    target_mods: list[str],
    pack: str,
    timeout: int = 240,
    log_name: str | None = None,
    compat_sets_path: Path | None = None,
) -> dict:
    """Boot the target mods alone (with just the libs they need), then with the whole named pack.

    Two sequential run_boot_test calls, each of which restores enabled_mods.json itself, so the rig's
    enabled_mods.json ends up back at its original content once this returns. Never calls run_boot_test
    with keep_mods=True. See docs/REVIVAL_ASSURANCE_PLAN.md P4 for the matrix/verdict design.
    """
    from .compat_sets import lib_mod_ids, resolve_set, load_compat_sets  # local import: avoids a circular import with compat_sets._is_link

    runtime_dir = Path(runtime_dir).expanduser().resolve()
    data = load_compat_sets(compat_sets_path)
    resolved = resolve_set(data, pack)
    pack_ids = sorted(resolved)
    lib_ids = lib_mod_ids(data, pack)

    needed_libs = _libs_needed_by_targets(runtime_dir, target_mods, lib_ids)
    alone_mods = sorted(set(target_mods) | set(needed_libs))
    with_pack_mods = sorted(set(target_mods) | set(pack_ids))

    base_name = log_name or "boot-matrix"
    result_alone = run_boot_test(runtime_dir, alone_mods, timeout=timeout, log_name=f"{base_name}-alone")
    result_with_pack = run_boot_test(runtime_dir, with_pack_mods, timeout=timeout, log_name=f"{base_name}-with-pack")

    verdict = _matrix_verdict(result_alone, result_with_pack)

    return {
        "schema_version": 1,
        "mode": "BOOT_MATRIX",
        "pack": pack,
        "target_mods": sorted(target_mods),
        "matrix": [
            {
                "config": "alone",
                "mods": alone_mods,
                "status": result_alone.get("status"),
                "reason": result_alone.get("reason"),
                "triage": _triage_counts(result_alone),
            },
            {
                "config": "with_pack",
                "mods": with_pack_mods,
                "status": result_with_pack.get("status"),
                "reason": result_with_pack.get("reason"),
                "triage": _triage_counts(result_with_pack),
            },
        ],
        "verdict": verdict,
        "results": {"alone": result_alone, "with_pack": result_with_pack},
    }
