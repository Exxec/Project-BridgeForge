"""S3 assertion controls use synthetic R1 runs, never live-game evidence."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bridgeforge import behavior_observations as observations, scenarios
from bridgeforge.behavior_obligations import plan_behavior_obligations
from bridgeforge.case_identity import digest
from bridgeforge.run_manifest import prepare_run, release_run
from tests import test_case_qualification as qualification
from tests.test_behavior_obligations import feature
from tests.support import resolved_temp_dir


def prepare(root, *, healthy=True, definition_edit=None, named=True):
    original = qualification.fixture
    def seeded(*args, **kwargs):
        result = original(*args, **kwargs)
        feature(result[2].original); feature(result[2].working)
        return result
    with patch.object(qualification, 'fixture', side_effect=seeded):
        store, case, prior, view, rig, old = qualification.BoundLiveQualificationTests().prepare(root)
    seed = plan_behavior_obligations(store, case, prior['record_id'])
    defs = root / 'definitions'; defs.mkdir()
    definition = {'schema_version': 1, 'name': 'synthetic-s3', 'family': 'generation',
                  'behavior_ids': [item['behavior_id'] for item in seed['obligations']],
                  'subject_mod': 'synthetic-s1', 'mods': ['synthetic-s1'],
                  'expect': {'probe': [{'check': '^feature-check$', 'status': 'OK',
                                       'subject_pattern': '^synthetic-s1$', 'min_count': 1}], 'save': []}}
    if definition_edit: definition_edit(definition)
    path = defs / 'synthetic-s3.json'; path.write_text(json.dumps(definition))
    groups = prior['content']['context']['inputs']
    inputs = {role: None if group is None else {key: Path(item['path']) for key, item in group.items()}
              for role, group in groups.items()}
    inputs['rules']['scenario.synthetic-s3'] = path
    candidate = store.add_candidate(case, inputs=inputs, predecessor=prior['record_id'])
    plan = plan_behavior_obligations(store, case, candidate['record_id'])
    manifest = prepare_run(rig, 'S3-CONTROL', 'live', targets=['synthetic-s1'],
                           expected=old['expected_milestones'], scenario='synthetic-s3' if named else '',
                           launcher=rig / 'game.bat')
    lines = Path(old['log']).read_text().splitlines()
    lines = [line for line in lines if 'manifest_id=' not in line]
    lines += ['BF-PROBE|0.3.2|run|manifest_id=' + manifest['manifest_id']]
    lines += ['BF-PROBE|0.3.2|feature-check|OK|' + ('synthetic-s1' if healthy else 'other-mod') + '|observed']
    Path(manifest['log']).write_text('\n'.join(lines) + '\n')
    release_run(rig, manifest['run_id'], launcher=rig / 'game.bat')
    return store, case, candidate, plan, rig, manifest, defs


def observe(parts):
    store, case, candidate, plan, rig, manifest, defs = parts
    return observations.observe_behavior_scenario(store, case, candidate['record_id'], plan,
                scenario='synthetic-s3', rig=rig, run_id=manifest['run_id'], definition_directory=defs)


class BehaviorObservationTests(unittest.TestCase):
    def test_healthy_assertions_are_observed_without_equivalence_or_acceptance(self):
        with resolved_temp_dir() as root:
            report = observe(prepare(root))
            self.assertEqual(report['state'], 'ASSERTIONS_OBSERVED', report)
            self.assertEqual(report['feature_preservation'], 'UNKNOWN')
            self.assertEqual(report['qualification'], 'NOT_EVALUATED')
            self.assertEqual(report['reference_observation'], 'UNAVAILABLE')
            self.assertTrue(report['residual_human_tests'])
            self.assertEqual(report['observation_id'], digest({k: v for k, v in report.items() if k != 'observation_id'}))

    def test_planted_wrong_subject_is_detected(self):
        with resolved_temp_dir() as root:
            report = observe(prepare(root, healthy=False))
            self.assertEqual(report['state'], 'REGRESSION_DETECTED', report)
            self.assertEqual(report['scenario_result']['status'], 'FAIL')
            self.assertEqual(report['scenario_result']['probe_assertions'][0]['matched_count'], 0)
            self.assertEqual(report['family_control_qualification'], 'NOT_EVALUATED')

    def test_vacuous_absence_only_boolean_and_unscoped_assertions_refuse(self):
        edits = [lambda d: d['expect'].update(probe=[]),
                 lambda d: d['expect']['probe'][0].update(min_count=0, max_count=0),
                 lambda d: d['expect']['probe'][0].update(min_count=True),
                 lambda d: d['expect']['probe'][0].update(check='*'),
                 lambda d: d['expect']['probe'][0].update(status='*')]
        for edit in edits:
            with self.subTest(edit=edit), resolved_temp_dir() as root:
                parts = prepare(root, definition_edit=edit)
                with self.assertRaises(ValueError): observe(parts)

    def test_save_setup_and_unknown_feature_definitions_refuse(self):
        edits = [lambda d: d.update(family='upgrade-reload'),
                 lambda d: d.update(probe_setups=['spawn-fixture']),
                 lambda d: d['expect'].update(save=[{'class': 'Example'}]),
                 lambda d: d.update(behavior_ids=['not-in-plan']),
                 lambda d: d.update(compat_set='libs')]
        for edit in edits:
            with self.subTest(edit=edit), resolved_temp_dir() as root:
                with self.assertRaises(ValueError): observe(prepare(root, definition_edit=edit))

    def test_named_run_is_required(self):
        with resolved_temp_dir() as root:
            with self.assertRaisesRegex(ValueError, 'prepared for this named'):
                observe(prepare(root, named=False))

    def test_rehashed_forged_plan_and_changed_definition_refuse(self):
        with resolved_temp_dir() as root:
            parts = list(prepare(root)); altered = copy.deepcopy(parts[3])
            altered['obligations'][0]['status'] = 'PASS'
            altered['plan_id'] = digest({k: v for k, v in altered.items() if k != 'plan_id'})
            parts[3] = altered
            with self.assertRaisesRegex(ValueError, 'stale, altered'): observe(parts)
        with resolved_temp_dir() as root:
            parts = prepare(root); (parts[-1] / 'synthetic-s3.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'current candidate'): observe(parts)

    def test_staged_drift_and_missing_echo_refuse_observation(self):
        for mutation in ('staged', 'echo'):
            with self.subTest(mutation=mutation), resolved_temp_dir() as root:
                parts = prepare(root); rig, manifest = parts[4:6]
                if mutation == 'staged':
                    (next(path for path in (rig / 'mods').iterdir() if path.is_dir()) / 'drift.txt').write_text('changed')
                else:
                    log = Path(manifest['log']); log.write_text('\n'.join(l for l in log.read_text().splitlines() if 'manifest_id=' not in l))
                self.assertEqual(observe(parts)['state'], 'REFUSED')

    def test_artifact_mutation_during_assertion_check_refuses(self):
        with resolved_temp_dir() as root:
            parts = prepare(root); actual = scenarios.scenario_check
            def mutate(*args, **kwargs):
                report = actual(*args, **kwargs); Path(parts[5]['log']).write_text('concurrent log edit'); return report
            with patch.object(scenarios, 'scenario_check', side_effect=mutate):
                with self.assertRaisesRegex(ValueError, 'changed during evaluation'): observe(parts)


class ExternalCatalogTests(unittest.TestCase):
    def test_external_catalog_is_explicit_and_cannot_override_bound_definition(self):
        with resolved_temp_dir() as root:
            parts = prepare(root); store, case, candidate, plan, rig, manifest, defs = parts
            with self.assertRaisesRegex(ValueError, 'bound in candidate rules'):
                observations.observe_behavior_scenario(store, case, candidate['record_id'], plan,
                    scenario='synthetic-s3', rig=rig, run_id=manifest['run_id'])
            other = root / 'other'; other.mkdir()
            (other / 'synthetic-s3.json').write_text((defs / 'synthetic-s3.json').read_text())
            with self.assertRaisesRegex(ValueError, 'bound in candidate rules'):
                observations.observe_behavior_scenario(store, case, candidate['record_id'], plan,
                    scenario='synthetic-s3', rig=rig, run_id=manifest['run_id'], definition_directory=other)
            self.assertEqual(observe(parts)['state'], 'ASSERTIONS_OBSERVED')

    def test_live_runner_forwards_explicit_named_scenario(self):
        from contextlib import contextmanager
        from bridgeforge.live import live_run
        @contextmanager
        def running(*args, **kwargs):
            self.assertEqual(kwargs['scenario'], 'synthetic-s3')
            yield Path('unused.log'), None, 14
        result = live_run.LiveResult('LIVE_DONE')
        with patch.object(live_run, 'running_game', running), patch.object(live_run, 'drive', return_value=result):
            self.assertIs(live_run.live_run(Path('unused-rig'), 'R-S3', scenario='synthetic-s3'), result)
