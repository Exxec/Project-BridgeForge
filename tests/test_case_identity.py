"""S1 byte/context identity and immutable persistence refusal tests."""
import json
import os
import shutil
import unittest
from unittest.mock import patch

from bridgeforge import case_identity as identity
from bridgeforge.case_store import CaseStore
from bridgeforge.case_workspace import open_workspace_view
from bridgeforge.live.live_trust import shipped_hash
from tests.support import link_dir, resolved_temp_dir
from tests.test_case_workspace import mod, snapshot

PROFILE = {'target': '0.98a-RC8', 'scope': 'new-game', 'profile_version': 1}
CASE = '1' * 32
STAMP = '2026-10-24T10:00:00+00:00'
TOOL = {'name': 'synthetic-check', 'version': '1', 'sha256': 'a' * 64}


def fixture(root):
    ws = root / 'workspace'; ws.mkdir()
    mod(ws / 'original'); mod(ws / 'working')
    (ws / 'working' / 'data').mkdir()
    (ws / 'working' / 'data' / 'payload.txt').write_text('payload', encoding='utf-8')
    context = root / 'context'; context.mkdir()
    inputs = {}
    for role in identity.CONTEXT_ROLES:
        path = context / (role + '.txt')
        path.write_text(role, encoding='utf-8')
        inputs[role] = {role: path}
    return open_workspace_view(ws), inputs


def receipt(candidate, artifact, **changes):
    options = dict(kind='static', outcome='PASS', reason='synthetic observation', tool=TOOL,
                   run_id='synthetic-run', observed_at=STAMP, evidence=[artifact])
    options.update(changes)
    return identity.make_receipt(candidate, **options)


