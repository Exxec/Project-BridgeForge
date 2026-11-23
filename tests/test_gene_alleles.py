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


def _mod(root: Path, ident: str, version: str, *, hullmod: bool = True) -> Path:
    _write(root / "mod_info.json", json.dumps({"id": ident, "name": ident, "version": version}))
    if hullmod:
        _write(root / "data/hullmods/hull_mods.csv", "name,id,tier\nA,hm_a,1\n")
    return root


def _full(root: Path) -> Path:
    """A copy defining every anchor kind the bank holds."""
    _mod(root, "moda", "1.0")
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


def _corpus(base: Path) -> Path:
    done = base / "Done"
    workspace = done / "Mod-A" / "workspace"
    _full(workspace / "working")
    _mod(workspace / "original" / "extracted" / "Mod A-0.9", "moda", "0.9")
    _mod(workspace / "genes" / "p1" / "work" / "carrier", "bf_gene_carrier", "1")  # a proof carrier: not an allele
    _mod(workspace / "scratch" / "copy", "moda", "1.0")
    _mod(done / "Mod-A" / "original" / "Mod A-1.0", "moda", "1.0")
    _mod(done / "_replaced-2026-11-01" / "Mod-A" / "workspace" / "working", "moda", "0.8")
    with zipfile.ZipFile(done / "Mod-A" / "Mod-A-1.0.zip", "w") as archive:
        archive.writestr("Mod A/mod_info.json", json.dumps({"id": "moda", "version": "1.0"}))
    with zipfile.ZipFile(done / "Other.zip", "w") as archive:
        archive.writestr("Other/mod_info.json", json.dumps({"id": "other", "version": "2"}))
    with zipfile.ZipFile(done / "Nothing.zip", "w") as archive:
        archive.writestr("readme.txt", "no mod")
    _write(done / "Old.7z", "7z")
    mentioner = _mod(done / "Mentioner", "mentioner", "3", hullmod=False)
    _write(mentioner / "data/variants/m.variant", json.dumps({"variantId": "m", "hullId": "ship_a", "hullMods": ["hm_a"]}))
    _write(mentioner / "data/strings/notes.txt", "wing_ab is another id; xwing_a too")  # not whole words: wing_a not named
    (mentioner / "jars").mkdir()
    with zipfile.ZipFile(mentioner / "jars" / "m.jar", "w") as jar:
        jar.writestr("m/C.class", b"\xca\xfe\xba\xbe\x00\x08gun_a\x00")
    return done


