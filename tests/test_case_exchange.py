"""Private case metadata rebinding never imports historical acceptance or broadens rights."""
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
import io
import shutil
import unittest

from bridgeforge.case_identity import digest, make_receipt
from bridgeforge.case_qualification import LEGACY_TARGET
from bridgeforge.case_store import CaseStore
from bridgeforge.cli import main
from bridgeforge.safeio import safe_rmtree
from tests.support import resolved_temp_dir
from tests.test_case_qualification import fixture
from bridgeforge import case_exchange as api


def create(root):
    store, case, view, inputs = fixture(root)
    candidate = store.add_candidate(case, inputs=inputs)
    destination = root / 'private-exchange.json'
    api.export_private_case(store, case, candidate['record_id'], destination)
    return store, case, view, inputs, api.read_exchange(destination)


class ExchangeTests(unittest.TestCase):
    def test_cold_path_rebinding_without_source_or_legacy_artifact_access(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            artifact = root / 'artifact.txt'; artifact.write_text('historical only')
            receipt = make_receipt(candidate, kind='static', outcome='PASS', reason='Synthetic history only',
                tool={'name': 'test', 'version': '1', 'sha256': '1' * 64}, run_id='old',
                observed_at=datetime.now(timezone.utc).isoformat(), evidence=[artifact])
            store.add_receipt(case, receipt)
            path = root / 'private.json'
            api.export_private_case(store, case, candidate['record_id'], path)
            record = api.read_exchange(path)
            restored = root / 'restored'; shutil.copytree(view.root, restored)
            context = root / 'restored-context'; shutil.copytree(root / 'context', context)
            remapped = {role: None if group is None else {
                name: context / p.relative_to(root / 'context') if p.is_relative_to(root / 'context') else p
                for name, p in group.items()} for role, group in inputs.items()}
            safe_rmtree(view.root, [root]); safe_rmtree(root / 'context', [root]); artifact.unlink()
            imported = CaseStore(root / 'imported-state')
            result = api.import_private_case(record, imported, restored, remapped)
            self.assertEqual(result['state'], 'IMPORTED_UNQUALIFIED')
            self.assertNotEqual(result['case_id'], case)
            self.assertEqual(result['qualification'], 'NOT_EVALUATED')
            self.assertEqual(imported.assess_candidate(result['case_id'], result['candidate_id'])['state'], 'CURRENT')
            self.assertFalse((imported.root / result['case_id'] / 'receipts').exists())
            self.assertTrue((imported.root / 'exchange-history' / (record['sha256'] + '.json')).exists())
            repeat = api.import_private_case(record, imported, restored, remapped)
            self.assertEqual(result['case_id'], repeat['case_id'])
            self.assertEqual(result['candidate_id'], repeat['candidate_id'])

    def test_payload_reports_and_policy_cannot_be_relaxed(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs, record = create(root)
            restored = root / 'restored'; shutil.copytree(view.root, restored)
            imported = CaseStore(root / 'imported-state')
            target = restored / 'working/new.txt'; target.write_text('payload drift')
            with self.assertRaisesRegex(ValueError, 'bytes differ'):
                api.import_private_case(record, imported, restored, inputs)
            target.unlink()
            (restored / 'reports').mkdir()
            (restored / 'reports/decision.txt').write_text('changed decision')
            with self.assertRaisesRegex(ValueError, 'reports/checkpoints'):
                api.import_private_case(record, imported, restored, inputs)
            safe_rmtree(restored / 'reports', [root])
            inputs['policy']['release'].write_text('{"mods":{}}')
            with self.assertRaisesRegex(ValueError, 'policy/review authority'):
                api.import_private_case(record, imported, restored, inputs, allow_context_change=True)
            self.assertFalse(imported.root.exists())

    def test_changed_tools_require_explicit_requalification_context(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs, record = create(root)
            restored = root / 'restored'; shutil.copytree(view.root, restored)
            extra = root / 'runtime.txt'; extra.write_text('new runtime identity')
            inputs['tools']['environment'] = extra
            imported = CaseStore(root / 'imported-state')
            with self.assertRaisesRegex(ValueError, 'allow_context_change'):
                api.import_private_case(record, imported, restored, inputs)
            result = api.import_private_case(record, imported, restored, inputs, allow_context_change=True)
            self.assertEqual(result['context_changes'], ['tools'])
            self.assertEqual(result['publication'], 'NOT_AUTHORIZED')

    def test_schema_tampering_privacy_and_unsupported_profile_refuse(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs, record = create(root)
            restored = root / 'restored'; shutil.copytree(view.root, restored)
            for field, value in (('schema_version', True), ('schema_version', 99), ('sha256', '0' * 64)):
                altered = deepcopy(record); altered[field] = value
                with self.assertRaises(ValueError):
                    api.import_private_case(altered, CaseStore(root / 'new-state'), restored, inputs)
            for field, value in (('publication_authorized', True), ('payload_included', 0)):
                altered = deepcopy(record); altered['content']['restrictions'][field] = value
                altered['sha256'] = digest(altered['content'])
                with self.assertRaisesRegex(ValueError, 'privacy'):
                    api.import_private_case(altered, CaseStore(root / 'new-state'), restored, inputs)
            # A structurally supported historical profile is readable but cannot acquire current acceptance.
            altered = deepcopy(record)
            for name in ('case', 'candidate'):
                sub = altered['content'][name]; sub['content']['target_profile'] = LEGACY_TARGET
                sub['record_id'] = digest(sub['content'])
            altered['sha256'] = digest(altered['content'])
            with self.assertRaisesRegex(ValueError, 'Unsupported imported profile'):
                api.import_private_case(altered, CaseStore(root / 'new-state'), restored, inputs)

    def test_summary_omits_private_paths_and_export_never_overwrites(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs, record = create(root)
            summary = api.exchange_summary(record)
            text = json.dumps(summary)
            self.assertNotIn(str(root), text)
            self.assertNotIn('workspace', text)
            self.assertFalse(summary['publication_authorized'])
            with self.assertRaisesRegex(ValueError, 'new metadata file'):
                api.export_private_case(store, case, record['content']['candidate']['record_id'], root / 'private-exchange.json')
            with self.assertRaisesRegex(ValueError, 'new metadata file'):
                api.export_private_case(store, case, record['content']['candidate']['record_id'], view.root / 'private.json')
            with self.assertRaisesRegex(ValueError, 'isolated restored'):
                api.import_private_case(record, CaseStore(root / 'imported-state'), view.root, inputs)

    def test_cli_requirements_summary_and_explicit_import(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs, record = create(root)
            manifest = root / 'private-exchange.json'
            for command in ('summary', 'requirements'):
                stream = io.StringIO()
                with redirect_stdout(stream):
                    self.assertEqual(main(['case-exchange', command, str(manifest), '--json']), 0)
                self.assertNotIn(str(root), stream.getvalue())
            restored = root / 'restored'; shutil.copytree(view.root, restored)
            bindings = root / 'bindings.json'
            bindings.write_text(json.dumps({'schema_version': 1, 'inputs': {
                role: None if group is None else {name: str(path) for name, path in group.items()}
                for role, group in inputs.items()}}))
            stream = io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(main(['case-exchange', 'import', str(manifest), '--workspace', str(restored),
                    '--store', str(root / 'imported-state'), '--inputs', str(bindings), '--json']), 0)
            self.assertEqual(json.loads(stream.getvalue())['state'], 'IMPORTED_UNQUALIFIED')


if __name__ == '__main__':
    unittest.main()
