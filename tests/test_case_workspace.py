"""S1 read-only workspace adapters, explicit authority and refusal boundaries."""
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import unittest
import zipfile

from bridgeforge.case_workspace import open_workspace_view
from bridgeforge.intake import intake_archive
from bridgeforge.workspace import create_workspace, workspace_paths
from tests.support import link_dir, resolved_temp_dir


def mod(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / 'mod_info.json').write_text('{"id":"synthetic-s1","name":"Synthetic S1","version":"1"}', encoding='utf-8')
    return root


def manifest(root: Path) -> dict:
    root.mkdir()
    mod(root / 'original-reference')
    mod(root / 'working-copy')
    record = {'schema_version': 1, 'original_reference': 'original-reference', 'working_copy': 'working-copy'}
    write_record(root / 'workspace-manifest.json', record)
    return record


def write_record(path: Path, record):
    path.write_text(json.dumps(record), encoding='utf-8')


def snapshot(root: Path):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            for p in root.rglob('*')}


class CaseWorkspaceTests(unittest.TestCase):
    def test_existing_manifest_api_and_bytes_remain_unchanged(self):
        with resolved_temp_dir() as root:
            source = mod(root / 'source')
            workspace = create_workspace(source, root / 'workspace')
            before = snapshot(root)
            original, working, _ = workspace_paths(workspace)
            view = open_workspace_view(workspace)
            self.assertEqual((view.original, view.working), (original, working))
            self.assertEqual(view.layout, 'manifest-v1')
            self.assertEqual(view.checkpoints, workspace / 'checkpoints')
            self.assertIsNone(view.reports)
            self.assertEqual(view.unavailable, ('reports',))
            self.assertEqual(view.provenance, 'UNVERIFIED')
            self.assertEqual(before, snapshot(root))

    def test_direct_convention_has_explicit_missing_capabilities_and_no_writes(self):
        with resolved_temp_dir() as root:
            mod(root / 'original'); mod(root / 'working')
            before = snapshot(root)
            view = open_workspace_view(root)
            self.assertEqual(view.layout, 'convention-v1')
            self.assertEqual(view.selection_source, 'ROOT_REFERENCE')
            self.assertEqual(view.unavailable, ('reports', 'checkpoints'))
            with self.assertRaises(FrozenInstanceError):
                view.working = root
            self.assertEqual(before, snapshot(root))

    def test_nested_originals_require_selection_never_first_match(self):
        with resolved_temp_dir() as root:
            mod(root / 'original' / 'a'); mod(root / 'original' / 'b'); mod(root / 'working')
            with self.assertRaisesRegex(ValueError, 'original_relative'):
                open_workspace_view(root)
            view = open_workspace_view(root, original_relative='b')
            self.assertEqual(view.original, root / 'original' / 'b')
            self.assertEqual(view.selection_source, 'EXPLICIT_SELECTION')

    def test_intake_record_resolves_nested_and_root_selections_without_claiming_identity(self):
        for selected in ('.', 'nested/ship'):
            with self.subTest(selected=selected), resolved_temp_dir() as root:
                extracted = root / 'original' / 'extracted'
                original = mod(extracted if selected == '.' else extracted / selected)
                mod(root / 'working'); (root / 'reports').mkdir()
                write_record(root / 'reports' / 'intake.json', {'schema_version': 1, 'mode': 'INTAKE', 'selected_root': selected})
                before = snapshot(root)
                view = open_workspace_view(root)
                self.assertEqual(view.original, original)
                self.assertEqual(view.selection_source, 'INTAKE_SELECTION')
                self.assertEqual(view.provenance, 'UNVERIFIED')
                self.assertEqual(snapshot(root), before)

    def test_real_intake_api_synthetic_zip_opens_without_mutation(self):
        with resolved_temp_dir() as root:
            archive = root / 'synthetic.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('ship/mod_info.json', '{"id":"synthetic-s1","name":"Synthetic S1","version":"1"}')
            repo = root / 'repo'; repo.mkdir()
            result = intake_archive(archive, repo)
            before = snapshot(root)
            view = open_workspace_view(Path(result['destination']))
            self.assertEqual(view.original, view.original_container / 'extracted' / 'ship')
            self.assertEqual(view.working, Path(result['working']))
            self.assertEqual(before, snapshot(root))

    def test_mixed_and_orphaned_layouts_refuse(self):
        with resolved_temp_dir() as root:
            manifest(root / 'workspace')
            (root / 'workspace' / 'working').mkdir()
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                open_workspace_view(root / 'workspace')
        with resolved_temp_dir() as root:
            (root / 'original-reference').mkdir()
            with self.assertRaisesRegex(ValueError, 'Incomplete/ambiguous'):
                open_workspace_view(root)

    def test_bad_manifest_schema_and_json_refuse(self):
        for value in ([], {}, {'schema_version': True}, {'schema_version': '1'}, {'schema_version': 2}):
            with self.subTest(value=value), resolved_temp_dir() as root:
                write_record(root / 'workspace-manifest.json', value)
                with self.assertRaisesRegex(ValueError, 'schema_version'):
                    open_workspace_view(root)
        with resolved_temp_dir() as root:
            (root / 'workspace-manifest.json').write_text('{bad', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'JSON record'):
                open_workspace_view(root)

    def test_manifest_path_values_refuse_traversal_drives_unc_and_missing_fields(self):
        for value in (None, 1, '', '.', '../outside', '/absolute', 'C:/outside', 'C:relative', r'\\server\share', r'a\..\b', 'a//b', ' original-reference', 'a:stream'):
            with self.subTest(value=value), resolved_temp_dir() as root:
                record = manifest(root / 'ws')
                record['original_reference'] = value
                write_record(root / 'ws' / 'workspace-manifest.json', record)
                with self.assertRaises(ValueError):
                    open_workspace_view(root / 'ws')

    def test_overlapping_roles_and_nested_working_refuse(self):
        for selected in ('original-reference', 'original-reference/child'):
            with self.subTest(selected=selected), resolved_temp_dir() as root:
                record = manifest(root / 'ws')
                if '/' in selected:
                    mod(root / 'ws' / selected)
                record['working_copy'] = selected
                write_record(root / 'ws' / 'workspace-manifest.json', record)
                with self.assertRaisesRegex(ValueError, 'overlap'):
                    open_workspace_view(root / 'ws')

    def test_missing_roots_metadata_or_optional_path_of_wrong_type_refuse(self):
        with resolved_temp_dir() as root:
            with self.assertRaisesRegex(ValueError, 'directory'):
                open_workspace_view(root)
            mod(root / 'original'); (root / 'working').mkdir()
            with self.assertRaisesRegex(ValueError, 'mod_info'):
                open_workspace_view(root)
            (root / 'working' / 'mod_info.json').write_text('{}', encoding='utf-8')
            (root / 'reports').write_text('not a directory', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'reports'):
                open_workspace_view(root)

    def test_intake_record_invalid_mode_schema_and_path_refuse(self):
        for field, value in (('mode', 'OTHER'), ('schema_version', 2), ('selected_root', None), ('selected_root', '../working'), ('selected_root', 'C:/escape')):
            with self.subTest(field=field, value=value), resolved_temp_dir() as root:
                mod(root / 'original'); mod(root / 'working'); (root / 'reports').mkdir()
                record = {'schema_version': 1, 'mode': 'INTAKE', 'selected_root': '.'}
                record[field] = value
                write_record(root / 'reports' / 'intake.json', record)
                with self.assertRaises(ValueError):
                    open_workspace_view(root)

    def test_explicit_selection_is_contained_and_can_select_container(self):
        with resolved_temp_dir() as root:
            mod(root / 'original'); mod(root / 'working')
            self.assertEqual(open_workspace_view(root, original_relative='.').original, root / 'original')
            for value in ('../working', '/absolute', 'C:/outside', ''):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    open_workspace_view(root, original_relative=value)

    def test_junction_or_symlink_working_and_optional_reports_refuse(self):
        for name in ('working', 'reports'):
            with self.subTest(name=name), resolved_temp_dir() as root:
                ws = root / 'ws'; ws.mkdir()
                mod(ws / 'original')
                target = mod(root / 'external')
                if name != 'working':
                    mod(ws / 'working')
                link_dir(target, ws / name)
                with self.assertRaisesRegex(ValueError, 'symlink/junction'):
                    open_workspace_view(ws)

    def test_linked_workspace_and_linked_original_selection_refuse(self):
        with resolved_temp_dir() as root:
            ws = root / 'ws'; ws.mkdir(); mod(ws / 'original'); mod(ws / 'working')
            link_dir(ws, root / 'alias')
            with self.assertRaisesRegex(ValueError, 'symlink/junction'):
                open_workspace_view(root / 'alias')
            link_dir(root / 'ws' / 'working', ws / 'original' / 'linked')
            with self.assertRaisesRegex(ValueError, 'symlink/junction'):
                open_workspace_view(ws, original_relative='linked')

    def test_manifest_optional_capabilities_are_not_created(self):
        with resolved_temp_dir() as root:
            manifest(root / 'ws')
            before = snapshot(root)
            view = open_workspace_view(root / 'ws')
            self.assertEqual(view.selection_source, 'WORKSPACE_REFERENCE')
            self.assertEqual(view.unavailable, ('reports', 'checkpoints'))
            self.assertEqual(before, snapshot(root))

    def test_intake_selection_only_checks_the_actual_extracted_path(self):
        with resolved_temp_dir() as root:
            original = mod(root / 'original' / 'extracted' / 'ship')
            target = mod(root / 'external')
            link_dir(target, root / 'original' / 'ship')
            mod(root / 'working'); (root / 'reports').mkdir()
            write_record(root / 'reports' / 'intake.json', {'schema_version': 1, 'mode': 'INTAKE', 'selected_root': 'ship'})
            self.assertEqual(open_workspace_view(root).original, original)
