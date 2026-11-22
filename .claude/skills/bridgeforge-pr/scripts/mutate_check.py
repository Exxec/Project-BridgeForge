"""Mutation check: replace one exact snippet in a module, run one test, restore the module. Prints the test outcome.

Usage: python mutate_check.py MODULE_PATH OLD NEW TEST_SELECTOR   (run from the checkout root; OLD must occur exactly once)

The selector runs unmutated first and must pass with at least one test: otherwise a mistyped selector or a module that
does not import would read as "the test catches the mutation" (a Project Go driver printed void kills that way,
2026-11-22). A mutant that stops the tests loading is reported as invalid, not as caught.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_RAN = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)
# What unittest prints when a test module cannot be imported or a name in the selector does not exist.
_NOT_LOADED = ("unittest.loader._FailedTest", "Failed to import test module")


def _run(selector: str) -> tuple[int, int, str]:
    """(exit code, tests run, stderr) of one unittest run."""
    done = subprocess.run([sys.executable, "-m", "unittest", selector], capture_output=True, text=True, check=False)
    ran = _RAN.search(done.stderr)
    return done.returncode, int(ran.group(1)) if ran else 0, done.stderr


def main(module: str, old: str, new: str, selector: str) -> int:
    # An argument starting with @ names a file holding the snippet (shell quoting mangles backslashes).
    old = Path(old[1:]).read_text(encoding="utf-8").rstrip("\n") if old.startswith("@") else old
    new = Path(new[1:]).read_text(encoding="utf-8").rstrip("\n") if new.startswith("@") else new
    path = Path(module)
    original = path.read_bytes()
    text = original.decode("utf-8")
    if text.count(old) != 1:
        print(f"snippet found {text.count(old)} times, expected 1: nothing run")
        return 2
    code, ran, stderr = _run(selector)
    if code or not ran or any(marker in stderr for marker in _NOT_LOADED):
        print(f"the unmutated selector does not pass ({ran} tests ran, exit {code}): nothing counts")
        print(stderr[-600:])
        return 2
    try:
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        code, ran, stderr = _run(selector)
    finally:
        path.write_bytes(original)
    if not ran or any(marker in stderr for marker in _NOT_LOADED):
        print("mutant INVALID: the tests no longer load (rewrite the mutant; this proves nothing)")
    elif code:
        print(f"mutated test FAILS (the test catches the mutation; {ran} tests ran)")
    else:
        print(f"mutated test PASSES (the test misses the mutation; {ran} tests ran)")
    print("\n".join(line for line in stderr.splitlines() if line.startswith(("FAIL", "ERROR", "AssertionError")))[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
