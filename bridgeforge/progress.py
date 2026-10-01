"""Progress and resume for commands that walk a whole queue or archive (house rule since 2026-09-27).

A long run must say what it is doing as it goes and must not lose finished work when it is
interrupted: `finding-stats --scan` ran 44 minutes over 305 workspaces with no output, and
`dependency-graph` and `corpus-index build` did the same, each keeping every result in memory
until the end.

`Checkpoint` is an append-only JSONL file. Its first line is a header naming the run's inputs; a
later run with the same header reuses every record already written and skips that work, and any
other header starts afresh. A line cut short by an interrupted write is ignored. `report` prints the
one-line-per-item progress format the commands share.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


class Checkpoint:
    def __init__(self, path: Path | None, header: dict):
        self.path, self.header = path, header
        self.done: dict[str, dict] = self._load() if path else {}
        self._out = None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not self.done:
                path.write_text(json.dumps(header) + "\n", encoding="utf-8")
            self._out = path.open("a", encoding="utf-8")

    def _load(self) -> dict[str, dict]:
        if not self.path.is_file():
            return {}
        lines = self.path.read_text(encoding="utf-8").splitlines()
        try:
            if not lines or json.loads(lines[0]) != self.header:
                return {}
        except json.JSONDecodeError:
            return {}
        records = {}
        for line in lines[1:]:
            try:
                record = json.loads(line)
                records[record["key"]] = record["value"]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue  # a line cut short by an interrupted run
        return records

    def get(self, key: str) -> dict | None:
        return self.done.get(key)

    def add(self, key: str, value: dict) -> None:
        if self._out:
            self._out.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
            self._out.flush()

    def close(self) -> None:
        if self._out:
            self._out.close()
            self._out = None

    def finish(self) -> None:
        """The run completed and its full result was written elsewhere: drop the checkpoint."""
        self.close()
        if self.path and self.path.is_file():
            self.path.unlink()

    def __enter__(self) -> Checkpoint:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def report(done: int, total: int, name: str, detail: str, seconds: float | None) -> None:
    """`[12/305] Batavia: 174 finding(s) (38.2s)`; `seconds=None` marks an item taken from a checkpoint."""
    tail = " (from checkpoint)" if seconds is None else f" ({seconds:.1f}s)"
    print(f"[{done}/{total}] {name}: {detail}{tail}", file=sys.stderr, flush=True)


# Commands that walk a whole queue or archive. Each must print per-item progress (and offer --quiet)
# and resume from a checkpoint; tests/test_progress.py holds every entry to that. Add new ones here.
LONG_RUNNING_COMMANDS = (
    ("finding-stats",),
    ("dependency-graph",),
    ("corpus-recheck",),
    ("corpus-index", "build"),
    ("supersession",),
    ("escalation", "queue"),
    ("revive-queue",),
    ("check-impact",),
    ("relink",),
    ("port-interfaces",),
)
