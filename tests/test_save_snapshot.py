import json
import tempfile
import unittest
from pathlib import Path

try:
    import _winapi
except ImportError:  # pragma: no cover - non-Windows
    _winapi = None

from bridgeforge.save_snapshot import (
    SaveSnapshotError,
    snapshot_list,
    snapshot_restore,
    snapshot_tag,
)


def _make_rig(root: Path) -> Path | None:
    if _winapi is None:
        return None
    core_real = root / "core_real"
    core_real.mkdir()
    rig = root / "rig"
    rig.mkdir()
    try:
        _winapi.CreateJunction(str(core_real), str(rig / "starsector-core"))
    except OSError:
        return None
    return rig


def _make_save(rig: Path, name: str, *, tagged_name: str = "Exigency") -> Path:
    save = rig / "saves" / name
    save.mkdir(parents=True)
    (save / "campaign.xml").write_text("<Campaign z=\"1\"></Campaign>", encoding="utf-8")
    (save / "descriptor.xml").write_text(
        "<?xml version=\"1.0\" ?>\n"
        "<SaveGameData z=\"1\">\n"
        "<allModsEverEnabled z=\"2\">\n"
        "<EnabledModData z=\"3\">\n"
        "<spec z=\"4\">\n"
        "<id>exigency</id>\n"
        f"<name>{tagged_name}</name>\n"
        "</spec>\n"
        "</EnabledModData>\n"
        "</allModsEverEnabled>\n"
        "</SaveGameData>\n",
        encoding="utf-8",
    )
    return save


class SaveSnapshotRigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.rig = _make_rig(self.root)
        if self.rig is None:
            self.skipTest("Directory junctions are not supported in this environment.")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_refuses_non_junction_runtime(self) -> None:
        not_a_rig = self.root / "not_a_rig"
        (not_a_rig / "starsector-core").mkdir(parents=True)
        with self.assertRaises(SaveSnapshotError):
            snapshot_tag(not_a_rig, "save_Foo", "t1")

    def test_refuses_common_as_save_name(self) -> None:
        _make_save(self.rig, "common")
        with self.assertRaises(SaveSnapshotError):
            snapshot_tag(self.rig, "common", "t1")

    def test_tag_copies_save_and_writes_manifest_with_build_tags(self) -> None:
        _make_save(self.rig, "save_Foo", tagged_name="Exigency [BF r3]")
        result = snapshot_tag(self.rig, "save_Foo", "t1")
        self.assertEqual(result["source_save"], "save_Foo")
        snapshot_dir = Path(result["snapshot_dir"])
        self.assertTrue((snapshot_dir / "campaign.xml").is_file())
        self.assertTrue((snapshot_dir / "descriptor.xml").is_file())
        manifest_path = Path(result["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["tag"], "t1")
        self.assertEqual(manifest["source_save"], "save_Foo")
        self.assertEqual(manifest["bf_build_tags"], {"exigency": "Exigency [BF r3]"})
        self.assertIn("campaign.xml", manifest["hashes"])
        self.assertIn("descriptor.xml", manifest["hashes"])

    def test_tag_without_build_tag_suffix_has_empty_bf_build_tags(self) -> None:
        _make_save(self.rig, "save_Foo", tagged_name="Exigency")
        result = snapshot_tag(self.rig, "save_Foo", "t1")
        manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["bf_build_tags"], {})

    def test_tag_refuses_duplicate_tag(self) -> None:
        _make_save(self.rig, "save_Foo")
        snapshot_tag(self.rig, "save_Foo", "t1")
        with self.assertRaises(SaveSnapshotError):
            snapshot_tag(self.rig, "save_Foo", "t1")

    def test_tag_refuses_missing_save(self) -> None:
        with self.assertRaises(SaveSnapshotError):
            snapshot_tag(self.rig, "save_DoesNotExist", "t1")

    def test_list_returns_manifests(self) -> None:
        self.assertEqual(snapshot_list(self.rig), [])
        _make_save(self.rig, "save_Foo")
        snapshot_tag(self.rig, "save_Foo", "t1")
        listed = snapshot_list(self.rig)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["tag"], "t1")
        self.assertEqual(listed[0]["manifest"]["source_save"], "save_Foo")

    def test_restore_copies_back_under_new_name(self) -> None:
        save = _make_save(self.rig, "save_Foo")
        snapshot_tag(self.rig, "save_Foo", "t1")
        # mutate the live save after the snapshot, to prove restore comes from the snapshot copy
        (save / "campaign.xml").write_text("<Campaign z=\"1\">mutated</Campaign>", encoding="utf-8")

        result = snapshot_restore(self.rig, "t1", as_name="save_Restored")
        restored = Path(result["restored_to"])
        self.assertTrue(restored.is_dir())
        self.assertEqual(restored.name, "save_Restored")
        content = (restored / "campaign.xml").read_text(encoding="utf-8")
        self.assertNotIn("mutated", content)

    def test_restore_refuses_to_overwrite_without_replace(self) -> None:
        _make_save(self.rig, "save_Foo")
        snapshot_tag(self.rig, "save_Foo", "t1")
        with self.assertRaises(SaveSnapshotError):
            snapshot_restore(self.rig, "t1")  # save_Foo already exists as a live save

    def test_restore_replace_overwrites(self) -> None:
        save = _make_save(self.rig, "save_Foo")
        snapshot_tag(self.rig, "save_Foo", "t1")
        (save / "campaign.xml").write_text("<Campaign z=\"1\">mutated</Campaign>", encoding="utf-8")
        result = snapshot_restore(self.rig, "t1", replace=True)
        restored = Path(result["restored_to"])
        content = (restored / "campaign.xml").read_text(encoding="utf-8")
        self.assertNotIn("mutated", content)

    def test_restore_refuses_common_as_destination(self) -> None:
        _make_save(self.rig, "save_Foo")
        snapshot_tag(self.rig, "save_Foo", "t1")
        with self.assertRaises(SaveSnapshotError):
            snapshot_restore(self.rig, "t1", as_name="common")

    def test_restore_unknown_tag_raises(self) -> None:
        with self.assertRaises(SaveSnapshotError):
            snapshot_restore(self.rig, "no-such-tag")

    def test_never_writes_into_saves_common(self) -> None:
        _make_save(self.rig, "save_Foo")
        snapshot_tag(self.rig, "save_Foo", "t1")
        snapshot_restore(self.rig, "t1", as_name="save_Restored")
        self.assertFalse((self.rig / "saves" / "common").exists())


if __name__ == "__main__":
    unittest.main()
