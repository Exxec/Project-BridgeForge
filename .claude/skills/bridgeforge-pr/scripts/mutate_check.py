"""Mutation check: replace one exact snippet in a module, run one test, restore the module. Prints the test outcome.

Usage: python mutate_check.py MODULE_PATH OLD NEW TEST_SELECTOR   (run from the checkout root; OLD must occur exactly once)

The selector runs unmutated first and must pass with at least one test that is not skipped. Otherwise a mistyped
selector or a module that does not import would read as "the test catches the mutation" (a Project Go driver printed
void kills that way, 2026-11-22). A mutant that stops the test module loading is reported as INVALID, not as caught.

Exit codes: 0 caught (FAILS), 1 missed (PASSES), 2 nothing run (snippet or baseline), 3 INVALID, 4 timed out.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_RAN = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)
_SKIPPED = re.compile(r"^(?:OK|FAILED) \(.*?\bskipped=(\d+)", re.MULTILINE)
# unittest's own lines when a test module cannot be imported or a name in the selector does not exist.
_NOT_LOADED = re.compile(r"^(?:ERROR: .*\(unittest\.loader\._FailedTest\.|ImportError: Failed to import test module)",
                         re.MULTILINE)
TIMEOUT_SECONDS = 900


def _run(selector: str) -> tuple[int, int, str]:
    """(exit code, tests run and not skipped, stderr) of one unittest run.

    Python trusts a .pyc whose recorded source mtime (whole seconds) and size match. So a same-length mutant written or
    restored within the second of a compile ran the wrong code (review 2026-11-22). The run therefore reads and writes
    bytecode only under an empty cache prefix: every module compiles from its source, and no .pyc is left behind.
    """
    with tempfile.TemporaryDirectory(prefix="mutate-check-pycache-") as empty_cache:
        done = subprocess.run([sys.executable, "-m", "unittest", selector], capture_output=True, text=True, check=False,
                              env=dict(os.environ, PYTHONPYCACHEPREFIX=empty_cache), timeout=TIMEOUT_SECONDS)
    ran = _RAN.search(done.stderr)
    skipped = _SKIPPED.search(done.stderr)
    executed = (int(ran.group(1)) if ran else 0) - (int(skipped.group(1)) if skipped else 0)
    return done.returncode, executed, done.stderr


def _snippet(path: str) -> str:
    """A snippet file's exact text, its line endings kept, without the line break that ends the file."""
    text = Path(path).read_bytes().decode("utf-8")
    return text[:-2] if text.endswith("\r\n") else text[:-1] if text.endswith("\n") else text


def main(module: str, old: str, new: str, selector: str) -> int:
    # An argument starting with @ names a file holding the snippet (shell quoting mangles backslashes).
    # Read as bytes: read_text turns CRLF into LF, so a multi-line snippet never matched a CRLF module (2026-11-22).
    old = _snippet(old[1:]) if old.startswith("@") else old
    new = _snippet(new[1:]) if new.startswith("@") else new
    path = Path(module)
    original = path.read_bytes()
    stamp = path.stat()
    text = original.decode("utf-8")
    if text.count(old) != 1:
        print(f"snippet found {text.count(old)} times, expected 1: nothing run")
        return 2
    code, executed, stderr = _run(selector)
    if code or executed < 1 or _NOT_LOADED.search(stderr):
        print(f"the unmutated selector does not pass ({executed} tests run and not skipped, exit {code}): nothing counts")
        print(stderr[-600:])
        return 2
    try:
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        code, executed, stderr = _run(selector)
    except subprocess.TimeoutExpired:
        print(f"mutated run TIMED OUT after {TIMEOUT_SECONDS} s: a hang, which counts only if a hang is what you meant")
        return 4
    finally:
        path.write_bytes(original)
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))  # the module as it was, mtime included
    if executed < 1 or _NOT_LOADED.search(stderr):
        print("mutant INVALID: the test module no longer loads (rewrite the mutant; this proves nothing)")
        return 3
    print("\n".join(line for line in stderr.splitlines() if line.startswith(("FAIL", "ERROR", "AssertionError")))[:600])
    if code:
        print(f"mutated test FAILS (the test catches the mutation; {executed} tests run)")
        return 0
    print(f"mutated test PASSES (the test misses the mutation; {executed} tests run)")
    return 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
