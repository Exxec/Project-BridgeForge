"""Owned analysis subprocesses: Windows kill-on-close jobs or POSIX sessions."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess

import psutil


class _WindowsJob:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64), ('flags', w.DWORD),
                        ('minimum', c.c_size_t), ('maximum', c.c_size_t), ('active', w.DWORD),
                        ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ('read', 'write', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(c.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                        ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)]
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel, self.handle = kernel, kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise c.WinError(c.get_last_error())
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; handle is not inheritable.
        if not kernel.SetInformationJobObject(self.handle, 9, c.byref(info), c.sizeof(info)):
            error = c.WinError(c.get_last_error())
            self.close()
            raise error

    def assign(self, pid):
        import ctypes as c
        from ctypes import wintypes as w
        handle = self.kernel.OpenProcess(0x0100 | 0x0001 | 0x1000, False, pid)
        if not handle:
            raise c.WinError(c.get_last_error())
        try:
            assigned = w.BOOL()
            if not self.kernel.IsProcessInJob(handle, self.handle, c.byref(assigned)):
                raise c.WinError(c.get_last_error())
            if assigned.value:
                return
            if not self.kernel.AssignProcessToJobObject(self.handle, handle):
                raise c.WinError(c.get_last_error())
        finally:
            self.kernel.CloseHandle(handle)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class AnalysisProcess:
    """Workers wait at a gate until their entire launch family has an owner."""
    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.close()

    def __init__(self, command: list[str], *, folder: Path, env: dict):
        self.job = _WindowsJob() if os.name == 'nt' else None
        self.process = None
        try:
            with (folder / 'stderr.log').open('wb') as error:
                self.process = subprocess.Popen(command, cwd=folder, env=env, stdout=subprocess.DEVNULL,
                                                stderr=error, start_new_session=os.name != 'nt')
            if self.job:
                self.job.assign(self.process.pid)
                # Windows venv launchers can already have spawned their Python child.
                # The analysis gate forbids further launches until both are assigned.
                for child in psutil.Process(self.process.pid).children(recursive=True):
                    self.job.assign(child.pid)
        except BaseException:
            self.close()
            raise

    @property
    def pid(self):
        return self.process.pid

    def poll(self):
        return self.process.poll()

    def rss(self):
        try:
            parent = psutil.Process(self.pid)
            return sum(p.memory_info().rss for p in [parent, *parent.children(recursive=True)])
        except psutil.NoSuchProcess:
            return 0
        except psutil.AccessDenied as exc:
            raise RuntimeError('Cannot observe the owned analysis resource budget') from exc

    def close(self):
        family = []
        if self.process:
            try:
                parent = psutil.Process(self.pid)
                family = [*parent.children(recursive=True), parent]
            except psutil.Error:
                pass
        if self.job:
            self.job.close()
        elif self.process:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.process:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        # Also cover a failed assignment before a startup gate was released.
        for member in family:
            try: member.kill()
            except psutil.NoSuchProcess: pass
        _, alive = psutil.wait_procs(family, timeout=10)
        if alive:
            raise RuntimeError('Owned analysis process tree did not terminate')
