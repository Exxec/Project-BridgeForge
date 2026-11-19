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


def select(cases: list[unittest.TestCase], slow: set[str], partition: str, *, subset: bool = False) -> list[unittest.TestCase]:
    """`subset`: the cases are some modules only (the pre-push, 96.5 C5), so slow ids of other modules are not stale."""
    ids = [case.id() for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate discovered test IDs')
    stale = slow - set(ids)
    if stale and not subset:
        raise ValueError('Unknown slow-test IDs: ' + ', '.join(sorted(stale)))
    if partition not in {'all', 'fast', 'slow'}:
        raise ValueError('Unknown partition: ' + partition)
    return [case for case in cases if partition == 'all' or ((case.id() in slow) == (partition == 'slow'))]


def module_cases(modules: list[str]) -> list[unittest.TestCase]:
    """The cases of some test modules, named as discovery names them (`test_x.Class.method`, the ids slow_tests.json uses).
    Discovery imports them with tests/ first on sys.path, as here."""
    import sys

    for folder in (str(ROOT), str(ROOT / 'tests')):
        if folder not in sys.path:
            sys.path.insert(0, folder)
    names = [name.removeprefix('tests.') for name in modules]
    return list(flatten(unittest.defaultTestLoader.loadTestsFromNames(names)))


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
    parser.add_argument('--modules', nargs='+', metavar='MODULE',
                        help='only these test modules (tests.test_x or test_x), as the pre-push selects them (96.5 C5)')
    args = parser.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    cases = module_cases(args.modules) if args.modules else list(flatten(unittest.defaultTestLoader.discover(str(ROOT / 'tests'))))
    try:
        chosen = select(cases, set(manifest['tests']), args.partition, subset=bool(args.modules))
    except ValueError as exc:
        parser.error(str(exc))
    print(f'{args.partition}: {len(chosen)} / {len(cases)} discovered cases', flush=True)
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=1, resultclass=TimedResult, buffer=True).run(unittest.TestSuite(chosen))
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
