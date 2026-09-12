from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.bootstrap import bootstrap_mods
from bridgeforge.baseline import load_baseline_keys


def _snapshot(root: Path) -> dict[str, tuple[int, float]]:
    """A cheap fingerprint of every file under root (size + mtime), to assert a tree is untouched."""
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class BootstrapTests(unittest.TestCase):
    def _make_mod(self, root: Path, mod_id: str) -> Path:
        mod_dir = root / mod_id
        mod_dir.mkdir(parents=True)
        (mod_dir / "mod_info.json").write_text(
            json.dumps({"id": mod_id, "name": f"{mod_id} Mod", "version": "1.0", "gameVersion": "0.98a"}),
            encoding="utf-8",
        )
        (mod_dir / "data").mkdir()
        (mod_dir / "data" / "hulls").mkdir()
        (mod_dir / "data" / "hulls" / "ship_data.csv").write_text("id\nfoo\n", encoding="utf-8")
        return mod_dir

    def test_bootstrap_writes_baseline_and_r0_manifest_without_touching_mod_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()  # CI temp dirs are 8.3 short paths; the code resolves them
            mod_dir = self._make_mod(root, "fixture_mod")
            before = _snapshot(mod_dir)

            baselines_dir = root / "out" / "baselines"
            manifests_dir = root / "out" / "manifests"
            vanilla_core = root / "vanilla-core"
            vanilla_core.mkdir()

            summary = bootstrap_mods(
                [mod_dir],
                vanilla_core=vanilla_core,
                baselines_dir=baselines_dir,
                manifests_dir=manifests_dir,
            )

            after = _snapshot(mod_dir)
            self.assertEqual(before, after)  # nothing written inside the mod folder

            info = summary["fixture_mod"]
            self.assertEqual(info["mod_id"], "fixture_mod")
            self.assertTrue(info["baseline_written"])
            baseline_path = Path(info["baseline_path"])
            self.assertTrue(baseline_path.is_file())
            self.assertEqual(baseline_path, baselines_dir / "fixture_mod.json")
            load_baseline_keys(baseline_path)  # must be readable in the standard baseline format

            manifest_path = Path(info["manifest_path"])
            self.assertTrue(manifest_path.is_file())
            self.assertEqual(manifest_path.name, "r0.json")
            self.assertEqual(info["manifest_build"], 0)
            self.assertGreaterEqual(info["manifest_file_count"], 1)

    def test_bootstrap_never_overwrites_an_existing_baseline_unless_told_to(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_dir = self._make_mod(root, "fixture_mod")
            baselines_dir = root / "out" / "baselines"
            manifests_dir = root / "out" / "manifests"
            vanilla_core = root / "vanilla-core"
            vanilla_core.mkdir()
            baselines_dir.mkdir(parents=True)
            existing_baseline = baselines_dir / "fixture_mod.json"
            existing_baseline.write_text(json.dumps({"findings": ["sentinel-key"]}), encoding="utf-8")

            summary = bootstrap_mods(
                [mod_dir],
                vanilla_core=vanilla_core,
                baselines_dir=baselines_dir,
                manifests_dir=manifests_dir,
            )
            info = summary["fixture_mod"]
            self.assertFalse(info["baseline_written"])
            self.assertTrue(info["baseline_kept_existing"])
            self.assertEqual(load_baseline_keys(existing_baseline), {"sentinel-key"})  # untouched

            summary2 = bootstrap_mods(
                [mod_dir],
                vanilla_core=vanilla_core,
                baselines_dir=baselines_dir,
                manifests_dir=manifests_dir,
                overwrite=True,
            )
            info2 = summary2["fixture_mod"]
            self.assertTrue(info2["baseline_written"])
            self.assertNotEqual(load_baseline_keys(existing_baseline), {"sentinel-key"})

    def test_bootstrap_multiple_mods_default_label_falls_back_to_dir_name_when_id_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_a = self._make_mod(root, "mod_a")
            mod_b = root / "Mod-B-No-Id"
            mod_b.mkdir()
            (mod_b / "mod_info.json").write_text(json.dumps({"name": "No Id Mod", "version": "1.0"}), encoding="utf-8")
            baselines_dir = root / "out" / "baselines"
            manifests_dir = root / "out" / "manifests"
            vanilla_core = root / "vanilla-core"
            vanilla_core.mkdir()

            summary = bootstrap_mods(
                [mod_a, mod_b],
                vanilla_core=vanilla_core,
                baselines_dir=baselines_dir,
                manifests_dir=manifests_dir,
            )
            self.assertIn("mod_a", summary)
            self.assertIn("Mod-B-No-Id", summary)
            self.assertIsNone(summary["Mod-B-No-Id"]["mod_id"])
