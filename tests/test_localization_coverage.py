import copy
import hashlib
import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridgeforge import localization_coverage as c

GO = Path(os.environ['PROJECT_GO_ACCEPTANCE_ROOT']) if 'PROJECT_GO_ACCEPTANCE_ROOT' in os.environ else None

class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'candidate'
        self.acceptance = GO / '.local/roadmap-next-20261020/localization-coverage.json' if GO else None
        if self.acceptance and self.acceptance.is_file():
            shutil.copytree(GO / 'fixtures/translation-conformance/input', self.root)
            self.report = json.loads(self.acceptance.read_text())
        else:
            self.root.mkdir()
            (self.root / 'mod_info.json').write_bytes(b'{}')
            self.report = {'schemaVersion': c.SCHEMA, 'inputKind': 'DIRECTORY', 'selectedRoot': '',
                'candidateSha256': c.inventory(self.root)[0], 'archiveSha256': '',
                'coverageStatus': 'OBSERVED_STANDARD_EXTRACTION',
                'files': [{'path': 'mod_info.json', 'handler': '', 'status': 'UNSUPPORTED', 'strings': 0, 'reason': 'NO_EXTRACTOR_MATCH'}],
                'supportedFileCount': 0, 'skippedFileCount': 1, 'extractedStringCount': 0,
                'totalSupportedStringCount': None, 'jsonGapCount': 0, 'csvGapCount': 0, 'limitations': ['Selected strings only']}
        self.file = Path(self.temp.name) / 'coverage.json'

    def write(self, report=None):
        self.file.write_text(json.dumps(self.report if report is None else report), encoding='utf-8')
        return self.file

    def test_real_match_changed_bytes_and_source_unchanged(self):
        before = c.inventory(self.root)
        result = c.observe(self.write(), self.root)
        self.assertEqual(result['candidateIdentity'], 'MATCH')
        if self.acceptance and self.acceptance.is_file():
            self.assertEqual(before[0], '8fedc6b762488dd280d540cf058b727ab798a74b9b968c326850637547387f04')
        self.assertFalse(result['completeCoverageEstablished'])
        self.assertEqual(c.inventory(self.root), before)
        (self.root / 'mod_info.json').write_bytes(b'changed')
        self.assertEqual(c.observe(self.file, self.root)['candidateIdentity'], 'MISMATCH')

    def test_partial_unknown(self):
        for status in ('NOT_ASSESSED', 'INCOMPLETE_SOURCE_PARSE', 'NOT_ASSESSED_INVALID_JAR'):
            report = copy.deepcopy(self.report)
            report.update(coverageStatus=status, files=[], supportedFileCount=0, skippedFileCount=0, extractedStringCount=0)
            result = c.observe(self.write(report), self.root)
            self.assertEqual(result['scope'], 'PARTIAL_OR_UNKNOWN')
            self.assertFalse(result['completeCoverageEstablished'])
        report['candidateSha256'] = ''
        self.assertEqual(c.observe(self.write(report), self.root)['candidateIdentity'], 'UNKNOWN')

    def test_malformed_duplicates_unsafe_counts_and_bounded_manifest(self):
        for field, value in (('schemaVersion', 'other'), ('extractedStringCount', True), ('skippedFileCount', 0)):
            report = copy.deepcopy(self.report)
            report[field] = value
            with self.assertRaises(ValueError): c.read_manifest(self.write(report))
        for name in ('../bad', '/bad', 'C:/bad', 'a\\b', 'a//b', 'a/./b'):
            report = copy.deepcopy(self.report)
            report['files'][0]['path'] = name
            with self.assertRaises(ValueError): c.read_manifest(self.write(report))
        report = copy.deepcopy(self.report)
        report['files'].append(report['files'][0])
        with self.assertRaises(ValueError): c.read_manifest(self.write(report))
        self.file.write_text('{"schemaVersion":1,"schemaVersion":2}')
        with self.assertRaises(ValueError): c.read_manifest(self.file)
        with patch.object(c, 'MAX_MANIFEST_BYTES', 1), self.assertRaises(ValueError): c.read_manifest(self.write())

    def test_java_unicode_sort(self):
        root = Path(self.temp.name) / 'unicode'
        root.mkdir()
        expected = hashlib.sha256(b'ProjectGo-inventory-v1\0')
        for name in ('\U00010000', '\ue000'):
            (root / name).write_bytes(b'x')
            raw = name.encode('utf-8')
            expected.update(struct.pack('>i', len(raw)) + raw + struct.pack('>q', 1) + hashlib.sha256(b'x').digest())
        self.assertEqual(c.inventory(root)[0], expected.hexdigest())

    def test_source_change_budget_and_hardlink(self):
        before = c.inventory(self.root)
        with patch.object(c, 'inventory', side_effect=[before, ('changed', *before[1:])]), self.assertRaises(ValueError):
            c.observe(self.write(), self.root)
        with patch.object(c, 'MAX_SOURCE_BYTES', 1), self.assertRaises(ValueError): c.inventory(self.root)
        os.link(self.root / 'mod_info.json', self.root / 'linked')
        with self.assertRaises(ValueError): c.inventory(self.root)

    def test_rejects_direct_and_ancestor_links(self):
        linked = Path(self.temp.name) / 'linked-root'
        try:
            linked.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest('Symlink creation unavailable: ' + str(error))
        with self.assertRaises(ValueError): c.inventory(linked)
        target = self.write()
        leaf = Path(self.temp.name) / 'linked-manifest.json'
        leaf.symlink_to(target)
        with self.assertRaises(ValueError): c.read_manifest(leaf)
        (self.root / 'report.json').write_bytes(target.read_bytes())
        with self.assertRaises(ValueError): c.read_manifest(linked / 'report.json')

if __name__ == '__main__': unittest.main()
