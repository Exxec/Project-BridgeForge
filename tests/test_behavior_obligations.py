"""S3 static plans retain missing behavior and refuse stale or unbound discovery."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bridgeforge import behavior_obligations as obligations
from bridgeforge.case_identity import digest, tree_files
from tests.support import resolved_temp_dir
from tests.test_case_qualification import fixture


def feature(root: Path, name: str = 'sample') -> Path:
    path = root / 'data' / 'world' / 'factions' / f'{name}.faction'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'id': name}), encoding='utf-8')
    return path


class BehaviorObligationTests(unittest.TestCase):
    def test_real_discovery_stable_unknown_and_read_only(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            feature(view.original); feature(view.working)
            before = tree_files(view.root)
            candidate = store.add_candidate(case, inputs=inputs)
            first = obligations.plan_behavior_obligations(store, case, candidate['record_id'])
            second = obligations.plan_behavior_obligations(store, case, candidate['record_id'])
            self.assertEqual(first, second)
            content = {key: value for key, value in first.items() if key != 'plan_id'}
            self.assertEqual(first['plan_id'], digest(content))
            self.assertEqual(first['state'], 'INCOMPLETE')
            self.assertEqual(first['qualification'], 'NOT_EVALUATED')
            self.assertEqual(first['reference']['runtime'], 'UNAVAILABLE')
            self.assertTrue(first['obligations'])
            for item in first['obligations']:
                self.assertEqual(item['status'], 'UNKNOWN')
                self.assertEqual(item['discovery'], 'BOTH')
                self.assertEqual(item['deviation_authority'], 'NONE')
                self.assertEqual(item['required_families'], list(obligations.FAMILIES))
            self.assertEqual(tree_files(view.root), before)

    def test_removed_and_added_features_stay_visible(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            feature(view.original, 'removed'); feature(view.working, 'added')
            candidate = store.add_candidate(case, inputs=inputs)
            report = obligations.plan_behavior_obligations(store, case, candidate['record_id'])
            roles = {item['discovery'] for item in report['obligations']}
            self.assertIn('ORIGINAL_ONLY', roles)
            self.assertIn('CANDIDATE_ONLY', roles)
            self.assertTrue(all(item['status'] == 'UNKNOWN' for item in report['obligations']))

    def test_empty_inventory_is_not_complete_coverage(self):
        with resolved_temp_dir() as root:
            store, case, _, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            report = obligations.plan_behavior_obligations(store, case, candidate['record_id'])
            self.assertEqual(report['obligations'], [])
            self.assertEqual(report['state'], 'INCOMPLETE')
            self.assertTrue(report['residual_human_tests'])
            for controls in report['family_controls'].values():
                self.assertEqual(controls, {'healthy': 'NOT_OBSERVED', 'known_bug': 'NOT_OBSERVED'})

    def test_changed_candidate_core_provider_and_rule_refuse_before_discovery(self):
        for role in ('working', 'core', 'dependencies', 'rules'):
            with self.subTest(role=role), resolved_temp_dir() as root:
                store, case, view, inputs = fixture(root)
                if role in ('dependencies', 'rules'):
                    path = root / 'bound'; path.mkdir()
                    (path / 'identity.txt').write_text('before')
                    inputs[role] = {'selected': path}
                elif role == 'core':
                    path = inputs['core']['starsector']
                else:
                    path = view.working
                candidate = store.add_candidate(case, inputs=inputs)
                (path / 'identity.txt').write_text('after')
                with patch.object(obligations, '_models', side_effect=AssertionError('no stale discovery')):
                    with self.assertRaisesRegex(ValueError, 'current candidate'):
                        obligations.plan_behavior_obligations(store, case, candidate['record_id'])

    def test_mutation_during_discovery_refuses(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            actual = obligations._models
            def mutate(*args):
                value = actual(*args)
                (view.working / 'changed.txt').write_text('concurrent edit')
                return value
            with patch.object(obligations, '_models', side_effect=mutate):
                with self.assertRaisesRegex(ValueError, 'current candidate'):
                    obligations.plan_behavior_obligations(store, case, candidate['record_id'])

    def test_java_needs_bound_configured_jdk(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            (view.working / 'Example.java').write_text('class Example {}')
            candidate = store.add_candidate(case, inputs=inputs)
            with patch.object(obligations, 'find_jdk', return_value=None), patch.object(obligations, '_models') as model:
                with self.assertRaisesRegex(ValueError, 'bound configured JDK'):
                    obligations.plan_behavior_obligations(store, case, candidate['record_id'])
                model.assert_not_called()

    def test_python_cannot_be_unbound(self):
        with resolved_temp_dir() as root:
            store, case, _, inputs = fixture(root); inputs['tools'] = {}
            candidate = store.add_candidate(case, inputs=inputs)
            with self.assertRaisesRegex(ValueError, 'bound running Python'):
                obligations.plan_behavior_obligations(store, case, candidate['record_id'])

    def test_explicit_provider_boundary_reaches_existing_scanner(self):
        from bridgeforge import behavior_discovery
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            with patch.object(behavior_discovery, 'scan_mod', wraps=behavior_discovery.scan_mod) as scan:
                obligations.plan_behavior_obligations(store, case, candidate['record_id'])
            self.assertEqual([call.kwargs['provider_roots'] for call in scan.call_args_list],
                             [[view.original], [view.working]])

    def test_implementation_change_during_discovery_refuses(self):
        with resolved_temp_dir() as root:
            store, case, _, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            with patch.object(obligations, 'engine_identity', side_effect=['a' * 64, 'b' * 64]):
                with self.assertRaisesRegex(ValueError, 'implementation changed'):
                    obligations.plan_behavior_obligations(store, case, candidate['record_id'])
