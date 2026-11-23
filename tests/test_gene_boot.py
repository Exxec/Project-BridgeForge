"""94.G2: `gene boot stage` and `gene boot evaluate`, the boot halves of a gene's proofs, on synthetic proofs and runs.

The cases follow P1's real boots on Test1: P1B-SUB2-20261120 (the subtracted donor, Fatal on a hull mod a recorded dependent
builds in: BLOCKED_BY_DEPENDENT, owner 2026-11-20), LOBSTER-SUB-20261120 (a Fatal no recorded dependent explains),
P1B-CAR-20261120 (a carrier the game never loaded, 93.65) and P1B-CAR3-20261122 (a carrier that loaded and passed).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.archive import ArchiveError, archive_mod
from bridgeforge.genome.boot import BLOCKED, BOOTED, STAGED_MARKER, BootError, _condition_held, evaluate, stage
from bridgeforge.probe.probe_group import ProbeGroupError
from bridgeforge.probe.probe_record import record_group
from bridgeforge.run_manifest import CONFIG_RELATIVE
from tests.bound_runs import CONTENT_IDS, MENU, PROBE, bound_run, make_rig
from tests.support import resolved_temp_dir

IDENTITY = "ab" * 32
DONOR, CARRIER = "fx_donor", "gene_carrier_fx"
PROOF_NAME = "p9-fx_tanks-20261122"
FATAL_TANKS = "12:00:01 dialog: 'Starsector' text: 'Fatal: Hullmod fx_tanks not found!'"
FATAL_GUN = "12:00:01 dialog: 'Starsector' text: 'Fatal: Weapon spec [fx_gun] not found!'"


def _json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def found(half: str, mod_id: str) -> str:
    """RC7's launcher line for a mod folder it read (P034-TANIA-20261122)."""
    return (f"500  [main] INFO  com.fs.starfarer.launcher.ModManager  - Found mod: {mod_id} "
            f"[C:\\rig\\starsector-core\\..\\mods\\{PROOF_NAME}-{half}]")


def mod_error(message: str) -> list[str]:
    """An exception whose frame is in a mod's scripts: log-triage's MOD-ERROR."""
    return [f"300 [main] ERROR com.fs.starfarer.loading.SpecStore  - java.lang.IllegalStateException: {message}",
            "\tat data.scripts.FxPlugin.onApplicationLoad(FxPlugin.java:12)"]


def make_proof(root: Path, *, loaded: str = "always", static_verdict: str = "PASS", needs_mods: list[str] | None = None,
               provides: list[str] | None = None, set_proof: bool = False, dependents: list[dict] | None = None) -> Path:
    """A proof folder as `gene prove` writes it: gene.json, both static proofs and the two work copies."""
    proof = root / PROOF_NAME
    gene = {"identity": IDENTITY, "schema_version": 4, "provides": provides or ["hullmod:fx_tanks", "hull:fx_ship"],
            "needs": {"vanilla": [], "mods": needs_mods or [], "genes": []}, "build": {"game_version": "0.98.5a-RC7"}}
    _json(proof / "gene.json", gene)
    head = {"evidence": "bridgeforge-gene-evidence", "gene": {"identity": IDENTITY, "schema_version": 4}, "verdict": static_verdict}
    rows = dependents if dependents is not None else [
        {"from": "data/hulls/fx_other.ship", "to": "hullmod:fx_tanks", "grade": "reference", "loaded": loaded}]
    _json(proof / "subtraction-proof.json", {**head, "kind": "subtraction-proof", "dependents": rows})
    _json(proof / ("set-isolation-proof.json" if set_proof else "isolation-proof.json"), {**head, "kind": "isolation-proof"})
    for half, mod_id in (("subtraction", DONOR), ("carrier", CARRIER)):
        _json(proof / "work" / half / "mod_info.json", {"id": mod_id, "name": mod_id, "version": "1.0", "description": "x"})
        _json(proof / "work" / half / "data" / "config" / "settings.json", {"half": half})
    return proof


def _config(mod_id: str, hulls: list[str]) -> dict:
    return {"group_members": {mod_id: {"hulls": hulls, "variants": [], "wings": [], "items": [], "factions": [],
                                       "commodities": [], "missions": [], "classes": []}}}


