"""B5 partition completeness, stale-marker refusal and timing failure semantics."""
from __future__ import annotations

import io
import unittest

from tests.run_partitioned import TimedResult, flatten, select


class PartitionTests(unittest.TestCase):
    def test_partitions_are_disjoint_complete_and_preserve_order(self):
        cases = [unittest.TestCase('runTest'), PartitionTests('test_new_cases_default_to_fast')]
        slow = {cases[1].id()}
        fast_cases = select(cases, slow, 'fast')
        slow_cases = select(cases, slow, 'slow')
        self.assertEqual(fast_cases, cases[:1])
        self.assertEqual(slow_cases, cases[1:])
        self.assertEqual(select(cases, slow, 'all'), cases)
        self.assertFalse({c.id() for c in fast_cases} & {c.id() for c in slow_cases})
        self.assertEqual(set(cases), set(fast_cases + slow_cases))

    def test_new_cases_default_to_fast(self):
        case = unittest.TestCase('runTest')
        self.assertEqual(select([case], set(), 'fast'), [case])
        self.assertEqual(select([case], set(), 'slow'), [])

    def test_stale_markers_and_duplicate_ids_are_errors(self):
        case = unittest.TestCase('runTest')
        with self.assertRaisesRegex(ValueError, 'Unknown slow-test IDs'):
            select([case], {'removed.test'}, 'fast')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            select([case, case], set(), 'all')

    def test_nested_suites_flatten_without_dropping_cases(self):
        case = unittest.TestCase('runTest')
        self.assertEqual(list(flatten(unittest.TestSuite([unittest.TestSuite([case])]))), [case])

    def test_timing_keeps_failure_and_skip_outcomes(self):
        class Outcomes(unittest.TestCase):
            def test_failure(self):
                self.fail('expected fixture failure')

            @unittest.skip('expected fixture skip')
            def test_skip(self):
                pass
        cases = list(flatten(unittest.defaultTestLoader.loadTestsFromTestCase(Outcomes)))
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=TimedResult).run(unittest.TestSuite(cases))
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.testsRun, 2)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(set(result.seconds), {case.id() for case in cases})
        self.assertTrue(all(seconds >= 0 for seconds in result.seconds.values()))
