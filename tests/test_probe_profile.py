import tempfile
import unittest
from pathlib import Path

from bridgeforge.probe_config import (
    DEFAULT_PROFILE_APPLY,
    PROFILE_DIR,
    PROFILE_FILE,
    ProbeConfigError,
    build_probe_config,
    load_profile,
    parse_profile,
    write_probe_config,
)

try:
    import _winapi
except ImportError:  # pragma: no cover - non-Windows
    _winapi = None

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _make_fixture_mod(root: Path) -> Path:
    mod = root / "fixture_mod"
    (mod / "data" / "hulls").mkdir(parents=True)
    (mod / "data" / "variants").mkdir(parents=True)
    (mod / "mod_info.json").write_text('{"id":"fixture_mod"}', encoding="utf-8")
    (mod / "data" / "hulls" / "ship_data.csv").write_text("id,hints\nfx_hull1,\n", encoding="utf-8")
    return mod


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


class ParseProfileLineFormTests(unittest.TestCase):
    def test_rep_line(self) -> None:
        result = parse_profile("rep exipirated = FRIENDLY\n")
        self.assertEqual(result["setups"], ["rep:exipirated=FRIENDLY"])

    def test_credits_line(self) -> None:
        result = parse_profile("credits = 500000\n")
        self.assertEqual(result["setups"], ["credits:500000"])

    def test_ship_line_with_count(self) -> None:
        result = parse_profile("ship ART_dimention_manipulator x1\n")
        self.assertEqual(result["setups"], ["ship:ART_dimention_manipulator:1"])

    def test_ship_line_without_count(self) -> None:
        result = parse_profile("ship ART_dimention_manipulator\n")
        self.assertEqual(result["setups"], ["ship:ART_dimention_manipulator"])

    def test_spawn_line(self) -> None:
        result = parse_profile("spawn pirates 120\n")
        self.assertEqual(result["setups"], ["spawn-fleet:pirates:120"])

    def test_jump_line(self) -> None:
        result = parse_profile("jump Corvus\n")
        self.assertEqual(result["setups"], ["jump:Corvus"])

    def test_case_and_whitespace_tolerance(self) -> None:
        result = parse_profile("  REP   exipirated   =   friendly  \n   CREDITS=100\nSHIP fx_hull1   X2\n")
        self.assertEqual(
            result["setups"],
            ["rep:exipirated=friendly", "credits:100", "ship:fx_hull1:2"],
        )


class ParseProfileCommentsAndDisableTests(unittest.TestCase):
    def test_full_line_and_inline_comments(self) -> None:
        text = "# a full comment\ncredits = 500000   # starting cash\n\n"
        result = parse_profile(text)
        self.assertEqual(result["setups"], ["credits:500000"])

    def test_blank_lines_ignored(self) -> None:
        result = parse_profile("\n\ncredits = 100\n\n\n")
        self.assertEqual(result["setups"], ["credits:100"])

    def test_disabled_line_excluded_from_setups(self) -> None:
        result = parse_profile("credits = 500000\n-credits = 100\n")
        self.assertEqual(result["setups"], ["credits:500000"])
        self.assertEqual(result["disabled"], ["credits:100"])

    def test_disabled_line_still_validated(self) -> None:
        with self.assertRaises(ProbeConfigError):
            parse_profile("-credits = not-a-number\n")

    def test_disabled_apply_line_does_not_change_apply(self) -> None:
        result = parse_profile("-apply = every-load\ncredits = 1\n")
        self.assertEqual(result["apply"], DEFAULT_PROFILE_APPLY)


class ParseProfileApplyTests(unittest.TestCase):
    def test_default_apply_is_once_per_save(self) -> None:
        result = parse_profile("credits = 1\n")
        self.assertEqual(result["apply"], "once-per-save")

    def test_apply_every_load(self) -> None:
        result = parse_profile("apply = every-load\ncredits = 1\n")
        self.assertEqual(result["apply"], "every-load")

    def test_apply_case_and_space_tolerant(self) -> None:
        result = parse_profile("APPLY=EVERY-LOAD\n")
        self.assertEqual(result["apply"], "every-load")

    def test_unrecognized_apply_mode_raises(self) -> None:
        with self.assertRaises(ProbeConfigError) as ctx:
            parse_profile("apply = whenever\n")
        self.assertIn("apply mode", str(ctx.exception))


class ParseProfileErrorFormatTests(unittest.TestCase):
    def test_error_includes_source_and_line_number(self) -> None:
        with self.assertRaises(ProbeConfigError) as ctx:
            parse_profile("credits = 1\nrep noequals\n", source="myfile.txt")
        self.assertTrue(str(ctx.exception).startswith("myfile.txt:2:"))

    def test_unrecognized_line_raises(self) -> None:
        with self.assertRaises(ProbeConfigError) as ctx:
            parse_profile("frobnicate everything\n", source="p.txt")
        self.assertIn("p.txt:1:", str(ctx.exception))

    def test_malformed_setup_reuses_validate_setup_spec(self) -> None:
        # rep value must be a RepLevel name or a number -- validate_setup_spec's own message.
        with self.assertRaises(ProbeConfigError) as ctx:
            parse_profile("rep exipirated = not-a-level\n", source="p.txt")
        self.assertIn("p.txt:1:", str(ctx.exception))
        self.assertIn("RepLevel", str(ctx.exception))

    def test_missing_equals_in_credits(self) -> None:
        with self.assertRaises(ProbeConfigError):
            parse_profile("credits 500000\n")

    def test_missing_variant_in_ship(self) -> None:
        with self.assertRaises(ProbeConfigError):
            parse_profile("ship\n")

    def test_malformed_spawn(self) -> None:
        with self.assertRaises(ProbeConfigError):
            parse_profile("spawn pirates\n")


