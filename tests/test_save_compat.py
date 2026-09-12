from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.save_compat import check_save_compat, compare_builds


# ---------------------------------------------------------------------------
# Minimal .class file / jar builders, copied from tests/test_rc8_bytecode_checks.py
# (kept self-contained here rather than imported, since save_compat only cares
# about jar entry *names*, not bytecode content -- these bodies are throwaway).
# ---------------------------------------------------------------------------

def _u2(value: int) -> bytes:
    return value.to_bytes(2, "big")


def _utf8_entry(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return b"\x01" + _u2(len(encoded)) + encoded


def _class_entry(name_index: int) -> bytes:
    return b"\x07" + _u2(name_index)


def build_class_file(this_class: str, super_class: str = "java/lang/Object") -> bytes:
    """Build a minimal well-formed .class file (name is all save_compat inspects)."""
    pool: list[bytes] = []

    def add_utf8(text: str) -> int:
        pool.append(_utf8_entry(text))
        return len(pool)

    def add_class(name_index: int) -> int:
        pool.append(_class_entry(name_index))
        return len(pool)

    this_class_idx = add_class(add_utf8(this_class))
    super_class_idx = add_class(add_utf8(super_class))

    constant_pool_count = len(pool) + 1
    data = b"\xca\xfe\xba\xbe" + _u2(0) + _u2(52) + _u2(constant_pool_count)
    data += b"".join(pool)
    data += _u2(0x0021)
    data += _u2(this_class_idx)
    data += _u2(super_class_idx)
    data += _u2(0)  # interfaces_count
    data += _u2(0)  # fields_count
    data += _u2(0)  # methods_count
    data += _u2(0)  # attributes_count
    return data


def write_jar(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for member, content in members.items():
            archive.writestr(member, content)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


SAVE_HEADER = '<?xml version="1.0" ?>\n<CampaignEngine z="1">\n<sc z="2">\n'
SAVE_FOOTER = "</sc>\n</CampaignEngine>\n"


class SaveCompatLoadsTests(unittest.TestCase):
    def test_all_referenced_classes_present_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_dir = root / "mod"
            _write(mod_dir / "mod_info.json", '{"id":"mymod","name":"My Mod","version":"1.0"}')
            write_jar(
                mod_dir / "jars" / "mymod.jar",
                {
                    "data/scripts/mymod/MyModPlugin.class": build_class_file("data/scripts/mymod/MyModPlugin"),
                    "data/scripts/mymod/MyModOther.class": build_class_file("data/scripts/mymod/MyModOther"),
                },
            )
            save_xml = (
                SAVE_HEADER
                + '<MyModPlugin z="3" bF="1.0">\n'
                + '<other cl="data.scripts.mymod.MyModOther" z="4"></other>\n'
                + "</MyModPlugin>\n"
                + SAVE_FOOTER
            )
            save_dir = root / "save"
            _write(save_dir / "campaign.xml", save_xml)

            result = check_save_compat(save_dir, mod_dir)

            self.assertEqual(result["status"], "LOADS")
            self.assertEqual(result["mod_id"], "mymod")
            self.assertEqual(result["build_tag"], "My Mod")
            self.assertEqual(result["referenced"]["count"], 2)
            self.assertEqual(result["missing"], [])
            referenced_names = {entry["class"] for entry in result["referenced"]["classes"]}
            self.assertEqual(
                referenced_names,
                {"data.scripts.mymod.MyModPlugin", "data.scripts.mymod.MyModOther"},
            )

    def test_save_dir_and_direct_campaign_xml_path_agree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_dir = root / "mod"
            _write(mod_dir / "mod_info.json", '{"id":"mymod"}')
            write_jar(
                mod_dir / "jars" / "mymod.jar",
                {"data/scripts/mymod/MyModPlugin.class": build_class_file("data/scripts/mymod/MyModPlugin")},
            )
            save_xml = SAVE_HEADER + '<MyModPlugin z="3"></MyModPlugin>\n' + SAVE_FOOTER
            save_dir = root / "save"
            _write(save_dir / "campaign.xml", save_xml)

            via_dir = check_save_compat(save_dir, mod_dir)
            via_file = check_save_compat(save_dir / "campaign.xml", mod_dir)

            self.assertEqual(via_dir["status"], via_file["status"])
            self.assertEqual(via_dir["referenced"]["count"], via_file["referenced"]["count"])
            self.assertEqual(via_dir["status"], "LOADS")


class SaveCompatMissingClassTests(unittest.TestCase):
    def test_removed_class_referenced_by_save_is_will_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_dir = root / "mod"
            _write(mod_dir / "mod_info.json", '{"id":"mymod"}')
            # Rebuild dropped MyModRemoved, but MyModOther (same package) survives,
            # so the removed class's package is still attributable to this mod.
            write_jar(
                mod_dir / "jars" / "mymod.jar",
                {"data/scripts/mymod/MyModOther.class": build_class_file("data/scripts/mymod/MyModOther")},
            )
            save_xml = (
                SAVE_HEADER
                + '<holder cl="data.scripts.mymod.MyModRemoved" z="3"></holder>\n'
                + '<other cl="data.scripts.mymod.MyModOther" z="4"></other>\n'
                + SAVE_FOOTER
            )
            save_dir = root / "save"
            _write(save_dir / "campaign.xml", save_xml)

            result = check_save_compat(save_dir, mod_dir)

            self.assertEqual(result["status"], "WILL_FAIL")
            missing_refs = {entry["reference"] for entry in result["missing"]}
            self.assertIn("data.scripts.mymod.MyModRemoved", missing_refs)
            entry = next(e for e in result["missing"] if e["reference"] == "data.scripts.mymod.MyModRemoved")
            self.assertEqual(entry["occurrences"], 1)
            self.assertTrue(entry["sample_path"])


class SaveCompatInnerClassTests(unittest.TestCase):
    def test_inner_class_outer_plus_inner_alias_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_dir = root / "mod"
            _write(mod_dir / "mod_info.json", '{"id":"mymod"}')
            write_jar(
                mod_dir / "jars" / "mymod.jar",
                {
                    "data/scripts/mymod/MyModMovement.class": build_class_file("data/scripts/mymod/MyModMovement"),
                    "data/scripts/mymod/MyModMovement$Waypoint.class": build_class_file(
                        "data/scripts/mymod/MyModMovement$Waypoint"
                    ),
                },
            )
            save_xml = (
                SAVE_HEADER
                + '<MyModMovement z="3">\n'
                + '<WAYPOINTS z="4">\n'
                + '<MyModMovementWaypoint z="5">\n'
                + "<loc>1.0|2.0</loc>\n"
                + "</MyModMovementWaypoint>\n"
                + "</WAYPOINTS>\n"
                + "</MyModMovement>\n"
                + SAVE_FOOTER
            )
            save_dir = root / "save"
            _write(save_dir / "campaign.xml", save_xml)

            result = check_save_compat(save_dir, mod_dir)

            self.assertEqual(result["status"], "LOADS")
            referenced_names = {entry["class"] for entry in result["referenced"]["classes"]}
            self.assertIn("data.scripts.mymod.MyModMovement$Waypoint", referenced_names)
            waypoint_entry = next(
                e for e in result["referenced"]["classes"] if e["class"] == "data.scripts.mymod.MyModMovement$Waypoint"
            )
            self.assertIn("MyModMovementWaypoint", waypoint_entry["aliases"])
            # WAYPOINTS is an all-caps field tag, never a class reference.
            self.assertNotIn("WAYPOINTS", {c["class"] for c in result["referenced"]["classes"]})


class SaveCompatVanillaAliasTests(unittest.TestCase):
    def test_short_vanilla_style_alias_is_never_treated_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_dir = root / "mod"
            vanilla_dir = root / "vanilla"
            _write(mod_dir / "mod_info.json", '{"id":"mymod"}')
            write_jar(
                mod_dir / "jars" / "mymod.jar",
                {"data/scripts/mymod/MyModPlugin.class": build_class_file("data/scripts/mymod/MyModPlugin")},
            )
            # An unrelated vanilla class, standing in for the real starfarer-core jars;
            # "Sstm" itself is a cryptic short alias this module deliberately never decodes.
            write_jar(
                vanilla_dir / "starfarer.api.jar",
                {"com/fs/starfarer/campaign/StarSystem.class": build_class_file("com/fs/starfarer/campaign/StarSystem")},
            )
            save_xml = (
                SAVE_HEADER
                + '<MyModPlugin z="3"></MyModPlugin>\n'
                + '<market cl="Sstm" z="4"></market>\n'
                + SAVE_FOOTER
            )
            save_dir = root / "save"
            _write(save_dir / "campaign.xml", save_xml)

            result = check_save_compat(save_dir, mod_dir, vanilla_core=vanilla_dir)

            self.assertEqual(result["status"], "LOADS")
            self.assertEqual(result["missing"], [])
            referenced_names = {entry["class"] for entry in result["referenced"]["classes"]}
            self.assertNotIn("Sstm", referenced_names)


class CompareBuildsTests(unittest.TestCase):
    def test_dropped_class_referenced_by_save_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_jar = root / "old.jar"
            new_jar = root / "new.jar"
            write_jar(
                old_jar,
                {
                    "data/scripts/mymod/MyModPlugin.class": build_class_file("data/scripts/mymod/MyModPlugin"),
                    "data/scripts/mymod/MyModDropped.class": build_class_file("data/scripts/mymod/MyModDropped"),
                },
            )
            write_jar(
                new_jar,
                {"data/scripts/mymod/MyModPlugin.class": build_class_file("data/scripts/mymod/MyModPlugin")},
            )
            save_xml = (
                SAVE_HEADER
                + '<MyModPlugin z="3"></MyModPlugin>\n'
                + '<dropped cl="data.scripts.mymod.MyModDropped" z="4"></dropped>\n'
                + SAVE_FOOTER
            )
            save_dir = root / "save"
            _write(save_dir / "campaign.xml", save_xml)

            result = compare_builds(save_dir, old_jar, new_jar)

            self.assertEqual(result["status"], "WILL_FAIL")
            self.assertIn("data.scripts.mymod.MyModDropped", result["dropped_in_new"])
            self.assertNotIn("data.scripts.mymod.MyModPlugin", result["dropped_in_new"])

    def test_no_dropped_classes_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_jar = root / "old.jar"
            new_jar = root / "new.jar"
            class_bytes = build_class_file("data/scripts/mymod/MyModPlugin")
            write_jar(old_jar, {"data/scripts/mymod/MyModPlugin.class": class_bytes})
            write_jar(new_jar, {"data/scripts/mymod/MyModPlugin.class": class_bytes})
            save_xml = SAVE_HEADER + '<MyModPlugin z="3"></MyModPlugin>\n' + SAVE_FOOTER
            save_dir = root / "save"
            _write(save_dir / "campaign.xml", save_xml)

            result = compare_builds(save_dir, old_jar, new_jar)

            self.assertEqual(result["status"], "LOADS")
            self.assertEqual(result["dropped_in_new"], [])


class SaveCompatLargeFileStreamingTests(unittest.TestCase):
    def test_large_synthetic_save_is_handled_by_streaming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_dir = root / "mod"
            _write(mod_dir / "mod_info.json", '{"id":"mymod"}')
            write_jar(
                mod_dir / "jars" / "mymod.jar",
                {"data/scripts/mymod/MyModPlugin.class": build_class_file("data/scripts/mymod/MyModPlugin")},
            )
            save_dir = root / "save"
            campaign = save_dir / "campaign.xml"
            save_dir.mkdir(parents=True, exist_ok=True)
            filler_line = '<fleetMember z="0" fp="12.0" hullId="filler_hull_id_padding_value"></fleetMember>\n'
            target_bytes = 5 * 1024 * 1024
            with campaign.open("w", encoding="utf-8") as handle:
                handle.write(SAVE_HEADER)
                written = 0
                count = 0
                while written < target_bytes:
                    handle.write(filler_line)
                    written += len(filler_line)
                    count += 1
                    if count % 5000 == 0:
                        handle.write('<MyModPlugin z="99"></MyModPlugin>\n')
                handle.write(SAVE_FOOTER)

            self.assertGreaterEqual(campaign.stat().st_size, target_bytes)
            result = check_save_compat(save_dir, mod_dir)

            self.assertEqual(result["status"], "LOADS")
            self.assertGreaterEqual(result["referenced"]["count"], 1)
            plugin_entry = next(
                e for e in result["referenced"]["classes"] if e["class"] == "data.scripts.mymod.MyModPlugin"
            )
            self.assertGreater(plugin_entry["occurrences"], 1)


if __name__ == "__main__":
    unittest.main()