def boot_run(root: Path, proof: Path, half: str, test_id: str, log: list[str], dialogs: list[str] | tuple | None = (),
             config: dict | None = None, release: bool = True, loaded_line: bool = True,
             providers: dict[str, list[str]] | None = None) -> tuple[Path, Path]:
    """Stage the half into a queue, run it on a rig (synthetic log, with the launcher's `Found mod` line unless
    `loaded_line` is off, and a dialog log unless `dialogs` is None), release it. Returns (rig, queue)."""
    rig = make_rig(root, providers)
    if config is not None:
        _json(rig / CONFIG_RELATIVE, config)
    queue = root / "queue"
    staged = stage(proof, half, queue, rig)
    mod_id = staged["mod_id"]
    lines = ([found(half, mod_id)] if loaded_line else []) + log
    bound_run(root, {mod_id: Path(staged["workspace"])}, test_id, lines, rig=rig, expected=(), release=release, providers=providers)
    if dialogs is not None:
        (rig / "logs" / f"{test_id}.windows.txt").write_text("".join(f"{d}\n" for d in dialogs), encoding="utf-8")
    return rig, queue


class StageTests(unittest.TestCase):
    def test_stage_copies_the_work_copy_with_a_marker_and_moves_an_older_copy_aside(self) -> None:
        with resolved_temp_dir() as root:
            proof, rig, queue = make_proof(root), make_rig(root), root / "queue"
            first = stage(proof, "carrier", queue, rig, today="2026-11-22")
            workspace = Path(first["workspace"])
            self.assertEqual(workspace.name, f"{PROOF_NAME}-carrier")
            self.assertTrue((workspace / "working" / "data" / "config" / "settings.json").is_file())
            marker = json.loads((workspace / STAGED_MARKER).read_text(encoding="utf-8"))
            self.assertEqual((marker["half"], marker["mod_id"], marker["gene"]["identity"]), ("carrier", CARRIER, IDENTITY))
            self.assertEqual(len(marker["tree_sha256"]), 64)
            self.assertIsNone(first["replaced"])
            second = stage(proof, "carrier", queue, rig, today="2026-11-22")
            self.assertEqual(Path(second["replaced"]), queue / "_replaced-2026-11-22" / workspace.name)
            self.assertTrue((Path(second["replaced"]) / STAGED_MARKER).is_file())  # moved, never deleted

    def test_a_copy_that_fails_part_way_is_still_marked(self) -> None:
        with resolved_temp_dir() as root:
            proof, rig, queue = make_proof(root), make_rig(root), root / "queue"
            with mock.patch("bridgeforge.genome.boot.shutil.copytree", side_effect=OSError("disk full")), self.assertRaises(OSError):
                stage(proof, "subtraction", queue, rig)
            self.assertTrue((queue / f"{PROOF_NAME}-subtraction" / STAGED_MARKER).is_file())

    def test_stage_refuses_a_half_whose_static_proof_did_not_pass(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root, static_verdict="FAIL")
            with self.assertRaisesRegex(BootError, "not PASS"):
                stage(proof, "subtraction", root / "queue", make_rig(root))
            self.assertFalse((root / "queue").exists())

    def test_stage_refuses_a_rig_without_a_mod_the_gene_needs(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root, needs_mods=["MagicLib", "lw_lazylib"])
            rig = make_rig(root, providers={"lw_lazylib": []})
            with self.assertRaisesRegex(BootError, "lacks mod\\(s\\) the gene needs: MagicLib"):
                stage(proof, "carrier", root / "queue", rig)

    def test_a_static_proof_about_another_gene_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            other = json.loads((proof / "isolation-proof.json").read_text(encoding="utf-8"))
            _json(proof / "isolation-proof.json", {**other, "gene": {"identity": "cd" * 32, "schema_version": 4}})
            with self.assertRaisesRegex(BootError, "about another gene"):
                stage(proof, "carrier", root / "queue", make_rig(root))

    def test_a_gene_set_proof_stages_its_carrier(self) -> None:
        with resolved_temp_dir() as root:
            staged = stage(make_proof(root, set_proof=True), "carrier", root / "queue", make_rig(root))
            self.assertEqual(staged["mod_id"], CARRIER)


