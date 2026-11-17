"""Mutation check: replace one exact snippet in a module, run one test, restore the module. Prints the test outcome.

Usage: python mutate_check.py MODULE_PATH OLD NEW TEST_SELECTOR   (run from the checkout root; OLD must occur exactly once)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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
    try:
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        done = subprocess.run([sys.executable, "-m", "unittest", selector], capture_output=True, text=True, check=False)
        verdict = "FAILS (the test catches the mutation)" if done.returncode else "PASSES (the test misses the mutation)"
        print(f"mutated test {verdict}")
        print("\n".join(line for line in done.stderr.splitlines() if line.startswith(("FAIL", "ERROR", "AssertionError")))[:600])
    finally:
        path.write_bytes(original)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
