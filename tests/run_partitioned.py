"""B5: profile or partition unittest cases without changing normal discovery."""
from __future__ import annotations

import argparse
from collections.abc import Iterator
import json
from pathlib import Path
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'tests' / 'slow_tests.json'


def flatten(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def select(cases: list[unittest.TestCase], slow: set[str], partition: str) -> list[unittest.TestCase]:
    ids = [case.id() for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate discovered test IDs')
    stale = slow - set(ids)
    if stale:
        raise ValueError('Unknown slow-test IDs: ' + ', '.join(sorted(stale)))
    if partition not in {'all', 'fast', 'slow'}:
        raise ValueError('Unknown partition: ' + partition)
    return [case for case in cases if partition == 'all' or ((case.id() in slow) == (partition == 'slow'))]


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seconds: dict[str, float] = {}
        self.started: float = 0

    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.seconds[test.id()] = time.perf_counter() - self.started
        super().stopTest(test)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partition', choices=('all', 'fast', 'slow'), default='all')
    parser.add_argument('--timings', type=Path, help='JSON report outside the tracked checkout (CI uses runner.temp)')
    args = parser.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    cases = list(flatten(unittest.defaultTestLoader.discover(str(ROOT / 'tests'))))
    try:
        chosen = select(cases, set(manifest['tests']), args.partition)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'{args.partition}: {len(chosen)} / {len(cases)} discovered cases', flush=True)
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=1, resultclass=TimedResult).run(unittest.TestSuite(chosen))
    elapsed = time.perf_counter() - started
    print(f'{args.partition} suite wall time: {elapsed:.3f}s', flush=True)
    if args.timings:
        report = {'partition': args.partition, 'discovered': len(cases), 'selected': len(chosen),
                  'run': result.testsRun, 'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
                  'wall_seconds': elapsed, 'seconds': result.seconds}
        args.timings.parent.mkdir(parents=True, exist_ok=True)
        args.timings.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