class CorpusRootsTests(unittest.TestCase):
    def test_roots_are_working_original_and_archive_copies_never_bridgeforge_s_own(self) -> None:
        with resolved_temp_dir() as root:
            done = _corpus(root)
            roots, zips, unread = corpus_roots(done)
            found = {(p.relative_to(done).as_posix(), kind) for p, kind in roots}
        self.assertEqual(found, {
            ("Mod-A/workspace/working", "archive"),
            ("Mod-A/workspace/original/extracted/Mod A-0.9", "original"),
            ("Mod-A/original/Mod A-1.0", "original"),
            ("_replaced-2026-11-01/Mod-A/workspace/working", "archive"),
            ("Mentioner", "original"),
        })
        self.assertEqual(sorted(p.name for p in zips), ["Mod-A-1.0.zip", "Nothing.zip", "Other.zip"])
        self.assertEqual([p.name for p in unread], ["Old.7z"])

    def test_a_working_copy_outside_done_is_working_and_excluded_folders_and_links_are_skipped(self) -> None:
        from tests.support import link_dir

        with resolved_temp_dir() as root:
            ops = root / "In operation"
            _mod(ops / "A" / "working", "moda", "1.0")
            _mod(ops / "_rig-x" / "mods" / "A", "moda", "1.0")
            _mod(root / "core-like" / "inner", "linked", "1")
            (ops / "B").mkdir()
            link_dir(root / "core-like", ops / "B" / "starsector-core")  # a rig links its core: never walked
            roots, _, _ = corpus_roots(ops, ("_rig-*",))
        self.assertEqual([(p.relative_to(ops).as_posix(), kind) for p, kind in roots], [("A/working", "working")])

    def test_a_zip_s_mod_infos_are_read_two_folders_down_at_most(self) -> None:
        with resolved_temp_dir() as root:
            with zipfile.ZipFile(root / "x.zip", "w") as archive:
                archive.writestr("a/b/mod_info.json", '{"id": "x", "version": {"major": 1, "minor": 2, "patch": 0}}')
                archive.writestr("a/b/c/d/mod_info.json", '{"id": "deep"}')
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
        with mock.patch("bridgeforge.genome.campaign.star_system_generators", return_value={}):
            return plan(done, bank=bank, quiet=True, base=root, **kwargs)

    def test_the_plan_lists_definitions_mentions_zips_and_what_could_not_be_read(self) -> None:
        with resolved_temp_dir() as root:
            result = self._plan(root)
        rows = {r["path"]: r for r in result["roots"]}
        self.assertEqual(result["pilot_anchors"], [PILOT])
        working = rows["Done/Mod-A/workspace/working"]
        self.assertEqual(sorted(working["defines"]), sorted(a for a in ANCHORS if a != "star-system:Sys"))
        self.assertEqual((working["mod_id"], working["mod_version"], working["folder"], working["mentions"]),
                         ("moda", "1.0", "archive", []))  # a defined id is not also a mention
        self.assertEqual(rows["Done/Mod-A/original/Mod A-1.0"]["defines"], [PILOT])
        self.assertEqual((rows["Done/Mentioner"]["defines"], sorted(rows["Done/Mentioner"]["mentions"])),
                         ([], sorted(["hullmod:hm_a", "hull:ship_a", "weapon:gun_a"])))
        self.assertEqual({z["path"].rsplit("/", 1)[-1]: z["state"] for z in result["zips"]},
                         {"Mod-A-1.0.zip": "packaged copy of a folder row", "Other.zip": "archive only, not described",
                          "Nothing.zip": "no mod"})
        self.assertEqual(result["unread_archives"], ["Done/Old.7z"])
        pilot = result["summary"]["anchors"][PILOT]
        # Four copies, three releases: 1.0 is both the archived working copy and the author's original.
        self.assertEqual((pilot["roots"], pilot["mod_versions"], pilot["mod_ids"], pilot["mention_only"]), (4, 3, 1, 1))
        self.assertEqual((result["summary"]["errors"], result["summary"]["roots_defining_a_pilot"]), (0, 4))

    def test_an_error_in_one_root_is_recorded_and_the_walk_goes_on(self) -> None:
        from bridgeforge.genome import alleles

        real = alleles.RootIndex

        def failing(root, kinds):
            if root.name == "Mentioner":
                raise KeyError("boom")
            return real(root, kinds)

        with resolved_temp_dir() as root, mock.patch.object(alleles, "RootIndex", failing):
            result = self._plan(root)
            args = SimpleNamespace(corpus=root / "Done", out=root / "plan.json", bank=root / "Genes", exclude=None, quiet=True)
            with mock.patch("bridgeforge.genome.campaign.star_system_generators", return_value={}), \
                    mock.patch("bridgeforge.paths.data_root", return_value=root), contextlib.redirect_stdout(io.StringIO()):
                code = run_alleles_cli(args)
        errors = {r["path"]: r["error"] for r in result["roots"] if r["error"]}
        self.assertEqual(errors, {"Done/Mentioner": "KeyError: 'boom'"})
        self.assertEqual((result["summary"]["errors"], result["summary"]["roots"], code), (1, 5, 1))  # an error fails the run

    def test_a_corpus_outside_the_data_root_an_empty_bank_and_an_unknown_kind_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            done = _corpus(root / "data")
            with self.assertRaisesRegex(AllelesError, "not under the data root"):
                plan(done, bank=_bank(root / "data"), quiet=True, base=root / "elsewhere")
            empty = root / "empty"
            _write(empty / "sources.json", "[]")
            with self.assertRaisesRegex(AllelesError, "holds no sources"):
                plan(done, bank=empty, quiet=True, base=root / "data")
            with self.assertRaisesRegex(AllelesError, "no corpus test for anchor kind\\(s\\) market"):
                plan(done, bank=_bank(root / "odd", anchors=[PILOT, "market:m"]), quiet=True, base=root / "data")

    def test_the_cli_writes_the_plan_resumes_from_its_checkpoint_and_removes_it(self) -> None:
        from bridgeforge.genome import alleles

        with resolved_temp_dir() as root, mock.patch("bridgeforge.genome.campaign.star_system_generators", return_value={}), \
                mock.patch("bridgeforge.paths.data_root", return_value=root):
            done, bank = _corpus(root), _bank(root)
            out = root / "plans" / "alleles.json"
            args = SimpleNamespace(corpus=done, out=out, bank=bank, exclude=None, quiet=True)
            scanned = []
            real = alleles.scan_root

            def counting(path, anchors, pattern):
                scanned.append(path.name)
                if len(scanned) == 2 and not out.exists():
                    raise KeyboardInterrupt  # an interrupted first run
                return real(path, anchors, pattern)

            with mock.patch.object(alleles, "scan_root", counting):
                with self.assertRaises(KeyboardInterrupt):
                    run_alleles_cli(args)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = run_alleles_cli(args)
            written = json.loads(out.read_text(encoding="utf-8"))
            left = out.with_name(out.name + ".partial.jsonl").exists()
        self.assertEqual((code, left, len(written["roots"])), (0, False, 5))
        self.assertEqual(len(scanned), 2 + 4)  # the first root came from the checkpoint
        self.assertIn(f"{PILOT}: 4 root(s), 3 mod version(s), 1 mention only", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