class SubtractionTests(unittest.TestCase):
    def test_a_fatal_naming_a_recorded_dependent_is_blocked_by_dependent_and_passes(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "SUB-1", [MENU], [FATAL_TANKS])
            result = evaluate(proof, "subtraction", rig, "SUB-1")
            self.assertEqual((result["verdict"], result["boot_verdict"]), ("PASS", BLOCKED))
            self.assertEqual(result["explained"][0]["dependents"], ["data/hulls/fx_other.ship -> hullmod:fx_tanks"])
            written = json.loads((proof / "boot-subtraction-SUB-1.json").read_text(encoding="utf-8"))
            self.assertEqual((written["kind"], written["boot_half"], written["mod_id"]), ("gene-boot", "subtraction", DONOR))
            self.assertEqual(sorted(i["path"] for i in written["inputs"]),
                             ["boot/SUB-1/SUB-1.manifest.json", "boot/SUB-1/SUB-1.stdout.log", "boot/SUB-1/SUB-1.windows.txt"])
            self.assertTrue((proof / "boot" / "SUB-1" / "SUB-1.windows.txt").is_file())
            self.assertNotIn("boot", json.loads((proof / "subtraction-proof.json").read_text(encoding="utf-8")))  # static proof untouched

    def test_a_fatal_no_recorded_dependent_explains_fails(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "SUB-2", [MENU], [FATAL_TANKS, FATAL_GUN])
            result = evaluate(proof, "subtraction", rig, "SUB-2")
            self.assertEqual(result["verdict"], "FAIL")
            self.assertEqual(len(result["unexplained"]), 1)
            self.assertIn("fx_gun", result["unexplained"][0])

    def test_a_dependent_whose_load_condition_did_not_hold_explains_nothing(self) -> None:
        for loaded in ("on mission start", "unknown", "with nexerelin"):
            with self.subTest(loaded=loaded), resolved_temp_dir() as root:
                proof = make_proof(root, loaded=loaded)
                rig, _ = boot_run(root, proof, "subtraction", "SUB-3", [MENU], [FATAL_TANKS])
                self.assertEqual(evaluate(proof, "subtraction", rig, "SUB-3")["verdict"], "FAIL")

    def test_a_dependent_loaded_with_an_enabled_mod_explains_its_line(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root, loaded="with lw_lazylib, nexerelin")
            rig, _ = boot_run(root, proof, "subtraction", "SUB-3B", [MENU], [FATAL_TANKS], providers={"lw_lazylib": []})
            self.assertEqual(evaluate(proof, "subtraction", rig, "SUB-3B")["boot_verdict"], BLOCKED)

    def test_a_dependent_whose_target_the_gene_does_not_provide_explains_nothing(self) -> None:
        for to in ("", "weapon:fx_gun"):
            with self.subTest(to=to), resolved_temp_dir() as root:
                proof = make_proof(root, dependents=[{"from": "data/x.csv", "to": to, "grade": "reference", "loaded": "always"}])
                rig, _ = boot_run(root, proof, "subtraction", "SUB-3C", [MENU], [FATAL_GUN])
                self.assertEqual(evaluate(proof, "subtraction", rig, "SUB-3C")["verdict"], "FAIL")

    def test_an_id_inside_a_longer_id_is_not_named(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            longer = "12:00:01 dialog: 'Starsector' text: 'Fatal: Hullmod fx_tanks_mk2 not found!'"
            rig, _ = boot_run(root, proof, "subtraction", "SUB-4", [MENU], [longer])
            self.assertEqual(evaluate(proof, "subtraction", rig, "SUB-4")["verdict"], "FAIL")

    def test_a_long_line_is_matched_whole_and_kept_short(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            long_fatal = f"12:00:01 dialog: 'Starsector' text: 'Fatal: {'x ' * 200}Hullmod fx_tanks not found!'"
            rig, _ = boot_run(root, proof, "subtraction", "SUB-4C", [MENU], [long_fatal])
            result = evaluate(proof, "subtraction", rig, "SUB-4C")
            self.assertEqual(result["boot_verdict"], BLOCKED)
            self.assertLessEqual(len(result["fatal"][0]), 300)

    def test_a_mod_error_is_judged_like_a_fatal(self) -> None:
        cases = (("no fx_gun here", "FAIL"), ("hull mod fx_tanks is missing", "PASS"))
        for message, verdict in cases:
            with self.subTest(message=message), resolved_temp_dir() as root:
                proof = make_proof(root)
                rig, _ = boot_run(root, proof, "subtraction", "SUB-4B", [MENU, *mod_error(message)])
                self.assertEqual(evaluate(proof, "subtraction", rig, "SUB-4B")["verdict"], verdict)

    def test_the_main_menu_with_no_fatal_is_booted(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "SUB-5", [MENU])
            result = evaluate(proof, "subtraction", rig, "SUB-5")
            self.assertEqual((result["verdict"], result["boot_verdict"]), ("PASS", BOOTED))

    def test_neither_the_main_menu_nor_a_fatal_is_unknown(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "SUB-6", ["5 [main] INFO  x.Y  - starting"], loaded_line=False)
            self.assertEqual(evaluate(proof, "subtraction", rig, "SUB-6")["verdict"], "UNKNOWN")

    def test_a_donor_read_then_stalled_before_the_menu_is_unknown(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "SUB-6B", ["5 [main] INFO  x.Y  - loading textures"])
            result = evaluate(proof, "subtraction", rig, "SUB-6B")
            self.assertEqual((result["verdict"], result["boot_verdict"], result["found"]), ("UNKNOWN", "NO_MAIN_MENU", True))

    def test_a_found_line_counts_only_for_this_mod_in_this_folder(self) -> None:
        other_folder = ("500  [main] INFO  com.fs.starfarer.launcher.ModManager  - Found mod: fx_donor "
                        "[C:\\rig\\starsector-core\\..\\mods\\fx_donor_original]")
        other_id = found("subtraction", "someone_else")
        for line in (other_folder, other_id):
            with self.subTest(line=line[-40:]), resolved_temp_dir() as root:
                proof = make_proof(root)
                rig, _ = boot_run(root, proof, "subtraction", "SUB-6C", [line, MENU], loaded_line=False)
                self.assertEqual(evaluate(proof, "subtraction", rig, "SUB-6C")["boot_verdict"], "NOT_LOADED")

    def test_a_donor_the_game_did_not_load_fails(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            log = [f"607 [main] ERROR com.fs.starfarer.loading.ModManager  - Error loading mod from [..\\mods\\{PROOF_NAME}-subtraction]",
                   '608 [main] ERROR com.fs.starfarer.loading.ModManager  - JSONObject["description"] not found.', MENU]
            rig, _ = boot_run(root, proof, "subtraction", "SUB-7", log)
            result = evaluate(proof, "subtraction", rig, "SUB-7")
            self.assertEqual((result["verdict"], result["boot_verdict"]), ("FAIL", "NOT_LOADED"))

    def test_a_main_menu_without_the_launcher_reading_the_donor_fails(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "SUB-7B", [MENU], loaded_line=False)
            self.assertEqual(evaluate(proof, "subtraction", rig, "SUB-7B")["boot_verdict"], "NOT_LOADED")

    def test_another_enabled_mod_that_did_not_load_makes_it_unknown(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            log = ["607 [main] ERROR com.fs.starfarer.loading.ModManager  - Error loading mod from [..\\mods\\lw_lazylib]",
                   "608 [main] ERROR com.fs.starfarer.loading.ModManager  - bad json", MENU]
            rig, _ = boot_run(root, proof, "subtraction", "SUB-7C", log, providers={"lw_lazylib": []})
            result = evaluate(proof, "subtraction", rig, "SUB-7C")
            self.assertEqual((result["verdict"], result["boot_verdict"]), ("UNKNOWN", "OTHER_NOT_LOADED"))

    def test_a_run_without_a_dialog_log_cannot_pass(self) -> None:
        for dialogs_fatal in (False, True):
            with self.subTest(blocked=dialogs_fatal), resolved_temp_dir() as root:
                proof = make_proof(root)
                log = [MENU, *mod_error("hull mod fx_tanks is missing")] if dialogs_fatal else [MENU]
                rig, _ = boot_run(root, proof, "subtraction", "SUB-8", log, dialogs=None)
                result = evaluate(proof, "subtraction", rig, "SUB-8")
                self.assertEqual((result["verdict"], result["boot_verdict"]), ("UNKNOWN", "NO_DIALOG_LOG"))


class CarrierTests(unittest.TestCase):
    def test_a_loaded_carrier_the_probe_passes_passes_and_lists_what_the_probe_saw(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "carrier", "CAR-1", [MENU, CONTENT_IDS], config=_config(CARRIER, ["fx_ship"]))
            result = evaluate(proof, "carrier", rig, "CAR-1")
            self.assertEqual((result["verdict"], result["member_verdict"]), ("PASS", "PASS"))
            # the probe checks hulls; it has no check of hull mods
            self.assertEqual(result["provided"], {"hull:fx_ship": "OBSERVED", "hullmod:fx_tanks": "NOT_OBSERVED"})

    def test_a_carrier_the_probe_fails_fails(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            failed = PROBE + "BF-PROBE|0.3.4|content-ids|FAIL|hull:fx_ship|not found"
            rig, _ = boot_run(root, proof, "carrier", "CAR-2", [MENU, CONTENT_IDS, failed], config=_config(CARRIER, ["fx_ship"]))
            result = evaluate(proof, "carrier", rig, "CAR-2")
            self.assertEqual((result["verdict"], result["member_verdict"]), ("FAIL", "FAIL"))
            self.assertEqual(result["provided"]["hull:fx_ship"], "NOT_OBSERVED")

    def test_a_carrier_with_a_fatal_fails_even_if_it_names_a_dependent(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "carrier", "CAR-3", [MENU, CONTENT_IDS], [FATAL_TANKS], config=_config(CARRIER, []))
            result = evaluate(proof, "carrier", rig, "CAR-3")
            self.assertEqual(result["verdict"], "FAIL")
            self.assertIn("1 Fatal", result["why"])  # judged on the Fatal itself, not only on the probe report's verdict

    def test_a_carrier_the_game_did_not_load_or_read_fails(self) -> None:
        error = [f"607 [main] ERROR com.fs.starfarer.loading.ModManager  - Error loading mod from [..\\mods\\{PROOF_NAME}-carrier]",
                 '608 [main] ERROR com.fs.starfarer.loading.ModManager  - JSONObject["description"] not found.']
        for log, loaded_line in ((error, True), ([], False)):
            with self.subTest(loaded_line=loaded_line), resolved_temp_dir() as root:
                proof = make_proof(root)
                rig, _ = boot_run(root, proof, "carrier", "CAR-4", [*log, MENU, CONTENT_IDS], config=_config(CARRIER, []),
                                  loaded_line=loaded_line)
                result = evaluate(proof, "carrier", rig, "CAR-4")
                self.assertEqual((result["verdict"], result["boot_verdict"]), ("FAIL", "NOT_LOADED"))

    def test_a_carrier_without_the_main_menu_or_a_dialog_log_is_unknown(self) -> None:
        for log, dialogs, boot in (([CONTENT_IDS], (), "NO_MAIN_MENU"), ([MENU, CONTENT_IDS], None, "NO_DIALOG_LOG")):
            with self.subTest(boot=boot), resolved_temp_dir() as root:
                proof = make_proof(root)
                rig, _ = boot_run(root, proof, "carrier", "CAR-5", log, dialogs, config=_config(CARRIER, []))
                result = evaluate(proof, "carrier", rig, "CAR-5")
                self.assertEqual((result["verdict"], result["boot_verdict"]), ("UNKNOWN", boot))


class BindingTests(unittest.TestCase):
    def test_a_run_of_a_copy_that_is_not_the_proofs_is_refused_and_nothing_is_written(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "BIND-1", [MENU])
            _json(proof / "work" / "subtraction" / "data" / "config" / "settings.json", {"changed": True})
            with self.assertRaisesRegex(BootError, "not the proof's work copy"):
                evaluate(proof, "subtraction", rig, "BIND-1")
            self.assertFalse((proof / "boot").exists())
            self.assertFalse((proof / "boot-subtraction-BIND-1.json").exists())

    def test_a_run_without_a_manifest_or_of_another_half_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "BIND-2", [MENU])
            with self.assertRaisesRegex(BootError, "not bound to anything"):
                evaluate(proof, "subtraction", rig, "BIND-NONE")
            with self.assertRaisesRegex(BootError, f"did not test {CARRIER}"):
                evaluate(proof, "carrier", rig, "BIND-2")

    def test_a_run_drifted_since_it_was_prepared_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, queue = boot_run(root, proof, "subtraction", "BIND-3", [MENU])
            _json(queue / f"{PROOF_NAME}-subtraction" / "working" / "extra.json", {})
            with self.assertRaisesRegex(BootError, "not bound to the proof's subtraction copy"):
                evaluate(proof, "subtraction", rig, "BIND-3")

    def test_a_run_never_released_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "BIND-5", [MENU], release=False)
            with self.assertRaisesRegex(BootError, "no completion record"):
                evaluate(proof, "subtraction", rig, "BIND-5")

    def test_a_proof_whose_static_half_no_longer_passes_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "BIND-6", [MENU])
            static = json.loads((proof / "subtraction-proof.json").read_text(encoding="utf-8"))
            _json(proof / "subtraction-proof.json", {**static, "verdict": "FAIL"})
            with self.assertRaisesRegex(BootError, "not PASS"):
                evaluate(proof, "subtraction", rig, "BIND-6")

    def test_a_run_is_evaluated_once(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "BIND-4", [MENU])
            evaluate(proof, "subtraction", rig, "BIND-4")
            with self.assertRaisesRegex(BootError, "evaluated for this proof before"):
                evaluate(proof, "subtraction", rig, "BIND-4")

    def test_a_failure_while_writing_removes_the_copies_so_the_run_can_be_evaluated_again(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            rig, _ = boot_run(root, proof, "subtraction", "BIND-7", [MENU])
            with mock.patch("bridgeforge.genome.evidence.header", side_effect=ValueError("bad header")):
                with self.assertRaisesRegex(BootError, "could not write the evidence"):
                    evaluate(proof, "subtraction", rig, "BIND-7")
            self.assertFalse((proof / "boot" / "BIND-7").exists())
            self.assertEqual(evaluate(proof, "subtraction", rig, "BIND-7")["verdict"], "PASS")


class RecordRefusalTests(unittest.TestCase):
    def test_probe_group_record_refuses_a_gene_boot_workspace(self) -> None:
        with resolved_temp_dir() as root:
            proof = make_proof(root)
            config = _config(CARRIER, ["fx_ship"])
            rig, queue = boot_run(root, proof, "carrier", "REC-1", [MENU, CONTENT_IDS], config=config)
            with self.assertRaisesRegex(ProbeGroupError, "gene boot copy"):
                record_group(rig / "logs" / "REC-1.stdout.log", config, queue, rig, test_id="REC-1")
            self.assertFalse((queue / "_live").exists())  # refused before the run record

    def test_archive_refuses_a_gene_boot_workspace(self) -> None:
        with resolved_temp_dir() as root:
            workspace = Path(stage(make_proof(root), "subtraction", root / "queue", make_rig(root))["workspace"])
            with self.assertRaisesRegex(ArchiveError, "gene boot copy"):
                archive_mod(workspace, root / "Done")
            self.assertFalse((root / "Done").exists())


class ConditionTests(unittest.TestCase):
    def test_load_conditions(self) -> None:
        enabled = {"MagicLib"}
        self.assertTrue(_condition_held("always", enabled))
        self.assertTrue(_condition_held("with MagicLib, nexerelin", enabled))
        self.assertFalse(_condition_held("with nexerelin", enabled))
        self.assertFalse(_condition_held("on mission start", enabled))
        self.assertFalse(_condition_held("unknown", enabled))


if __name__ == "__main__":
    unittest.main()
