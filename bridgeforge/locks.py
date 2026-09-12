"""Read-only lock diagnostics. Never terminates processes or releases their locks."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path


def _inside(path: str, target: Path) -> bool:
    candidate = Path(path).resolve()
    return candidate == target or (target.is_dir() and target in candidate.parents)


def _restart_manager(files: list[Path]) -> list[dict[str, object]]:
    if os.name != "nt":
        raise OSError("Restart Manager is Windows-only")
    if not files:
        return []

    class UniqueProcess(ctypes.Structure):
        _fields_ = [("pid", wintypes.DWORD), ("start", wintypes.FILETIME)]

    class ProcessInfo(ctypes.Structure):
        _fields_ = [("process", UniqueProcess), ("name", wintypes.WCHAR * 256),
                    ("service", wintypes.WCHAR * 64), ("type", ctypes.c_uint),
                    ("status", wintypes.ULONG), ("session", wintypes.DWORD),
                    ("restartable", wintypes.BOOL)]

    dll = ctypes.WinDLL("rstrtmgr.dll")
    dll.RmStartSession.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.LPWSTR]
    dll.RmRegisterResources.argtypes = [wintypes.DWORD, ctypes.c_uint,
        ctypes.POINTER(wintypes.LPCWSTR), ctypes.c_uint, ctypes.POINTER(UniqueProcess),
        ctypes.c_uint, ctypes.POINTER(wintypes.LPCWSTR)]
    dll.RmGetList.argtypes = [wintypes.DWORD, ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ProcessInfo), ctypes.POINTER(wintypes.DWORD)]
    dll.RmEndSession.argtypes = [wintypes.DWORD]
    for function in (dll.RmStartSession, dll.RmRegisterResources, dll.RmGetList, dll.RmEndSession):
        function.restype = wintypes.DWORD
    handle = wintypes.DWORD()
    key = ctypes.create_unicode_buffer(33)
    error = dll.RmStartSession(ctypes.byref(handle), 0, key)
    if error:
        raise OSError(f"RmStartSession error {error}")
    try:
        names = (wintypes.LPCWSTR * len(files))(*(str(p) for p in files))
        error = dll.RmRegisterResources(handle, len(files), names, 0, None, 0, None)
        if error:
            raise OSError(f"RmRegisterResources error {error}")
        needed, count, reasons = ctypes.c_uint(), ctypes.c_uint(), wintypes.DWORD()
        error = dll.RmGetList(handle, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reasons))
        for _ in range(4):
            if error == 0:
                return []
            if error != 234:
                raise OSError(f"RmGetList error {error}")
            count.value = needed.value
            entries = (ProcessInfo * count.value)()
            error = dll.RmGetList(handle, ctypes.byref(needed), ctypes.byref(count), entries, ctypes.byref(reasons))
            if error == 0:
                return [{"pid": int(p.process.pid), "name": p.name,
                         "sources": ["restart_manager"]} for p in entries[:count.value]]
        raise OSError("Restart Manager process list kept changing; retry")
    finally:
        dll.RmEndSession(handle)


def _process_paths(target: Path) -> tuple[list[dict[str, object]], list[str]]:
    try:
        import psutil
    except ImportError:
        return [], ["psutil unavailable: current-directory and open-file checks not performed"]
    found, limitations = [], []
    denied = 0
    for process in psutil.process_iter():
        sources = []
        try:
            if _inside(process.cwd(), target):
                sources.append("cwd")
        except psutil.AccessDenied:
            denied += 1
        except (psutil.NoSuchProcess, OSError):
            continue
        try:
            if any(_inside(item.path, target) for item in process.open_files()):
                sources.append("open_file")
        except psutil.AccessDenied:
            denied += 1
        except (psutil.NoSuchProcess, OSError):
            pass
        if sources:
            try:
                name, command = process.name(), process.cmdline()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                name, command = "unknown", []
            text = " ".join(command).lower()
            watcher = name.lower() in {"tail", "tail.exe", "grep", "grep.exe"} or (
                "get-content" in text and "-wait" in text)
            found.append({"pid": process.pid, "name": name, "command": command,
                          "sources": sources, "watcher_candidate": watcher})
    if denied:
        limitations.append(f"{denied} process queries denied; absence of results is not proof of no locks")
    return found, limitations


def who_locks(path: Path) -> dict[str, object]:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise ValueError(f"path does not exist: {target}")
    files = [target] if target.is_file() else [p for p in (
        target / "starsector.log", target / "starsector-core/starsector.log",
        target / "mods/enabled_mods.json") if p.is_file()]
    processes, limitations = _process_paths(target)
    try:
        processes.extend(_restart_manager(files))
    except OSError as exc:
        limitations.append(str(exc))
    by_pid: dict[int, dict[str, object]] = {}
    for item in processes:
        pid = int(item["pid"])
        if pid in by_pid:
            by_pid[pid]["sources"] = sorted(set(by_pid[pid]["sources"]) | set(item["sources"]))
        else:
            by_pid[pid] = item
    if target.is_dir():
        limitations.append("Directory Restart Manager coverage is limited to rig log/config sentinels; process cwd/open-file checks cover descendants")
    return {"schema_version": 1, "mode": "WHO_LOCKS", "target": str(target),
            "status": "FOUND" if by_pid else "NO_PROCESS_FOUND",
            "processes": [by_pid[pid] for pid in sorted(by_pid)], "limitations": limitations,
            "note": "Candidates only: cwd and open files do not necessarily prevent deletion. No process was stopped."}
