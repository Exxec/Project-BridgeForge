"""S1 public command flow and observable refusal/exit contracts."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import unittest

from bridgeforge.cli import main
from tests import test_case_qualification as fixtures
from tests.support import resolved_temp_dir
from tests.test_case_workspace import snapshot


def invoke(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(['case', *map(str, argv)])
    return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()


def inputs_file(root, inputs):
    path = root / 'inputs.json'
    path.write_text(json.dumps({'schema_version': 1, 'inputs': {
        role: None if group is None else {name: str(value) for name, value in group.items()}
        for role, group in inputs.items()}}))
    return path


class CaseCliTests(unittest.TestCase):
    def test_open_retry_status_capture_and_stale_refusal(self):
        with resolved_temp_dir() as root:
            store, _, view, inputs = fixtures.fixture(root)
            path = inputs_file(root, inputs)
            case = 'f' * 32
            before = snapshot(view.root)
            args = ['open', view.root, '--store', store.root, '--inputs', path, '--case-id', case, '--json']
            code, opened, error = invoke(args)
            self.assertEqual(code, 0, error)
            self.assertEqual(invoke(args)[1], opened)
            self.assertEqual(snapshot(view.root), before)
            self.assertEqual(invoke(['status', case, '--store', store.root, '--json'])[1]['state'], 'CURRENT_INPUTS')
            (view.working / 'changed.txt').write_text('changed')
            code, result, _ = invoke(['status', case, '--store', store.root, '--json'])
            self.assertEqual(code, 1)
            self.assertEqual(result['candidates'][0]['state'], 'STALE')
            code, newer, error = invoke(['capture', case, '--store', store.root, '--inputs', path,
                                         '--predecessor', opened['candidate_id'], '--json'])
            self.assertEqual(code, 0, error)
            self.assertNotEqual(newer['candidate_id'], opened['candidate_id'])

    def test_missing_live_qualification_exit_and_paired_arguments(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixtures.fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)['record_id']
            args = ['qualify', case, candidate, '--store', store.root, '--json']
            code, value, _ = invoke(args)
            self.assertEqual(code, 1)
            self.assertEqual(value['dimensions']['live']['status'], 'INCOMPLETE')
            code, _, error = invoke([*args, '--rig', root / 'rig'])
            self.assertEqual(code, 2)
            self.assertIn('supplied together', error)

    def test_cli_prepare_finalize_and_retry_use_actual_shared_evaluator(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = fixtures.BoundLiveQualificationTests().prepare(root)
            code, prepared, error = invoke(['prepare', case, candidate['record_id'], '--store', store.root,
                                            '--archive-root', root / 'archives', '--json'])
            self.assertEqual(code, 0, error)
            args = ['finalize', case, prepared['operation_id'], '--store', store.root, '--rig', rig,
                    '--run-id', manifest['run_id'], '--json']
            code, finalized, error = invoke(args)
            self.assertEqual(code, 0, error)
            self.assertEqual(finalized['state'], 'COMPLETE')
            self.assertEqual(invoke(args)[1], finalized)
            self.assertTrue(Path(finalized['archive']).is_dir())
            code, current, _ = invoke(['status', case, '--store', store.root, '--json'])
            self.assertEqual(code, 0)
            self.assertEqual(current['operations'][0]['recorded_state'], 'COMPLETE')
            self.assertEqual(current['operations'][0]['authority'], 'HISTORICAL_CHECKPOINT_NOT_CURRENT_QUALIFICATION')

    def test_duplicate_relative_and_boolean_input_records_refuse_before_writes(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixtures.fixture(root)
            for text in ('{"schema_version":1,"schema_version":1,"inputs":{}}',
                         '{"schema_version":true,"inputs":{}}',
                         '{"schema_version":1,"inputs":{"tools":{"python":"relative.exe"}}}'):
                with self.subTest(record=text):
                    path = root / 'inputs.json'; path.write_text(text)
                    before = snapshot(store.root)
                    code, _, error = invoke(['open', view.root, '--store', store.root, '--inputs', path, '--json'])
                    self.assertEqual(code, 2, error)
                    self.assertEqual(snapshot(store.root), before)


    def test_prepare_run_manifest_matches_existing_unattended_harness(self):
        from bridgeforge import launch
        from bridgeforge.live.live_run import LIVE_EXPECTED_MILESTONES
        from bridgeforge.run_manifest import release_run
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = fixtures.BoundLiveQualificationTests().prepare(root)
            _, prepared, _ = invoke(['prepare', case, candidate['record_id'], '--store', store.root,
                                       '--archive-root', root / 'archives', '--json'])
            code, bound, error = invoke(['prepare-run', case, prepared['operation_id'], '--store', store.root,
                                         '--rig', rig, '--run-id', 'cli-harness', '--json'])
            self.assertEqual(code, 0, error)
            observed = launch.prepare_manifest(rig, 'cli-harness', 'live', targets=['synthetic-s1'],
                expected=list(LIVE_EXPECTED_MILESTONES), scenario='probe-group live', bat=rig / 'game.bat')
            self.assertEqual(observed['manifest_id'], bound['manifest_id'])
            release_run(rig, 'cli-harness', launcher=rig / 'game.bat')
