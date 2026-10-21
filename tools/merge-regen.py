"""Git merge driver for generated files (ROADMAP-3 item 80.1): take THEIRS, remember that a regeneration is needed.

One-time setup per clone (`.gitattributes` already marks the files with `merge=bfregen`):

    git config merge.bfregen.name "regenerate generated files"
    git config merge.bfregen.driver "python tools/merge-regen.py %O %A %B %P"

Git calls the driver only when both sides changed the file. The driver copies the other side's version over the current one
(%A), exits 0 (no conflict) and appends the path to `<git-dir>/bf-regen-needed`. Run `python tools/regen-generated.py`
afterwards: it regenerates the files from the merged source and clears the marker. The tests that compare the files with the
source (test_cli_golden, test_checks_index) stay the backstop: a stale file still fails CI.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

MARKER_NAME = "bf-regen-needed"


def git_dir(cwd: Path | None = None) -> Path:
    out = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], capture_output=True, text=True, check=True, cwd=cwd)
    return Path(out.stdout.strip())


def record_needed(marker: Path, path: str) -> None:
    known = marker.read_text(encoding="utf-8").splitlines() if marker.exists() else []
    if path not in known:
        marker.write_text("\n".join([*known, path]) + "\n", encoding="utf-8", newline="\n")


def merge(ancestor: str, current: str, other: str, path: str, marker: Path) -> int:
    shutil.copyfile(other, current)
    record_needed(marker, path)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: merge-regen.py %O %A %B %P", file=sys.stderr)
        return 2
    ancestor, current, other, path = argv
    return merge(ancestor, current, other, path, git_dir() / MARKER_NAME)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
