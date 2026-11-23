"""94.G3 slice 2a: the allele denominator, `gene bank alleles` (docs/GENE_BANK_DESIGN.md). Synthetic fixtures only."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bridgeforge.genome.alleles import AllelesError, RootIndex, corpus_roots, plan, run_alleles_cli, zip_mod_infos
from tests.support import resolved_temp_dir, write_text as _write

PILOT = "hullmod:hm_a"
ANCHORS = [PILOT, "hull:ship_a", "weapon:gun_a", "wing:wing_a", "variant:ship_a_v", "faction:fac_a", "combat-plugin:plug_a",
           "custom-start:start_a", "star-system:Sys"]
NO_SYSTEMS = mock.patch("bridgeforge.genome.campaign.star_system_generators", return_value={})


def _info(ident: str, version: str, revived: bool) -> str:
    """A revival keeps the author's id and version; its mod_info.json differs only in what BridgeForge changed."""
    return json.dumps({"id": ident, "name": ident, "version": version, **({"gameVersion": "0.98a-RC8"} if revived else {})})


def _mod(root: Path, ident: str, version: str, *, hullmod: bool = True, revived: bool = False) -> Path:
    _write(root / "mod_info.json", _info(ident, version, revived))
    if hullmod:
        _write(root / "data/hullmods/hull_mods.csv", "name,id,tier\nA,hm_a,1\n")
    return root


def _full(root: Path, version: str = "1.0") -> Path:
    """A revived copy defining every anchor kind the bank holds."""
    _mod(root, "moda", version, revived=True)
    _write(root / "data/hulls/ship_data.csv", "name,id\nShip A,ship_a\n")
    _write(root / "data/hulls/ship_a.ship", json.dumps({"hullId": "ship_a"}))
    _write(root / "data/weapons/gun_a.wpn", json.dumps({"id": "gun_a"}))
    _write(root / "data/hulls/wing_data.csv", "id,variant\nwing_a,ship_a_v\n")
    _write(root / "data/variants/ship_a_v.variant", json.dumps({"variantId": "ship_a_v", "hullId": "ship_a"}))
    _write(root / "data/world/factions/fac_a.faction", json.dumps({"id": "fac_a"}))
    _write(root / "data/config/settings.json", json.dumps({"plugins": {"plug_a": "a.Plug", "blank": " "}}))
    # Two starts: describe refuses such a file, but the copy still defines the id (its refusal is recorded later).
    _write(root / "data/config/exerelin/customStarts.json", json.dumps({"starts": [{"id": "start_a"}, {"id": "start_b"}]}))
    return root


