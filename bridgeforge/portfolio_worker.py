"""Private read-only portfolio worker; never a qualification/repair command."""
from __future__ import annotations

from contextlib import nullcontext
import json
import os
from pathlib import Path
import signal
import sys
from threading import Thread
import time

import psutil

from .analysis_reuse import reuse_parses
from .case_evidence import evaluate_request
from .case_qualification import engine_identity
from .safeio import atomic_write_json


def _watch_parent(pid: int, created: float):
    while True:
        try:
            alive = psutil.Process(pid).create_time() == created
        except psutil.Error:
            alive = False
        if not alive:
            os.killpg(os.getpgrp(), signal.SIGKILL)
        time.sleep(.1)


def main():
    folder = Path(sys.argv[1])
    request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    # Windows kernel job ownership handles parent loss; POSIX sessions need a watcher.
    if os.name != 'nt':
        Thread(target=_watch_parent, args=(request['parent_pid'], request['parent_created']), daemon=True).start()
    until = time.monotonic() + 30
    while not (folder / 'start.json').is_file():
        if time.monotonic() > until:
            raise SystemExit(125)
        time.sleep(.01)
    config = request['parse_reuse']
    if engine_identity() != request['engine_id']:
        raise ValueError('Analysis engine changed before worker execution')
    scope = reuse_parses(**config) if config else nullcontext()
    began = time.perf_counter()
    with scope as cache:
        raw = evaluate_request(request['scan'])
        if engine_identity() != request['engine_id']:
            raise ValueError('Analysis engine changed during worker execution')
        atomic_write_json(folder / 'response.json', raw)
        atomic_write_json(folder / 'metrics.json', {'seconds': time.perf_counter() - began,
                                                   'reuse': cache.stats() if cache else None})


if __name__ == '__main__':
    main()
