"""96.5 A10: one file hash and one per-file tree hash for every module; the old private copies are the shared functions."""
from __future__ import annotations

import hashlib
import importlib
import unittest

from bridgeforge import file_hash
from bridgeforge.file_hash import CHUNK, file_hashes, sha256_file, sha256_file_or_none
from tests.support import resolved_temp_dir
from tests.support import write_text as _write

# module -> (old name, shared function): each name a module kept for its call sites is the shared function itself.
ROUTED = {
    "api_diff": ("_sha256", sha256_file), "archive": ("_digest", sha256_file), "archive_intake": ("_sha256", sha256_file),
    "bytecode.src_to_jar": ("_sha", sha256_file), "decompiler": ("_sha256", sha256_file),
    "explain_proofs": ("sha256", sha256_file), "live.live_trust": ("_sha256", sha256_file),
    "move_machine": ("sha256_of", sha256_file), "reference_rigs": ("_sha256", sha256_file), "revise": ("_file_sha", sha256_file),
    "research.research_decompile": ("jar_sha256", sha256_file), "run_manifest": ("_sha256_file", sha256_file),
    "scan.scan_registry": ("_sha256", sha256_file),  # save_snapshot's _hash_file served only its _hash_tree, so it is gone
    "shadow_triage": ("_sha", sha256_file), "snapshot_restore": ("_sha256", sha256_file), "targets": ("_sha256", sha256_file),
    "translation": ("_sha256", sha256_file), "vendor_plan": ("_sha256", sha256_file), "workspace": ("sha256_file", sha256_file),
    "dossier": ("_mod_info_sha256", sha256_file_or_none), "escalation.escalation_policy": ("_sha", sha256_file_or_none),
    "fixers.presets": ("file_sha256", sha256_file_or_none), "revive": ("_sha256", sha256_file_or_none),
    "substitution_proposals": ("_sha256", sha256_file_or_none),
    "evaluation": ("_tree_hashes", file_hashes), "validate": ("_tree_hashes", file_hashes),
    "save.save_snapshot": ("_hash_tree", file_hashes),
}


class FileHashTests(unittest.TestCase):
    def test_the_digest_is_hashlib_s_for_small_empty_and_multi_chunk_files(self) -> None:
        with resolved_temp_dir() as root:
            for name, data in (("empty", b""), ("small", b"abc"), ("big", bytes(range(256)) * (CHUNK // 256 * 2 + 3))):
                path = root / name
                path.write_bytes(data)
                with self.subTest(name=name):
                    self.assertEqual(sha256_file(path), hashlib.sha256(data).hexdigest())
                    self.assertEqual(sha256_file(str(path)), hashlib.sha256(data).hexdigest())

    def test_or_none_is_none_for_a_missing_file_or_a_folder(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "f.txt", "x")
            self.assertEqual(sha256_file_or_none(root / "f.txt"), hashlib.sha256(b"x").hexdigest())
            self.assertIsNone(sha256_file_or_none(root / "missing"))
            self.assertIsNone(sha256_file_or_none(root))
            with self.assertRaises(OSError):
                sha256_file(root / "missing")

    def test_file_hashes_maps_every_nested_file_by_posix_path_in_order(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "b.txt", "b")
            _write(root / "a" / "z.txt", "z")
            (root / "empty-dir").mkdir()
            hashes = file_hashes(root)
            self.assertEqual(list(hashes), ["a/z.txt", "b.txt"])
            self.assertEqual(hashes["a/z.txt"], hashlib.sha256(b"z").hexdigest())


class CopiesAreGoneTests(unittest.TestCase):
    def test_every_old_name_is_the_shared_function(self) -> None:
        for key, (name, shared) in ROUTED.items():
            module = importlib.import_module(f"bridgeforge.{key}")
            with self.subTest(module=key, name=name):
                self.assertIs(getattr(module, name), shared)

    def test_the_wrappers_with_their_own_result_for_a_missing_file(self) -> None:
        from bridgeforge.escalation.escalation_review import snapshot_dir
        from bridgeforge.lookup import _sha256 as lookup_sha256
        from bridgeforge.value_proposals import _sha

        with resolved_temp_dir() as root:
            _write(root / "d" / "f.txt", "x")
            self.assertEqual(snapshot_dir(root / "d"), file_hashes(root / "d"))
            self.assertEqual(snapshot_dir(root / "missing"), {})
            self.assertEqual(_sha(root / "missing"), "")
            self.assertEqual(_sha(root / "d" / "f.txt"), sha256_file(root / "d" / "f.txt"))
            self.assertIsNone(lookup_sha256(root / "missing"))
            self.assertIsNone(lookup_sha256(root / "d"))  # a folder: any read error is None there

    def test_the_module_lists_what_stays_apart(self) -> None:
        doc = file_hash.__doc__ or ""
        for name in ("provenance", "scan_registry", "revival_audit", "93.27"):
            self.assertIn(name, doc)


if __name__ == "__main__":
    unittest.main()
