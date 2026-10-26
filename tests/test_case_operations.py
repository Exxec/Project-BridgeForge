"""S1 local archive operations preserve inputs and recover without trusting labels."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bridgeforge import case_operations as ops
from tests.support import resolved_temp_dir
from tests import test_case_qualification as qualification_tests
from tests.test_case_qualification import fixture
from tests.test_case_workspace import snapshot


class CaseOperationTests(unittest.TestCase):
    def test_prepare_is_idempotent_and_never_bumps_version(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            before = snapshot(view.root)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            self.assertEqual(ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives'), prepared)
            self.assertEqual(before, snapshot(view.root))
            self.assertFalse((root / 'archives').exists())

    def test_missing_live_refuses_without_publishing(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            result = ops.finalize_case(store, case, prepared['operation_id'])
            self.assertEqual(result['state'], 'REFUSED')
            self.assertFalse((root / 'archives').exists())

    def test_existing_archive_and_original_preserved_and_retry_exact(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = qualification_tests.BoundLiveQualificationTests().prepare(root)
            destination = root / 'archives'; destination.mkdir()
            (destination / 'prior.zip').write_bytes(b'prior archive')
            before = snapshot(view.root)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=destination)
            result = ops.finalize_case(store, case, prepared['operation_id'], live=(rig, manifest['run_id']))
            self.assertEqual(result['state'], 'COMPLETE', result)
            archived = snapshot(Path(result['archive']))
            retried = ops.finalize_case(store, case, prepared['operation_id'], live=(rig, manifest['run_id']))
            self.assertEqual(retried, result)
            self.assertEqual(snapshot(Path(result['archive'])), archived)
            self.assertEqual(snapshot(view.root), before)
            self.assertEqual((destination / 'prior.zip').read_bytes(), b'prior archive')

    def test_interruption_after_move_reconciles_only_recorded_bytes(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = qualification_tests.BoundLiveQualificationTests().prepare(root)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            original = ops._write
            def interrupt(path, value):
                if path.name == 'checkpoint.json' and value.get('state') == 'COMPLETE':
                    raise OSError('injected after publication')
                return original(path, value)
            with patch.object(ops, '_write', side_effect=interrupt):
                with self.assertRaisesRegex(OSError, 'injected'):
                    ops.finalize_case(store, case, prepared['operation_id'], live=(rig, manifest['run_id']))
            final = root / 'archives' / prepared['operation_id']
            before = snapshot(final)
            result = ops.finalize_case(store, case, prepared['operation_id'], live=(rig, manifest['run_id']))
            self.assertEqual(result['state'], 'COMPLETE')
            self.assertEqual(before, snapshot(final))

    def test_tampered_prepared_copy_and_destination_overlap_refused(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            for destination in [view.root / 'archives', store.root / 'archives', inputs['core']['starsector'] / 'archives']:
                with self.subTest(destination=destination), self.assertRaises(ops.OperationError):
                    ops.prepare_case(store, case, candidate['record_id'], archive_root=destination)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            operation = store.root / case / 'operations' / prepared['operation_id']
            working = operation / prepared['prepared_relative'] / 'working'
            (working / 'changed.txt').write_text('tamper')
            with self.assertRaisesRegex(ops.OperationError, 'Prepared inputs changed'):
                ops.finalize_case(store, case, prepared['operation_id'])

    def test_collision_is_never_adopted_or_overwritten(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = qualification_tests.BoundLiveQualificationTests().prepare(root)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            final = root / 'archives' / prepared['operation_id']; final.mkdir(parents=True)
            (final / 'unrelated.txt').write_text('preserve')
            before = snapshot(final)
            with self.assertRaisesRegex(ops.OperationError, 'Unrecorded destination'):
                ops.finalize_case(store, case, prepared['operation_id'], live=(rig, manifest['run_id']))
            self.assertEqual(snapshot(final), before)

    def test_plan_checksum_and_unsupported_schema_refused(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            path = store.root / case / 'operations' / prepared['operation_id'] / 'plan.json'
            value = json.loads(path.read_text()); value['schema_version'] = True; path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ops.OperationError, 'Unsupported'):
                ops.finalize_case(store, case, prepared['operation_id'])


    def test_run_preparation_and_interrupted_receipt_are_idempotent(self):
        from bridgeforge.run_manifest import release_run
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = qualification_tests.BoundLiveQualificationTests().prepare(root)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            original = ops._write
            def interrupt(path, value):
                if value.get('state') == 'RUN_PREPARED':
                    raise OSError('injected after manifest')
                return original(path, value)
            with patch.object(ops, '_write', side_effect=interrupt):
                with self.assertRaisesRegex(OSError, 'injected'):
                    ops.prepare_case_run(store, case, prepared['operation_id'], rig=rig, run_id='new-case-run')
            result = ops.prepare_case_run(store, case, prepared['operation_id'], rig=rig, run_id='new-case-run')
            self.assertEqual(result['state'], 'RUN_PREPARED', result)
            self.assertEqual(ops.prepare_case_run(store, case, prepared['operation_id'], rig=rig, run_id='new-case-run'), result)
            release_run(rig, 'new-case-run', launcher=rig / 'game.bat')

    def test_wrong_staged_bytes_refuse_before_run_manifest(self):
        from bridgeforge.run_manifest import manifest_path
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = qualification_tests.BoundLiveQualificationTests().prepare(root)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            (rig / 'mods' / view.root.name / 'unbound.txt').write_text('staging drift')
            result = ops.prepare_case_run(store, case, prepared['operation_id'], rig=rig, run_id='wrong-staged')
            self.assertEqual(result['state'], 'REFUSED')
            self.assertFalse(manifest_path(rig, 'wrong-staged').exists())

    def test_failed_private_archive_attempt_is_preserved_on_retry(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = qualification_tests.BoundLiveQualificationTests().prepare(root)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            def fail(workspace, done, **kwargs):
                done.mkdir(parents=True)
                (done / 'partial.txt').write_text('preserve interrupted output')
                raise OSError('injected archive failure')
            with patch.object(ops, 'archive_mod', side_effect=fail):
                with self.assertRaisesRegex(OSError, 'injected'):
                    ops.finalize_case(store, case, prepared['operation_id'], live=(rig, manifest['run_id']))
            partial = next((root / 'archives').rglob('partial.txt'))
            result = ops.finalize_case(store, case, prepared['operation_id'], live=(rig, manifest['run_id']))
            self.assertEqual(result['state'], 'COMPLETE')
            self.assertEqual(partial.read_text(), 'preserve interrupted output')

    def test_concurrent_operation_lock_and_stale_input_refusal(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            with store._write_lock(), self.assertRaisesRegex(ValueError, 'locked'):
                ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            (view.working / 'changed.txt').write_text('after prepare')
            report = ops.finalize_case(store, case, prepared['operation_id'])
            self.assertEqual(report['state'], 'REFUSED')
            self.assertFalse((root / 'archives').exists())


    def test_manifest_workspace_preparation_preserves_nonstandard_paths(self):
        from bridgeforge.case_workspace import open_workspace_view
        from bridgeforge.case_qualification import TARGET
        with resolved_temp_dir() as root:
            store, case, old, inputs = fixture(root)
            (old.root / 'original').rename(old.root / 'reference')
            (old.root / 'working').rename(old.root / 'edit')
            (old.root / 'workspace-manifest.json').write_text(json.dumps({'schema_version': 1,
                'original_reference': 'reference', 'working_copy': 'edit'}))
            view = open_workspace_view(old.root)
            case = store.create_case(view, target_profile=TARGET, declared_scope='local-new-game')['content']['case_id']
            candidate = store.add_candidate(case, inputs=inputs)
            before = snapshot(view.root)
            prepared = ops.prepare_case(store, case, candidate['record_id'], archive_root=root / 'archives')
            self.assertEqual(prepared['state'], 'PREPARED')
            self.assertEqual(snapshot(view.root), before)


    def test_unbound_launcher_command_is_never_executed_for_version_observation(self):
        import os
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = qualification_tests.BoundLiveQualificationTests().prepare(root)
            # Select this launcher explicitly in a fresh candidate, but leave the runtime JDK unchanged.
            foreign = root / ('foreign-java.exe' if os.name == 'nt' else 'foreign-java')
            foreign.write_bytes(b'not a tool to execute')
            (rig / 'game.bat').write_text('"' + str(foreign) + '" -version')
            groups = candidate['content']['context']['inputs']
            inputs = {role: {name: Path(item['path']) for name, item in group.items()} for role, group in groups.items()}
            selected = store.add_candidate(case, inputs=inputs)
            prepared = ops.prepare_case(store, case, selected['record_id'], archive_root=root / 'archives')
            with patch('bridgeforge.run_manifest.runtime_hashes', side_effect=AssertionError('must validate before observing')):
                with self.assertRaisesRegex(ops.OperationError, 'unbound Java'):
                    ops.prepare_case_run(store, case, prepared['operation_id'], rig=rig, run_id='foreign-runtime')