class CaseIdentityTests(unittest.TestCase):
    def test_payload_matches_existing_run_algorithm_and_is_read_only(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            extra = view.working / 'sun_fr'; extra.mkdir(); (extra / 'image.png').write_bytes(b'synthetic')
            before = snapshot(root)
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            self.assertEqual(candidate['content']['payload']['sha256'], shipped_hash(view.working))
            self.assertIn('sun_fr/image.png', candidate['content']['payload']['files'])
            self.assertEqual(candidate, identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs))
            self.assertEqual(snapshot(root), before)
            self.assertEqual(identity.candidate_state(candidate, view, inputs)['state'], 'CURRENT')

    def test_generated_reports_do_not_change_identity_but_unshipped_source_does(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            (view.working / 'reports').mkdir(); (view.working / 'reports' / 'scan.json').write_text('{}', encoding='utf-8')
            self.assertEqual(identity.candidate_state(candidate, view, inputs)['state'], 'CURRENT')
            (view.working / 'src').mkdir(); (view.working / 'src' / 'Plugin.java').write_text('class Plugin {}', encoding='utf-8')
            changed = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            self.assertEqual(changed['content']['payload']['sha256'], candidate['content']['payload']['sha256'])
            self.assertNotEqual(changed['record_id'], candidate['record_id'])

    def test_same_version_payload_edit_and_context_edit_invalidate(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            path = view.working / 'data' / 'payload.txt'; info = path.stat()
            path.write_text('changed', encoding='utf-8'); os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
            self.assertEqual(identity.candidate_state(candidate, view, inputs)['state'], 'STALE')
            path.write_text('payload', encoding='utf-8')
            for role in identity.CONTEXT_ROLES:
                context = next(iter(inputs[role].values()))
                before = context.read_bytes(); context.write_bytes(before + b'changed')
                with self.subTest(role=role):
                    self.assertEqual(identity.candidate_state(candidate, view, inputs)['state'], 'STALE')
                context.write_bytes(before)

    def test_original_change_and_target_change_bind_new_identity(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            (view.original / 'extra.txt').write_text('upstream', encoding='utf-8')
            changed = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            self.assertNotEqual(candidate['record_id'], changed['record_id'])
            other = identity.capture_candidate(view, case_id=CASE, target_profile={**PROFILE, 'target': 'other'}, inputs=inputs)
            self.assertNotEqual(other['record_id'], changed['record_id'])

    def test_missing_context_stays_visible_and_empty_dependencies_are_explicit(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            inputs['dependencies'] = {}
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            self.assertEqual(candidate['content']['context']['missing_roles'], [])
            incomplete = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs={})
            self.assertEqual(incomplete['content']['context']['missing_roles'], list(identity.CONTEXT_ROLES))
            self.assertEqual(incomplete['content']['context']['provenance'], 'BYTE_BOUND_NOT_QUALIFIED')

    def test_directory_context_and_deleted_input_are_not_reused(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            core = root / 'core'; core.mkdir(); (core / 'data.txt').write_bytes(b'core')
            inputs['core'] = {'core': core}
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            (core / 'added.txt').write_bytes(b'new')
            self.assertEqual(identity.candidate_state(candidate, view, inputs)['state'], 'STALE')
            next(iter(inputs['launcher'].values())).unlink()
            with self.assertRaises(OSError):
                identity.candidate_state(candidate, view, inputs)

    def test_payload_and_context_links_are_refused(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            external = root / 'external'; external.mkdir(); (external / 'secret').write_bytes(b'do not traverse')
            link_dir(external, view.working / 'alias')
            with self.assertRaisesRegex(ValueError, 'symlink/junction'):
                identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            link_dir(root / 'context', root / 'alias')
            inputs['core'] = {'core': root / 'alias'}
            with self.assertRaisesRegex(ValueError, 'symlink/junction'):
                identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)

    def test_mid_capture_and_mid_file_mutation_refuse(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            original = identity._working
            def mutate(view):
                result = original(view)
                (view.working / 'data' / 'payload.txt').write_bytes(b'changed')
                return result
            with patch.object(identity, '_working', side_effect=mutate), self.assertRaisesRegex(ValueError, 'changed during'):
                identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            real_hash = identity.sha256_file
            target = view.working / 'data' / 'payload.txt'
            def hash_then_change(path):
                result = real_hash(path); path.write_bytes(b'longer changed data'); return result
            with patch.object(identity, 'sha256_file', side_effect=hash_then_change), self.assertRaisesRegex(ValueError, 'changed while hashing'):
                identity.file_digest(target)

    def test_malformed_and_tampered_records_refuse(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            for alteration in ('digest', 'version', 'algorithm', 'fields'):
                changed = json.loads(json.dumps(candidate))
                if alteration == 'digest': changed['content']['case_id'] = '2' * 32
                if alteration == 'version': changed['schema_version'] = True
                if alteration == 'algorithm':
                    changed['content']['payload']['algorithm'] = 'unknown'; changed['record_id'] = identity.digest(changed['content'])
                if alteration == 'fields':
                    changed['content']['approved'] = True; changed['record_id'] = identity.digest(changed['content'])
                with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                    identity.validate_record(changed, 'candidate')
            with self.assertRaises(ValueError): identity.canonical({'value': float('nan')})

    def test_receipts_bind_subject_context_evidence_and_keep_observation_unverified(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            artifact = root / 'observation.json'; artifact.write_text('{"observed":true}', encoding='utf-8')
            record = receipt(candidate, artifact)
            self.assertEqual(identity.receipt_state(record, candidate), {'state': 'CURRENT', 'outcome': 'PASS', 'provenance': 'RECORDED_NOT_VERIFIED'})
            changed = identity.capture_candidate(view, case_id='2' * 32, target_profile=PROFILE, inputs=inputs)
            self.assertEqual(identity.receipt_state(record, changed)['state'], 'STALE')
            artifact.write_bytes(b'changed')
            self.assertEqual(identity.receipt_state(record, candidate)['state'], 'STALE')
            artifact.unlink()
            self.assertEqual(identity.receipt_state(record, candidate)['state'], 'INCOMPLETE')
            self.assertEqual(identity.receipt_state({'status': 'PASS'}, candidate)['state'], 'UNKNOWN')

    def test_invalid_receipt_fields_never_create_current_evidence(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            candidate = identity.capture_candidate(view, case_id=CASE, target_profile=PROFILE, inputs=inputs)
            artifact = root / 'log'; artifact.write_bytes(b'observation')
            bad = [{'outcome':'VERIFIED'}, {'reason':''}, {'run_id':''}, {'tool':{}}, {'observed_at':'2026-10-24'}, {'evidence':[]}, {'evidence':[artifact,artifact]}]
            for changes in bad:
                with self.subTest(changes=changes), self.assertRaises(ValueError): receipt(candidate, artifact, **changes)
            incomplete = receipt(candidate, artifact, outcome='INCOMPLETE', evidence=[], reason='tool unavailable')
            self.assertEqual(identity.receipt_state(incomplete, candidate)['outcome'], 'INCOMPLETE')


class CaseStoreTests(unittest.TestCase):
    def setup_case(self, root):
        view, inputs = fixture(root)
        store = CaseStore(root / 'state')
        case = store.create_case(view, target_profile=PROFILE, declared_scope='local-new-game', case_id=CASE)
        return view, inputs, store, case

    def test_case_retry_and_candidate_receipt_roundtrip_without_input_writes(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            before = snapshot(view.root)
            self.assertEqual(case, store.create_case(view, target_profile=PROFILE, declared_scope='local-new-game', case_id=CASE))
            candidate = store.add_candidate(CASE, inputs=inputs)
            self.assertEqual(candidate, store.add_candidate(CASE, inputs=inputs))
            self.assertEqual(candidate, store.load_candidate(CASE, candidate['record_id']))
            artifact = root / 'log'; artifact.write_bytes(b'observed')
            record = receipt(candidate, artifact)
            self.assertEqual(store.add_receipt(CASE, record), store.add_receipt(CASE, record))
            self.assertEqual(record, store.load_receipt(CASE, record['record_id']))
            self.assertEqual(case['content']['authority'], 'DECLARED_NOT_APPROVED')
            self.assertEqual(before, snapshot(view.root))

    def test_case_scope_conflict_and_invalid_identifiers_refuse(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            with self.assertRaisesRegex(ValueError, 'different workspace/scope/profile'):
                store.create_case(view, target_profile=PROFILE, declared_scope='distribution', case_id=CASE)
            for value in ('../escape', '', 'A' * 32):
                with self.subTest(value=value), self.assertRaises(ValueError): store.load_case(value)
            with self.assertRaises(ValueError): store.load_candidate(CASE, '../escape')
            with self.assertRaises(ValueError): store.load_receipt(CASE, 'bad')

    def test_store_inside_workspace_or_context_refuses(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root)
            forbidden = CaseStore(view.working / 'state')
            before = snapshot(view.root)
            with self.assertRaisesRegex(ValueError, 'outside the workspace'):
                forbidden.create_case(view, target_profile=PROFILE, declared_scope='analysis')
            self.assertEqual(before, snapshot(view.root))
            store = CaseStore(root / 'state'); store.create_case(view, target_profile=PROFILE, declared_scope='analysis', case_id=CASE)
            inputs['core'] = {'state': store.root}
            with self.assertRaisesRegex(ValueError, 'overlap'): store.add_candidate(CASE, inputs=inputs)

    def test_predecessor_binding_and_cross_case_replay_refuse(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            first = store.add_candidate(CASE, inputs=inputs)
            second = store.add_candidate(CASE, inputs=inputs, predecessor=first['record_id'])
            self.assertEqual(second['content']['predecessor'], first['record_id'])
            self.assertNotEqual(second['record_id'], first['record_id'])
            with self.assertRaises(ValueError): store.add_candidate(CASE, inputs=inputs, predecessor='b' * 64)
            other = '2' * 32
            store.create_case(view, target_profile=PROFILE, declared_scope='analysis', case_id=other)
            destination = store.root / other / 'candidates'; destination.mkdir(parents=True)
            shutil.copyfile(store.root / CASE / 'candidates' / (first['record_id'] + '.json'), destination / (first['record_id'] + '.json'))
            with self.assertRaisesRegex(ValueError, 'subject/path'): store.load_candidate(other, first['record_id'])
            artifact = root / 'log'; artifact.write_bytes(b'observed')
            with self.assertRaisesRegex(ValueError, 'another case'): store.add_receipt(other, receipt(first, artifact))

    def test_interrupted_publication_can_retry_without_partial_acceptance(self):
        with resolved_temp_dir() as root:
            view, inputs = fixture(root); store = CaseStore(root / 'state')
            before = snapshot(view.root)
            with patch('bridgeforge.case_store.atomic_write_json', side_effect=OSError('injected failure')):
                with self.assertRaises(OSError): store.create_case(view, target_profile=PROFILE, declared_scope='analysis', case_id=CASE)
            with self.assertRaises(ValueError): store.load_case(CASE)
            self.assertFalse((store.root / '.write-lock').exists())
            case = store.create_case(view, target_profile=PROFILE, declared_scope='analysis', case_id=CASE)
            self.assertEqual(case, store.load_case(CASE))
            self.assertEqual(before, snapshot(view.root))

    def test_lock_conflict_preserves_existing_records_and_readers(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            with store._write_lock():
                self.assertEqual(case, store.load_case(CASE))
                with self.assertRaisesRegex(ValueError, 'locked'): store.add_candidate(CASE, inputs=inputs)
            lock = store.root / '.write-lock'; lock.write_text('abandoned', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'locked'): store.add_candidate(CASE, inputs=inputs)
            self.assertEqual(lock.read_text(), 'abandoned')

    def test_tampered_or_partial_record_is_never_overwritten(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            candidate = store.add_candidate(CASE, inputs=inputs)
            path = store.root / CASE / 'candidates' / (candidate['record_id'] + '.json')
            path.write_text('{partial', encoding='utf-8')
            with self.assertRaises(ValueError): store.load_candidate(CASE, candidate['record_id'])
            with self.assertRaises(ValueError): store.add_candidate(CASE, inputs=inputs)
            self.assertEqual(path.read_text(), '{partial')
            case_path = store.root / 'cases' / (CASE + '.json')
            case_path.write_text('{"schema":1,"schema":2}', encoding='utf-8')
            with self.assertRaises(ValueError): store.load_case(CASE)

    def test_changed_or_missing_receipt_evidence_is_not_published(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            candidate = store.add_candidate(CASE, inputs=inputs)
            artifact = root / 'log'; artifact.write_bytes(b'old')
            record = receipt(candidate, artifact)
            artifact.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError, 'not current'): store.add_receipt(CASE, record)
            self.assertFalse((store.root / CASE / 'receipts').exists())

    def test_store_junction_and_workspace_rebinding_refuse(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            link_dir(store.root, root / 'state-alias')
            with self.assertRaisesRegex(ValueError, 'symlink/junction'): CaseStore(root / 'state-alias')
            changed = json.loads(json.dumps(case)); changed['content']['workspace']['layout'] = 'manifest-v1'
            changed['record_id'] = identity.digest(changed['content'])
            (store.root / 'cases' / (CASE + '.json')).write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'layout changed'): store.workspace(CASE)

    def test_resume_uses_persisted_context_locations_and_detects_drift(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            candidate = store.add_candidate(CASE, inputs=inputs)
            reopened = CaseStore(store.root)
            self.assertEqual(reopened.assess_candidate(CASE, candidate['record_id'])['state'], 'CURRENT')
            next(iter(inputs['core'].values())).write_bytes(b'new core bytes')
            self.assertEqual(reopened.assess_candidate(CASE, candidate['record_id'])['state'], 'STALE')

    def test_individual_immutable_store_artifact_can_bind_context(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            inputs['source_authority'] = {'declaration': store.root / 'cases' / (CASE + '.json')}
            candidate = store.add_candidate(CASE, inputs=inputs)
            self.assertEqual(store.assess_candidate(CASE, candidate['record_id'])['state'], 'CURRENT')
            self.assertEqual(candidate['content']['context']['provenance'], 'BYTE_BOUND_NOT_QUALIFIED')

    def test_case_metadata_cannot_claim_approval_or_unsupported_schema(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            path = store.root / 'cases' / (CASE + '.json')
            for field, value in (('authority', 'APPROVED'), ('declared_scope', ''), ('created_at', STAMP[:10]), ('target_profile', {})):
                with self.subTest(field=field):
                    changed = json.loads(json.dumps(case))
                    changed['content'][field] = value
                    changed['record_id'] = identity.digest(changed['content'])
                    path.write_text(json.dumps(changed), encoding='utf-8')
                    with self.assertRaises(ValueError): store.load_case(CASE)
            changed = json.loads(json.dumps(case)); changed['content']['case_id'] = '2' * 32
            changed['record_id'] = identity.digest(changed['content'])
            path.write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'identity/path'): store.load_case(CASE)

    def test_resealed_receipt_provenance_and_context_do_not_gain_qualification(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            candidate = store.add_candidate(CASE, inputs=inputs)
            artifact = root / 'log'; artifact.write_bytes(b'observation')
            record = receipt(candidate, artifact)
            for field, value in (('outcome', 'APPROVED'), ('provenance', 'VERIFIED'), ('observed_at', STAMP[:10]), ('evidence', {'relative.log': 'a' * 64})):
                with self.subTest(field=field):
                    changed = json.loads(json.dumps(record))
                    changed['content'][field] = value
                    changed['record_id'] = identity.digest(changed['content'])
                    with self.assertRaises(ValueError): store.add_receipt(CASE, changed)
            changed = json.loads(json.dumps(record)); changed['content']['context_id'] = 'b' * 64
            changed['record_id'] = identity.digest(changed['content'])
            self.assertEqual(identity.receipt_state(changed, candidate)['state'], 'STALE')
            with self.assertRaises(ValueError): store.add_receipt(CASE, changed)

    def test_valid_foreign_record_and_changed_lock_owner_are_preserved(self):
        with resolved_temp_dir() as root:
            view, inputs, store, case = self.setup_case(root)
            first = store.add_candidate(CASE, inputs=inputs)
            second = store.add_candidate(CASE, inputs=inputs, predecessor=first['record_id'])
            path = store.root / CASE / 'candidates' / (first['record_id'] + '.json')
            path.write_text(json.dumps(second), encoding='utf-8')
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'Immutable record collision'): store.add_candidate(CASE, inputs=inputs)
            self.assertEqual(path.read_bytes(), before)
            lock = store.root / '.write-lock'
            with self.assertRaisesRegex(ValueError, 'ownership changed'):
                with store._write_lock():
                    lock.write_text('another owner', encoding='utf-8')
            self.assertEqual(lock.read_text(), 'another owner')