def _zip(path: Path, entries: dict[str, str | bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def _bank(root: Path, anchors=ANCHORS, sources=(PILOT,)) -> Path:
    """A bank holding one current record per anchor; only the fields the scan reads."""
    bank = root / "Genes"
    rids = []
    for number, anchor in enumerate(anchors):
        rid = f"{number:064x}"
        _write(bank / "records" / f"{rid}.json", json.dumps({"anchor": anchor}))
        rids.append(rid)
    lines = [{"path": "In operation/A/working", "folder": "working", "anchor": a, "build": "b"} for a in sources]
    _write(bank / "sources.json", json.dumps(lines))
    _write(bank / "entries.json", json.dumps([{**lines[0], "records": rids}]))
    return bank


def _archive(done: Path, name: str) -> Path:
    """archive.py's layout: ARCHIVE_NOTE.md, the revival as <Mod>/, original/, a reports-only workspace/."""
    folder = done / name
    _write(folder / "ARCHIVE_NOTE.md", "# note\n")
    _write(folder / "workspace" / "REVIVAL_REPORT.md", "# report\n")
    return folder


def _corpus(base: Path) -> Path:
    done = base / "Done"
    mod_a = _archive(done, "Mod-A")
    _full(mod_a / "Mod-A")
    _mod(mod_a / "original" / "extracted" / "Mod A-1.0", "moda", "1.0")
    _zip(mod_a / "original" / "Mod A-1.0.zip", {"Mod A/mod_info.json": _info("moda", "1.0", False)})
    _zip(mod_a / "original" / "Mod A-0.7.zip", {"Mod A/mod_info.json": _info("moda", "0.7", False)})
    _mod(mod_a / "alt-original-descriptions" / "Mod-A", "moda", "1.0", revived=True)  # BridgeForge's copy: skipped
    _zip(mod_a / "Mod-A-1.0.zip", {"Mod-A/mod_info.json": _info("moda", "1.0", True)})
    # Review 2026-11-23 (H2): the author's zip alone, same id and version as the revival, is not a packaged copy of it.
    mod_b = _archive(done, "Mod-B")
    _mod(mod_b / "Mod-B", "modb", "2.0", hullmod=False, revived=True)
    _zip(mod_b / "original" / "Mod B-2.0.zip", {"Mod B/mod_info.json": _info("modb", "2.0", False)})
    _mod(_archive(done / "_replaced-2026-11-01", "Mod-A") / "Mod-A", "moda", "0.8", revived=True)
    legacy = done / "Mod-A-old" / "workspace"  # an older archive that kept a whole workspace
    _mod(legacy / "working", "moda", "0.9", revived=True)
    _mod(legacy / "original" / "extracted" / "Mod A-0.6", "moda", "0.6")
    _mod(legacy / "genes" / "p1" / "work" / "carrier", "bf_gene_carrier", "1")  # a proof carrier: skipped
    _mod(legacy / "scratch" / "copy", "moda", "0.9")
    _zip(done / "Other.zip", {"Other/mod_info.json": _info("other", "2", False)})
    _zip(done / "Nothing.zip", {"readme.txt": "no mod"})
    _write(done / "Old.7z", "7z")
    mentioner = _mod(done / "Mentioner", "mentioner", "3", hullmod=False)
    _write(mentioner / "data/variants/m.variant", json.dumps({"variantId": "m", "hullId": "ship_a", "hullMods": ["hm_a"]}))
    _write(mentioner / "data/strings/notes.txt", "wing_ab is another id; xwing_a too")  # not whole words: wing_a not named
    # In a class, the byte before a constant is its length: here "a", a word character (review 2026-11-23).
    _zip(mentioner / "jars" / "m.jar", {"m/Big.class": b"\xca\xfe" * 40, "m/C.class": b"\xca\xfe\xba\xbe\x00agun_a\x00"})
    return done


EXPECTED_ROOTS = {
    ("Mod-A/Mod-A", "archive"), ("Mod-A/original/extracted/Mod A-1.0", "original"), ("Mod-B/Mod-B", "archive"),
    ("_replaced-2026-11-01/Mod-A/Mod-A", "archive"), ("Mod-A-old/workspace/working", "archive"),
    ("Mod-A-old/workspace/original/extracted/Mod A-0.6", "original"), ("Mentioner", "original"),
}


class CorpusRootsTests(unittest.TestCase):
    def test_roots_follow_archive_s_layout_and_bridgeforge_s_own_copies_are_listed_as_skipped(self) -> None:
        with resolved_temp_dir() as root:
            done = _corpus(root)
            roots, zips, unread, skipped = corpus_roots(done)
            found = {(p.relative_to(done).as_posix(), kind) for p, kind in roots}
            skipped_paths = sorted(p.relative_to(done).as_posix() for p, _ in skipped)
            zip_paths = sorted(p.relative_to(done).as_posix() for p in zips)
        self.assertEqual(found, EXPECTED_ROOTS)
        self.assertEqual(skipped_paths, ["Mod-A-old/workspace/genes/p1/work/carrier", "Mod-A-old/workspace/scratch/copy",
                                         "Mod-A/alt-original-descriptions/Mod-A"])
        self.assertEqual(zip_paths, ["Mod-A/Mod-A-1.0.zip", "Mod-A/original/Mod A-0.7.zip", "Mod-A/original/Mod A-1.0.zip",
                                     "Mod-B/original/Mod B-2.0.zip", "Nothing.zip", "Other.zip"])
        self.assertEqual([p.name for p in unread], ["Old.7z"])

    def test_a_working_copy_outside_done_is_working_and_excluded_folders_links_and_bare_working_are_handled(self) -> None:
        from tests.support import link_dir

        with resolved_temp_dir() as root:
            ops = root / "In operation"
            _mod(ops / "A" / "working", "moda", "1.0")
            (ops / "Bare" / "working").mkdir(parents=True)  # a workspace whose working/ has no mod_info.json
            _mod(ops / "_rig-x" / "mods" / "A", "moda", "1.0")
            _mod(root / "core-like" / "inner", "linked", "1")
            (ops / "B").mkdir()
            link_dir(root / "core-like", ops / "B" / "starsector-core")  # a rig links its core: never walked
            roots, _, _, skipped = corpus_roots(ops, ("_rig-*",))
        self.assertEqual([(p.relative_to(ops).as_posix(), kind) for p, kind in roots], [("A/working", "working")])
        self.assertEqual([(p.relative_to(ops).as_posix(), why) for p, why in skipped],
                         [("Bare/working", "a workspace's working/ with no mod_info.json")])

    def test_a_zip_s_mod_infos_are_read_two_folders_down_at_most(self) -> None:
        with resolved_temp_dir() as root:
            _zip(root / "x.zip", {"a/b/mod_info.json": '{"id": "x", "version": {"major": 1, "minor": 2, "patch": 0}}',
                                  "a/b/c/d/mod_info.json": '{"id": "deep"}'})
            infos = zip_mod_infos(root / "x.zip")
        self.assertEqual([(i["id"], i["version"]) for i in infos], [("x", "1.2.0")])


class RootIndexTests(unittest.TestCase):
    def test_every_kind_is_found_by_the_describer_s_own_tables(self) -> None:
        with resolved_temp_dir() as root, mock.patch("bridgeforge.genome.campaign.star_system_generators",
                                                     return_value={"Sys": ["a.Gen"], None: ["a.Comp"]}):
            index = RootIndex(_full(root / "m"), {a.partition(":")[0] for a in ANCHORS})
            found = [a for a in ANCHORS if index.defines(a)]
            absent = [a for a in ("hull:other", "combat-plugin:blank", "custom-start:start_c", "star-system:None") if index.defines(a)]
        self.assertEqual((found, absent), (ANCHORS, []))


class PlanTests(unittest.TestCase):
    def _plan(self, root: Path, **kwargs) -> dict:
        done = _corpus(root)
        bank = _bank(root)
        with NO_SYSTEMS, mock.patch("bridgeforge.zipsafe.MAX_CLASS_BYTES", 64):
            return plan(done, bank=bank, quiet=True, base=root, **kwargs)

    def test_the_plan_lists_definitions_mentions_zips_skipped_copies_and_what_could_not_be_read(self) -> None:
        with resolved_temp_dir() as root:
            result = self._plan(root)
        rows = {r["path"]: r for r in result["roots"]}
        self.assertEqual(result["pilot_anchors"], [PILOT])
        working = rows["Done/Mod-A/Mod-A"]
        self.assertEqual(sorted(working["defines"]), sorted(a for a in ANCHORS if a != "star-system:Sys"))
        self.assertEqual((working["mod_id"], working["mod_version"], working["folder"], working["mentions"]),
                         ("moda", "1.0", "archive", []))  # a defined id is not also a mention
        self.assertEqual(rows["Done/Mod-A/original/extracted/Mod A-1.0"]["defines"], [PILOT])
        mentioner = rows["Done/Mentioner"]
        self.assertEqual((mentioner["defines"], sorted(mentioner["mentions"])),
                         ([], sorted(["hullmod:hm_a", "hull:ship_a", "weapon:gun_a"])))
        self.assertEqual(mentioner["unreadable"], ["jars/m.jar!m/Big.class (ZipEntryTooLarge)"])  # and C.class still read
        self.assertEqual({z["path"].removeprefix("Done/"): z["state"] for z in result["zips"]}, {
            "Mod-A/Mod-A-1.0.zip": "packaged copy of a scanned copy",
            "Mod-A/original/Mod A-1.0.zip": "packaged copy of a scanned copy",
            "Mod-A/original/Mod A-0.7.zip": "archive only, not described",
            "Mod-B/original/Mod B-2.0.zip": "archive only, not described",
            "Other.zip": "archive only, not described", "Nothing.zip": "no mod"})
        self.assertEqual(result["unread_archives"], ["Done/Old.7z"])
        self.assertEqual(len(result["skipped"]), 3)
        pilot = result["summary"]["anchors"][PILOT]
        # Five copies, four releases: 1.0 is both the archived revival and the author's original.
        self.assertEqual((pilot["roots"], pilot["mod_versions"], pilot["mod_ids"], pilot["mention_only"]), (5, 4, 1, 1))
        self.assertEqual((result["summary"]["errors"], result["summary"]["roots_defining_a_pilot"]), (0, 5))

    def test_an_error_in_one_root_or_one_zip_is_recorded_and_the_walk_goes_on(self) -> None:
        from bridgeforge.genome import alleles

        real_index, real_zip = alleles.RootIndex, alleles.zip_mod_infos

        def failing(root, kinds):
            if root.name == "Mentioner":
                raise KeyError("boom")
            return real_index(root, kinds)

        def deflate64(path):
            if path.name == "Other.zip":
                raise NotImplementedError("That compression method is not supported")
            return real_zip(path)

        with resolved_temp_dir() as root, mock.patch.object(alleles, "RootIndex", failing), \
                mock.patch.object(alleles, "zip_mod_infos", deflate64):
            result = self._plan(root)
            args = SimpleNamespace(corpus=root / "Done", out=root / "plan.json", bank=root / "Genes", exclude=None, quiet=True)
            with NO_SYSTEMS, mock.patch("bridgeforge.paths.data_root", return_value=root), contextlib.redirect_stdout(io.StringIO()):
                code = run_alleles_cli(args)
        rows = {r["path"]: r for r in result["roots"]}
        self.assertEqual(rows["Done/Mentioner"]["error"], "defines: KeyError: 'boom'")
        self.assertEqual(sorted(rows["Done/Mentioner"]["mentions"]), sorted(["hullmod:hm_a", "hull:ship_a", "weapon:gun_a"]))
        zips = {z["path"]: z["state"] for z in result["zips"]}
        self.assertEqual(zips["Done/Other.zip"], "unreadable (NotImplementedError)")
        self.assertEqual((result["summary"]["errors"], result["summary"]["roots"], code), (1, 7, 1))  # an error fails the run

    def test_a_corpus_outside_the_data_root_an_empty_bank_a_bad_record_and_an_unknown_kind_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            done = _corpus(root / "data")
            with self.assertRaisesRegex(AllelesError, "not under the data root"):
                plan(done, bank=_bank(root / "data"), quiet=True, base=root / "elsewhere")
            empty = root / "empty"
            _write(empty / "sources.json", "[]")
            with self.assertRaisesRegex(AllelesError, "holds no sources"):
                plan(done, bank=empty, quiet=True, base=root / "data")
            bad = _bank(root / "bad")
            _write(bad / "records" / f"{0:064x}.json", json.dumps({"kind": "hullmod"}))
            with self.assertRaisesRegex(AllelesError, "a current record with no anchor"):
                plan(done, bank=bad, quiet=True, base=root / "data")
            with self.assertRaisesRegex(AllelesError, "no corpus test for anchor kind\\(s\\) market"):
                plan(done, bank=_bank(root / "odd", anchors=[PILOT, "market:m"]), quiet=True, base=root / "data")


class ResumeTests(unittest.TestCase):
    def test_the_cli_resumes_from_its_checkpoint_and_removes_it(self) -> None:
        from bridgeforge.genome import alleles

        with resolved_temp_dir() as root, NO_SYSTEMS, mock.patch("bridgeforge.paths.data_root", return_value=root):
            done, bank = _corpus(root), _bank(root)
            out = root / "plans" / "alleles.json"
            args = SimpleNamespace(corpus=done, out=out, bank=bank, exclude=None, quiet=True)
            scanned = []
            real = alleles.scan_root

            def counting(path, anchors, patterns):
                scanned.append(path.name)
                if len(scanned) == 2 and not out.exists():
                    raise KeyboardInterrupt  # an interrupted first run
                return real(path, anchors, patterns)

            with mock.patch.object(alleles, "scan_root", counting):
                with self.assertRaises(KeyboardInterrupt):
                    run_alleles_cli(args)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = run_alleles_cli(args)
            written = json.loads(out.read_text(encoding="utf-8"))
            left = out.with_name(out.name + ".partial.jsonl").exists()
        self.assertEqual((code, left, len(written["roots"])), (0, False, 7))
        self.assertEqual(len(scanned), 2 + 6)  # the first root came from the checkpoint
        self.assertIn(f"{PILOT}: 5 root(s), 4 mod version(s), 1 mention only", stdout.getvalue())

    def test_new_anchors_restart_and_a_copy_changed_in_place_is_scanned_again(self) -> None:
        # Review 2026-11-23 (H1): a longer anchor list read as "grown" and reused rows scanned without the new anchor.
        from bridgeforge.genome import alleles

        with resolved_temp_dir() as root, NO_SYSTEMS:
            done = _corpus(root)
            checkpoint = root / "plan.partial.jsonl"
            _write(done / "Mod-A" / "Mod-A" / "data/weapons/gun_new.wpn", json.dumps({"id": "gun_new"}))
            plan(done, bank=_bank(root), quiet=True, base=root, checkpoint_path=checkpoint)
            grown = plan(done, bank=_bank(root / "b2", anchors=[*ANCHORS, "weapon:gun_new"]), quiet=True, base=root,
                         checkpoint_path=checkpoint)
            refreshed = done / "_replaced-2026-11-01" / "Mod-A" / "Mod-A"
            _write(refreshed / "mod_info.json", _info("moda", "0.8+bf.2", True))
            scanned = []
            real = alleles.scan_root
            with mock.patch.object(alleles, "scan_root", lambda r, a, p: scanned.append(r) or real(r, a, p)):
                plan(done, bank=_bank(root / "b2", anchors=[*ANCHORS, "weapon:gun_new"]), quiet=True, base=root,
                     checkpoint_path=checkpoint)
        rows = {r["path"]: r for r in grown["roots"]}
        self.assertIn("weapon:gun_new", rows["Done/Mod-A/Mod-A"]["defines"])
        self.assertEqual(scanned, [refreshed])

    def test_a_root_that_failed_is_scanned_again_on_resume(self) -> None:
        from bridgeforge.genome import alleles

        real = alleles.RootIndex

        def failing(root, kinds):
            if root.name == "Mentioner":
                raise KeyError("boom")
            return real(root, kinds)

        with resolved_temp_dir() as root, NO_SYSTEMS:
            done, bank, checkpoint = _corpus(root), _bank(root), root / "plan.partial.jsonl"
            with mock.patch.object(alleles, "RootIndex", failing):
                first = plan(done, bank=bank, quiet=True, base=root, checkpoint_path=checkpoint)
            again = plan(done, bank=bank, quiet=True, base=root, checkpoint_path=checkpoint)
        self.assertEqual((first["summary"]["errors"], again["summary"]["errors"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
