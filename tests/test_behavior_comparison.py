"""Self-authored comparison fixtures are not live evidence or owner approvals."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import unittest
from unittest.mock import Mock, patch

from bridgeforge import behavior_comparison as api
from bridgeforge.case_identity import digest, file_digest
from bridgeforge.cli import main
from bridgeforge.safeio import atomic_write_json
from tests.support import resolved_temp_dir


def endpoint(root, label, *, count=1, minimum=1, maximum=1, state='ASSERTIONS_OBSERVED'):
    artifact = root / (label + '.log')
    artifact.write_text('SELF-AUTHORED UNIT FIXTURE, NOT GAME OUTPUT')
    row = {'assertion': {'check': '^fixture-action$', 'status': 'INFO', 'subject_pattern': '^fixture$',
                         'min_count': minimum, 'max_count': maximum}, 'matched_count': count,
           'status': 'PASS' if state == 'ASSERTIONS_OBSERVED' else 'FAIL'}
    body = {'state': state, 'family': 'generation', 'behavior_ids': ['fixture.callback'],
            'artifacts': {str(artifact): file_digest(artifact)},
            'scenario_result': {'probe_assertions': [row]}}
    observation = {**body, 'observation_id': digest({'label': label, 'body': body})}
    store = Mock()
    store.assess_candidate.return_value = {'state': 'CURRENT'}
    return store, {'case_id': ('1' if label == 'candidate' else '2') * 32, 'candidate_id': '3' * 64}, observation


class ComparisonTests(unittest.TestCase):
    def compare(self, candidate, reference=None, *, deviation=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(api, 'engine_identity', return_value='e' * 64))
            stack.enter_context(patch.object(api, '_endpoint', side_effect=[candidate] + ([reference] if reference else [])))
            stack.enter_context(patch.object(api, '_mod_id', return_value='self-authored-fixture'))
            return api.compare_behavior_scenarios({'synthetic': 'candidate'}, {'synthetic': 'reference'} if reference else None,
                                                  deviation=deviation)

    def test_match_is_not_feature_or_save_qualification(self):
        with resolved_temp_dir() as root:
            value = self.compare(endpoint(root, 'candidate'), endpoint(root, 'reference'))
            self.assertEqual(value['state'], 'ASSERTION_VECTOR_MATCH')
            self.assertTrue(value['comparison_performed'])
            self.assertEqual(value['feature_preservation'], 'UNKNOWN')
            self.assertEqual(value['qualification'], 'NOT_EVALUATED')
            self.assertEqual(value['save_upgrade'], 'NOT_EVALUATED')

    def test_missing_or_failed_reference_never_means_preserved(self):
        with resolved_temp_dir() as root:
            candidate = endpoint(root, 'candidate')
            self.assertEqual(self.compare(candidate)['state'], 'REFERENCE_UNAVAILABLE')
            self.assertEqual(self.compare(candidate, endpoint(root, 'reference', state='REGRESSION_DETECTED'))['state'], 'REFERENCE_INCOMPLETE')

    def test_failed_assertion_cannot_be_waived_by_a_deviation(self):
        with resolved_temp_dir() as root:
            candidate = endpoint(root, 'candidate', count=2, state='REGRESSION_DETECTED')
            reference = endpoint(root, 'reference')
            self.assertEqual(self.compare(candidate, reference)['state'], 'REGRESSION_DETECTED')
            with self.assertRaisesRegex(ValueError, 'waive failed assertions'):
                self.compare(candidate, reference, deviation=root / 'not-even-read.json')

    def test_deviation_binds_exact_vectors_and_revocation(self):
        with resolved_temp_dir() as root:
            candidate = endpoint(root, 'candidate', count=2, minimum=2, maximum=2)
            reference = endpoint(root, 'reference')
            first = self.compare(candidate, reference)
            self.assertEqual(first['state'], 'OBSERVED_DIFFERENCE')
            path = root / 'synthetic-owner-decision.json'
            decision = {'schema_version': 1, 'scope': api.SCOPE, 'subject_id': first['subject_id'],
                        'actor': 'OWNER', 'decision': 'APPROVE_EXACT_SCENARIO_DEVIATION',
                        'reason': 'Self-authored unit test only', 'owner_words': 'Synthetic fixture, not an actual approval'}
            atomic_write_json(path, decision)
            self.assertEqual(self.compare(candidate, reference, deviation=path)['state'], 'EXPECTED_SCOPED_DEVIATION')
            decision['decision'] = 'REVOKE'; atomic_write_json(path, decision)
            self.assertEqual(self.compare(candidate, reference, deviation=path)['state'], 'OBSERVED_DIFFERENCE')
            decision['subject_id'] = '0' * 64; atomic_write_json(path, decision)
            with self.assertRaisesRegex(ValueError, 'exact subject'):
                self.compare(candidate, reference, deviation=path)

    def test_incomparable_family_predicate_or_feature_requires_new_design(self):
        with resolved_temp_dir() as root:
            candidate, reference = endpoint(root, 'candidate'), endpoint(root, 'reference')
            for change in ('family', 'behavior_ids', 'predicate'):
                other = deepcopy(reference[2])
                if change == 'predicate':
                    other['scenario_result']['probe_assertions'][0]['assertion']['check'] = '^another-action$'
                else:
                    other[change] = 'combat-callbacks' if change == 'family' else ['other.feature']
                with self.assertRaisesRegex(ValueError, 'Incomparable'):
                    self.compare(candidate, (reference[0], reference[1], other))

    def test_artifact_or_candidate_drift_refuses_comparison(self):
        with resolved_temp_dir() as root:
            candidate, reference = endpoint(root, 'candidate'), endpoint(root, 'reference')
            reference[0].assess_candidate.return_value = {'state': 'STALE'}
            with self.assertRaisesRegex(ValueError, 'stale'):
                self.compare(candidate, reference)
            reference[0].assess_candidate.return_value = {'state': 'CURRENT'}
            (root / 'reference.log').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'evidence changed'):
                self.compare(candidate, reference)

    def test_selector_rejects_generic_pass_and_relative_paths(self):
        for value in ({'PASS': True}, {'store': 'relative', 'rig': 'relative', 'case_id': '1' * 32,
                                     'candidate_id': '2' * 64, 'scenario': 'fixture', 'run_id': 'fixture'}):
            with self.assertRaises(ValueError):
                api._endpoint(value)

    def test_cli_schema_refusal_and_scoped_success(self):
        with resolved_temp_dir() as root:
            path = root / 'selection.json'
            atomic_write_json(path, {'schema_version': True, 'candidate': {}, 'reference': None})
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(['case-behavior-compare', str(path)]), 2)
            atomic_write_json(path, {'schema_version': 1, 'candidate': {}, 'reference': None})
            with patch('bridgeforge.cmd_behavior_comparison.compare_behavior_scenarios', return_value={
                    'state': 'ASSERTION_VECTOR_MATCH', 'qualification': 'NOT_EVALUATED'}), redirect_stdout(io.StringIO()):
                self.assertEqual(main(['case-behavior-compare', str(path), '--json']), 0)