class LoadProfileTests(unittest.TestCase):
    def test_load_by_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.txt"
            path.write_text("credits = 42\n", encoding="utf-8")
            profile = load_profile(str(path))
            self.assertEqual(profile["setups"], ["credits:42"])
            self.assertEqual(profile["text"], "credits = 42\n")
            self.assertEqual(profile["path"], str(path.resolve()))

    def test_load_bundled_by_name(self) -> None:
        profile = load_profile("exigency-rep")
        self.assertIn("rep:exipirated=FRIENDLY", profile["setups"])
        self.assertEqual(profile["path"], str(PROFILE_DIR / "exigency-rep.txt"))

    def test_load_missing_raises(self) -> None:
        with self.assertRaises(ProbeConfigError):
            load_profile("does-not-exist-anywhere")

    def test_all_bundled_profiles_parse(self) -> None:
        # README.txt documents the format; it is not itself a profile (see the folder's README).
        for path in sorted(p for p in PROFILE_DIR.glob("*.txt") if p.name != "README.txt"):
            with self.subTest(profile=path.name):
                profile = load_profile(path.stem)
                self.assertGreaterEqual(len(profile["setups"]), 1)
                self.assertIn(profile["apply"], {"once-per-save", "every-load"})


class BuildProbeConfigMergeTests(unittest.TestCase):
    def test_profile_setups_merge_after_explicit_setups_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _make_fixture_mod(Path(directory))
            profile = parse_profile("credits = 500000\njump Corvus\n")
            config = build_probe_config(
                mod,
                setups=["rep:exipirated=FRIENDLY"],
                profile=profile,
            )
            self.assertEqual(
                config["setups"],
                ["rep:exipirated=FRIENDLY", "credits:500000", "jump:Corvus"],
            )

    def test_profile_apply_passes_through_to_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _make_fixture_mod(Path(directory))
            profile = parse_profile("apply = every-load\ncredits = 1\n")
            config = build_probe_config(mod, profile=profile)
            self.assertEqual(config["apply"], "every-load")

    def test_no_profile_defaults_apply_to_once_per_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _make_fixture_mod(Path(directory))
            config = build_probe_config(mod)
            self.assertEqual(config["apply"], "once-per-save")


class WriteProbeConfigProfileTests(unittest.TestCase):
    def test_writes_profile_raw_text_to_rig_common_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Directory junctions are not supported in this environment.")
            profile = load_profile("exigency-rep")
            result = write_probe_config(mod, rig, profile=profile)
            self.assertTrue(result["written"])
            profile_path = rig / "saves" / "common" / PROFILE_FILE
            self.assertTrue(profile_path.is_file())
            self.assertEqual(profile_path.read_text(encoding="utf-8"), profile["text"])
            self.assertEqual(result["config"]["apply"], profile["apply"])

    def test_no_profile_writes_no_profile_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Directory junctions are not supported in this environment.")
            write_probe_config(mod, rig)
            self.assertFalse((rig / "saves" / "common" / PROFILE_FILE).exists())

    def test_dry_run_does_not_write_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Directory junctions are not supported in this environment.")
            profile = load_profile("flux-basic")
            result = write_probe_config(mod, rig, profile=profile, dry_run=True)
            self.assertFalse(result["written"])
            self.assertFalse((rig / "saves" / "common" / PROFILE_FILE).exists())


class ProbeProfileParityTests(unittest.TestCase):
    """Both bridgeforge/probe_config.py's parse_profile (here) and probe-mod's
    ProbeProfile.java (hand-parser, no JVM test harness in this repo) must accept this exact
    fixture and agree on the resulting setups/apply. See the fixture file's header comment."""

    def test_shared_fixture_produces_expected_setups_and_apply(self) -> None:
        text = (FIXTURES_DIR / "probe_profile_parity.txt").read_text(encoding="utf-8")
        result = parse_profile(text, source="probe_profile_parity.txt")
        self.assertEqual(result["apply"], "every-load")
        self.assertEqual(
            result["setups"],
            [
                "rep:exipirated=FRIENDLY",
                "credits:500000",
                "ship:ART_dimention_manipulator:1",
                "ship:fx_hull1",
                "spawn-fleet:pirates:120",
                "jump:Corvus",
            ],
        )
        self.assertEqual(result["disabled"], ["credits:100", "ship:fx_hull2:2"])


if __name__ == "__main__":
    unittest.main()
