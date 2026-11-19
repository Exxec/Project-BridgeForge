"""94.G1 WP4 (GR-6): one licence ledger per mod, read in one place."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import unittest
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.licence_ledger import decision, licence_allows, local_only_paths, member_file, vendoring
from bridgeforge.release import ReleaseError, _load_policy, apply_standing_licence, record_path_exception, record_policy_decision
from bridgeforge.strip_plan import vendor_copy
from tests.support import resolved_temp_dir, write_text as _write

ROOT = Path(__file__).resolve().parents[1]
ART = {"prefix": "graphics/other_author", "local_only": True, "reason": "sprites by another author, no permission"}


def _policy(root: Path, mods: dict) -> Path:
    path = root / "policy" / "release_policy.json"
    _write(path, json.dumps({"schema_version": 1, "mods": mods, "default": {"local_only": False, "reason": None}}))
    return path


def _mod(root: Path, name: str, mod_id: str) -> Path:
    folder = root / name
    _write(folder / "mod_info.json", json.dumps({"id": mod_id, "name": mod_id}))
    return folder


class PathExceptionTests(unittest.TestCase):
    def test_an_exception_survives_a_new_decision_and_the_standing_licence(self) -> None:
        with resolved_temp_dir() as base:
            policy = _policy(base, {})
            record_policy_decision("open_mod", local_only=False, reason="MIT", policy_path=policy)
            record_path_exception("open_mod", "graphics/other_author/", reason=ART["reason"], policy_path=policy)
            record_policy_decision("open_mod", local_only=False, reason="MIT, re-checked", policy_path=policy)
            self.assertFalse(apply_standing_licence("open_mod", "open_mod", live_date="2026-11-19", policy_path=policy))
            entry = _load_policy(policy)["mods"]["open_mod"]
            self.assertEqual(entry["reason"], "MIT, re-checked")
            self.assertEqual(entry["paths"], [ART])

    def test_whole_segments_only_and_members_match_by_their_file(self) -> None:
        with resolved_temp_dir() as base:
            policy = _policy(base, {"m": {"local_only": False, "reason": "MIT", "paths": [ART, {
                "prefix": "jars/bundled.jar", "local_only": True, "reason": "a bundled library"}, {
                "prefix": "data/hullmods/hull_mods.csv", "local_only": True, "reason": "rows by another author"}]}})
            paths = ["graphics/other_author/a.png", "graphics/other_authorX/a.png", "graphics/other_author",
                     "jars/bundled.jar!a/B.class", "jars/bundled.jarx!a/B.class", "data/hullmods/hull_mods.csv [x_radar]",
                     "graphics/mine/a.png"]
            found = [hit["path"] for hit in local_only_paths("m", None, paths, policy)]
        self.assertEqual(found, ["graphics/other_author/a.png", "graphics/other_author", "jars/bundled.jar!a/B.class",
                                 "data/hullmods/hull_mods.csv [x_radar]"])
        self.assertEqual(member_file("jars/x.jar!a/B.class"), "jars/x.jar")

    def test_a_prefix_that_leaves_the_mod_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            for bad in ("../x", "/graphics", "graphics\\x", "C:/x", "a/../b", ""):
                with self.subTest(bad):
                    policy = _policy(base / bad.replace("/", "_").replace("\\", "_").replace(":", "_").replace(".", "d"),
                                     {"m": {"local_only": False, "reason": "MIT", "paths": [{**ART, "prefix": bad}]}})
                    with self.assertRaises(ReleaseError):
                        _load_policy(policy)
            policy = _policy(base / "ok", {"m": {"local_only": False, "reason": "MIT"}})
            with self.assertRaises(ReleaseError):
                record_path_exception("m", "../escape", reason="r", policy_path=policy)
            with self.assertRaisesRegex(ReleaseError, "no recorded decision"):
                record_path_exception("unrecorded", "graphics", reason="r", policy_path=policy)


class UseTests(unittest.TestCase):
    def test_local_is_always_allowed_and_distribute_needs_an_explicit_release(self) -> None:
        with resolved_temp_dir() as base:
            policy = _policy(base, {"open": {"local_only": False, "reason": "MIT", "paths": [ART]},
                                    "closed": {"local_only": True, "reason": "no licence"}})
            self.assertTrue(licence_allows("unknown", None, "local", policy_path=policy)["allowed"])
            self.assertFalse(licence_allows("unknown", None, "distribute", policy_path=policy)["allowed"])  # UNRECORDED
            self.assertFalse(licence_allows("closed", None, "distribute", policy_path=policy)["allowed"])
            self.assertTrue(licence_allows("open", None, "distribute", paths=["graphics/mine/a.png"], policy_path=policy)["allowed"])
            refused = licence_allows("open", None, "distribute", paths=["graphics/other_author/a.png"], policy_path=policy)
            self.assertFalse(refused["allowed"])
            self.assertIn("graphics/other_author", refused["reason"])
            with self.assertRaises(ValueError):
                licence_allows("open", None, "sell", policy_path=policy)

    def test_a_local_only_path_of_a_releasable_source_vendors_only_into_a_local_only_target(self) -> None:
        with resolved_temp_dir() as base:
            policy = _policy(base, {"open": {"local_only": False, "reason": "MIT", "paths": [ART]},
                                    "revenantlib": {"local_only": True, "reason": "local archive"}})
            public, local = _mod(base, "public", "public_mod"), _mod(base, "local", "revenantlib")
            art = ["graphics/other_author/a.png"]
            self.assertFalse(vendoring("open", None, public, policy, art)["allowed"])
            into_local = vendoring("open", None, local, policy, art)
            self.assertEqual((into_local["allowed"], into_local["must_stay_local_only"]), (True, True))
            self.assertTrue(vendoring("open", None, public, policy, ["graphics/mine/a.png"])["allowed"])

    def test_vendor_copy_refuses_a_script_under_a_local_only_path(self) -> None:
        with resolved_temp_dir() as base:
            provider = _mod(base, "provider", "open")
            _write(provider / "data" / "hullmods" / "hull_mods.csv", "name,id,script,desc\nRadar,x_radar,data.hullmods.XRadar,d\n")
            _write(provider / "data" / "hullmods" / "XRadar.java", "package data.hullmods;\nclass XRadar {}\n")
            policy = _policy(base, {"open": {"local_only": False, "reason": "MIT", "paths": [
                {"prefix": "data/hullmods/XRadar.java", "local_only": True, "reason": "script by another author"}]}})
            result = vendor_copy("hullmod", "x_radar", provider, _mod(base, "target", "public_mod"), policy_path=policy)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("XRadar.java", result["reason"])

    def test_the_decision_answer_is_unchanged(self) -> None:
        # gene describe writes this into gene.json's licence; PR B changes the schema, not this one.
        from bridgeforge.substitutes import revival_licence
        with resolved_temp_dir() as base:
            policy = _policy(base, {"open": {"local_only": False, "reason": "MIT", "paths": [ART]}})
            self.assertEqual(revival_licence("open", None, policy), {"decision": "RELEASABLE", "reason": "MIT"})
            self.assertEqual(decision("nobody", None, policy)["decision"], "UNRECORDED")


class CliTests(unittest.TestCase):
    def test_path_set_show_and_remove(self) -> None:
        with resolved_temp_dir() as base:
            policy = str(_policy(base, {"open": {"local_only": False, "reason": "MIT"}}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["release-policy", "path", "open", "graphics/other_author", "--reason", "theirs", "--policy", policy]), 0)
                self.assertEqual(main(["release-policy", "show", "open", "--policy", policy]), 0)
                self.assertEqual(main(["release-policy", "path", "open", "graphics/other_author", "--remove", "--policy", policy]), 0)
            self.assertIn("local-only path graphics/other_author: theirs", out.getvalue())
            self.assertNotIn("paths", _load_policy(Path(policy))["mods"]["open"])
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["release-policy", "path", "open", "../x", "--reason", "r", "--policy", policy]), 2)


class OnePlaceTests(unittest.TestCase):
    """GR-6: only release.py (the file format and its writers) and the ledger read the policy's internals."""

    INTERNALS = {"_load_policy", "policy_entry", "_licence_gate", "DEFAULT_POLICY_PATH", "_overlay_policy_fragments"}
    ALLOWED = {"bridgeforge/release.py", "bridgeforge/licence_ledger.py"}

    def test_no_other_module_imports_the_policy_internals(self) -> None:
        offenders = []
        for path in sorted((ROOT / "bridgeforge").rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative in self.ALLOWED:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == "release":
                    offenders += [f"{relative}: {alias.name}" for alias in node.names if alias.name in self.INTERNALS]
        self.assertEqual(offenders, [])

    def test_the_check_catches_an_import(self) -> None:
        tree = ast.parse("from .release import _load_policy\n")
        node = tree.body[0]
        self.assertTrue(isinstance(node, ast.ImportFrom) and node.names[0].name in self.INTERNALS)


if __name__ == "__main__":
    unittest.main()
