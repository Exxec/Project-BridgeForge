"""94.G2 slice 11: a gene set's carrier and its static isolation proof."""
from __future__ import annotations

import hashlib
import io
import json
import unittest
import zipfile
from contextlib import redirect_stderr
from unittest import mock

from bridgeforge.genome import gene_set
from bridgeforge.genome.evidence import check
from bridgeforge.genome.gene import GeneError
from bridgeforge.genome.proof import ProofError, build_carrier, cut_csv_row
from tests.support import resolved_temp_dir, write_text as _write
from tests.test_vendor_plan import _rebal, _vanilla

FACTION = {"id": "rebal_faction", "knownShips": {"tags": [], "hulls": ["lasher"]},
           "knownWeapons": {"tags": [], "weapons": ["rebal_rail"]}, "knownHullMods": {"tags": [], "hullMods": ["shields_formshield"]}}


def _gene(anchor: str, members: list[tuple[str, str]], *, needs: list[str] = (), vanilla: list[str] = (), suspects: list[dict] = (),
          registrations: list[dict] = (), kind: str | None = None) -> dict:
    return {"identity": hashlib.sha256(anchor.encode("utf-8")).hexdigest(), "kind": kind or anchor.split(":", 1)[0],
            "anchors": [anchor], "provides": [anchor],
            "members": [{"what": "csv-row" if " [" in p else "json-entry" if "#" in p else "jar-class" if "!" in p else "file",
                         "path": p, "sha256": s} for p, s in members],
            "needs": {"vanilla": list(vanilla), "mods": [], "genes": list(needs)}, "registrations": list(registrations),
            "unknowns": {"missing": [], "suspects": list(suspects)}}


def _with_faction(root):
    ws = _rebal(root)
    _write(ws / "working" / "data" / "world" / "factions" / "rebal.faction", json.dumps(FACTION))
    _write(ws / "working" / "data" / "world" / "factions" / "factions.csv", "faction\ndata/world/factions/rebal.faction\n")
    return ws


class GeneSetPieceTests(unittest.TestCase):
    def test_a_shared_path_is_written_once_and_another_hash_is_a_conflict(self) -> None:
        genes = {"a:x": _gene("a:x", [("shared.png", "1" * 64), ("a.png", "2" * 64)]),
                 "b:y": _gene("b:y", [("shared.png", "1" * 64)]), "c:z": _gene("c:z", [("a.png", "3" * 64)])}
        merged, conflicts = gene_set.merge_members(genes)
        self.assertEqual([m["path"] for m in merged], ["a.png", "shared.png"])
        self.assertEqual(conflicts, [{"path": "a.png", "genes": ["a:x", "c:z"]}])

    def test_a_file_held_whole_by_one_gene_and_in_part_by_another_is_a_conflict(self) -> None:
        genes = {"a:x": _gene("a:x", [("data/config/settings.json", "1" * 64), ("jars/x.jar", "4" * 64)]),
                 "b:y": _gene("b:y", [("data/config/settings.json#/key", "2" * 64), ("data/hullmods/hull_mods.csv [m]", "3" * 64),
                                      ("jars/x.jar!a/B.class", "5" * 64)])}
        _merged, conflicts = gene_set.merge_members(genes)
        self.assertEqual(conflicts, [{"path": "jars/x.jar!a/B.class", "genes": ["a:x", "b:y"]},  # the csv row's table is not held whole
                                     {"path": "data/config/settings.json#/key", "genes": ["a:x", "b:y"]}])

    def test_several_genes_write_one_table_one_settings_file_and_one_jar_once_each(self) -> None:
        genes = {"a:x": _gene("a:x", [("data/hullmods/hull_mods.csv [ma]", "1" * 64), ("data/config/settings.json#/ka", "2" * 64),
                                      ("jars/x.jar!a/A.class", "3" * 64), ("jars/x.jar!c/Shared.class", "9" * 64)]),
                 "b:y": _gene("b:y", [("data/hullmods/hull_mods.csv [mb]", "4" * 64), ("data/config/settings.json#/kb", "5" * 64),
                                      ("jars/x.jar!b/B.class", "6" * 64), ("jars/x.jar!c/Shared.class", "9" * 64)])}
        merged, conflicts = gene_set.merge_members(genes)
        self.assertEqual(conflicts, [])
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "m", "name": "M", "gameVersion": "0.98.5a-RC7"}))
            _write(mod / "data/hullmods/hull_mods.csv", "name,id\nA,ma\nOther,mo\nB,mb\n")
            _write(mod / "data/config/settings.json", json.dumps({"ka": 1, "kb": {"x": 2}, "kc": 3}))
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars/x.jar", "w") as jar:
                for entry in ("a/A.class", "b/B.class", "c/Shared.class", "d/Other.class"):
                    jar.writestr(entry, entry)
            carrier = root / "carrier"
            build_carrier(mod, {"identity": "0" * 64, "anchors": ["a:x and the 1 genes it needs"], "members": merged,
                                "needs": {"mods": []}, "kind": "set", "registrations": []}, carrier)
            table = (carrier / "data/hullmods/hull_mods.csv").read_text(encoding="utf-8")
            settings = json.loads((carrier / "data/config/settings.json").read_text(encoding="utf-8"))
            with zipfile.ZipFile(carrier / "jars/x.jar") as jar:
                entries = [info.filename for info in jar.infolist()]
            info = json.loads((carrier / "mod_info.json").read_text(encoding="utf-8"))
        self.assertEqual(table, "name,id\nA,ma\nB,mb\n")
        self.assertEqual(settings, {"ka": 1, "kb": {"x": 2}})
        self.assertEqual(sorted(entries), ["a/A.class", "b/B.class", "c/Shared.class"])  # the shared class once
        self.assertEqual(info["jars"], ["jars/x.jar"])

    def test_the_anchor_comes_first_even_when_it_sorts_last(self) -> None:
        genes = {"weapon:z": {}, "faction:a": {}, "hull:m": {}}
        self.assertEqual(gene_set.carried_order("weapon:z", genes), ["weapon:z", "faction:a", "hull:m"])

    def test_the_set_identity_ignores_order_and_follows_every_member_gene(self) -> None:
        a, b = _gene("a:x", [("f", "1" * 64)]), _gene("b:y", [("g", "2" * 64)])
        self.assertEqual(gene_set.set_identity({"a:x": a, "b:y": b}), gene_set.set_identity({"b:y": b, "a:x": a}))
        self.assertNotEqual(gene_set.set_identity({"a:x": a, "b:y": b}), gene_set.set_identity({"a:x": a}))

    def test_only_the_star_system_registration_is_made(self) -> None:
        genes = {"star-system:S": _gene("star-system:S", [], registrations=[{"locus": "P.onNewGame", "statement": "Gen: generate"}]),
                 "faction:f": _gene("faction:f", [], registrations=[{"locus": "P.setUp", "statement": 'getFaction("f")'}])}
        self.assertEqual(gene_set.registrations_not_made(genes, "star-system:S"),
                         [{"gene": "faction:f", "locus": "P.setUp", "statement": 'getFaction("f")'}])

    def test_suspects_are_bucketed_by_file_and_ids_nobody_supplies_are_not_carried(self) -> None:
        genes = {"faction:f": _gene("faction:f", [], needs=["hull:h"], vanilla=["hull:wolf"], suspects=[
                    {"path": "f.faction#/music", "mentions": ["music_own", "h"], "reason": "r"},
                    {"path": "jars/x.jar!a/B.class", "mentions": ["wolf"], "reason": "r"}]),
                 "hull:h": _gene("hull:h", [])}
        buckets, absent = gene_set.suspect_buckets(genes)
        self.assertEqual(sorted(buckets), ["f.faction", "jars/x.jar"])
        self.assertEqual(buckets["f.faction"][0]["gene"], "faction:f")
        self.assertEqual(absent, [{"file": "f.faction", "id": "music_own"}])  # h is carried, wolf is the core's

    def test_a_factions_csv_row_is_cut_by_its_faction_column(self) -> None:
        text = "faction\ndata/world/factions/a.faction\ndata/world/factions/b.faction\n"
        rest, row = cut_csv_row(text, "data/world/factions/b.faction", "faction")
        self.assertEqual((rest, row), ("faction\ndata/world/factions/a.faction\n", "data/world/factions/b.faction\n"))
        with self.assertRaisesRegex(ProofError, "no id column"):
            cut_csv_row(text, "data/world/factions/b.faction")


class CarrierResolutionTests(unittest.TestCase):
    def test_each_kind_resolves_only_when_the_carrier_defines_it(self) -> None:
        resolved = ["faction:listed", "combat-plugin:loose", "industry:own_industry", "hull:own_hull", "hull:skin_hull",
                    "variant:own_v", "weapon:own_gun", "wing:own_wing", "hullmod:own_mod", "shipsystem:own_system",
                    "condition:own_cond", "planet-type:own_planet"]
        anchors = [*resolved, "faction:unlisted", "faction:absent", "combat-plugin:classless", "combat-plugin:unregistered",
                   "industry:gone_industry", "hull:gone_hull", "planet-type:gone_planet", "star-system:Nowhere", "market:somewhere"]
        genes = {"set:all": _gene("set:all", [], needs=anchors)}
        with resolved_temp_dir() as root:
            carrier = root / "carrier"
            _write(carrier / "mod_info.json", json.dumps({"id": "c", "name": "C"}))
            for ident in ("listed", "unlisted"):
                _write(carrier / "data/world/factions" / f"{ident}.faction", json.dumps({"id": ident}))
            _write(carrier / "data/world/factions/factions.csv", "faction\ndata/world/factions/listed.faction\n")
            _write(carrier / "data/config/settings.json", json.dumps({"plugins": {"loose": "data.scripts.Loose",
                                                                                 "classless": "data.scripts.Gone"}}))
            _write(carrier / "data/scripts/Loose.java", "package data.scripts;\npublic class Loose {}\n")
            _write(carrier / "data/campaign/industries.csv", "id,name\nown_industry,Own\n")
            _write(carrier / "data/hulls/ship_data.csv", "name,id\nOwn,own_hull\n")
            _write(carrier / "data/hulls/own.skin", json.dumps({"skinHullId": "skin_hull", "baseHullId": "own_hull"}))
            _write(carrier / "data/variants/own.variant", json.dumps({"variantId": "own_v", "hullId": "own_hull"}))
            _write(carrier / "data/weapons/own.wpn", json.dumps({"id": "own_gun"}))
            _write(carrier / "data/hulls/wing_data.csv", "id,variant\nown_wing,own_v\n")
            _write(carrier / "data/hullmods/hull_mods.csv", "name,id\nOwn,own_mod\n")
            _write(carrier / "data/shipsystems/ship_systems.csv", "name,id\nOwn,own_system\n")
            _write(carrier / "data/campaign/market_conditions.csv", "id,name\nown_cond,Own\n")
            _write(carrier / "data/config/planets.json", json.dumps({"own_planet": {"name": "Own"}}))
            unresolved = {u["anchor"]: u["why"] for u in gene_set.unresolved_in_carrier(carrier, genes)}
        self.assertFalse(set(resolved) & set(unresolved), unresolved)
        self.assertEqual(sorted(unresolved), ["combat-plugin:classless", "combat-plugin:unregistered", "faction:absent",
                                              "faction:unlisted", "hull:gone_hull", "industry:gone_industry", "market:somewhere",
                                              "planet-type:gone_planet", "set:all", "star-system:Nowhere"])
        self.assertIn("does not list data/world/factions/unlisted.faction", unresolved["faction:unlisted"])
        self.assertIn("no .faction file", unresolved["faction:absent"])
        self.assertIn("holds no class data.scripts.Gone", unresolved["combat-plugin:classless"])
        self.assertIn("createStarSystem", unresolved["star-system:Nowhere"])
        self.assertIn("is not checked", unresolved["market:somewhere"])


class GeneSetWalkTests(unittest.TestCase):
    MANIFESTS = {"star-system:S": _gene("star-system:S", [], needs=["faction:f"]),
                 "faction:f": _gene("faction:f", [], needs=["hull:h", "hull:gone"]),
                 "hull:h": _gene("hull:h", [], needs=["faction:f"])}

    def _describe(self, _mod, anchor, vanilla_core=None):
        if anchor not in self.MANIFESTS:
            raise GeneError(f"{anchor} is not defined")
        return self.MANIFESTS[anchor]

    def test_every_needed_gene_is_described_once_and_a_refusal_is_kept(self) -> None:
        with resolved_temp_dir() as root, mock.patch.object(gene_set, "describe", side_effect=self._describe) as describe, \
                redirect_stderr(io.StringIO()) as err:
            genes, refused = gene_set.walk(root, "star-system:S", root, checkpoint_path=root / "walk.partial.jsonl")
        self.assertEqual(sorted(genes), ["faction:f", "hull:h", "star-system:S"])
        self.assertEqual(refused, {"hull:gone": "hull:gone is not defined"})
        self.assertEqual(describe.call_count, 4)  # the cycle back to faction:f is not described again
        self.assertIn("[4/4] hull:gone: refused", err.getvalue())

    def test_an_interrupted_walk_resumes_from_its_checkpoint(self) -> None:
        with resolved_temp_dir() as root, redirect_stderr(io.StringIO()):
            mod, core, checkpoint = root / "mod", root / "core", root / "walk.partial.jsonl"
            _write(mod / "data" / "a.csv", "id\na\n")
            _write(core / "data" / "b.csv", "id\nb\n")
            with mock.patch.object(gene_set, "describe", side_effect=self._describe):
                first = gene_set.walk(mod, "star-system:S", core, checkpoint_path=checkpoint)
            with mock.patch.object(gene_set, "describe", side_effect=AssertionError("described again")):
                second = gene_set.walk(mod, "star-system:S", core, checkpoint_path=checkpoint)
        self.assertEqual(first, second)

    def test_a_checkpoint_inside_the_workspace_still_resumes(self) -> None:
        # P3's proofs go to <workspace>/genes/, beside working/: only working/ is fingerprinted, not the growing checkpoint.
        with resolved_temp_dir() as root, redirect_stderr(io.StringIO()):
            ws, core = root / "Demo-Workspace", root / "core"
            _write(ws / "working" / "mod_info.json", json.dumps({"id": "demo", "name": "Demo"}))
            _write(core / "data" / "b.csv", "id\nb\n")
            checkpoint = ws / "genes" / "p3-set.closure.partial.jsonl"
            with mock.patch.object(gene_set, "describe", side_effect=self._describe):
                first = gene_set.walk(ws, "star-system:S", core, checkpoint_path=checkpoint)
            with mock.patch.object(gene_set, "describe", side_effect=AssertionError("described again")):
                second = gene_set.walk(ws, "star-system:S", core, checkpoint_path=checkpoint)
        self.assertEqual(first, second)

    def test_a_checkpoint_made_before_the_mod_or_the_core_changed_is_not_resumed(self) -> None:
        with resolved_temp_dir() as root, redirect_stderr(io.StringIO()):
            mod, core, checkpoint = root / "mod", root / "core", root / "walk.partial.jsonl"
            _write(mod / "data" / "a.csv", "id\na\n")
            _write(core / "data" / "b.csv", "id\nb\n")
            for changed in (mod / "data" / "added.csv", core / "data" / "added.csv"):
                with self.subTest(changed=changed.parent.parent.name):
                    with mock.patch.object(gene_set, "describe", side_effect=self._describe):
                        gene_set.walk(mod, "star-system:S", core, checkpoint_path=checkpoint)
                    _write(changed, "id\nnew\n")
                    with mock.patch.object(gene_set, "describe", side_effect=self._describe) as describe:
                        gene_set.walk(mod, "star-system:S", core, checkpoint_path=checkpoint)
                    self.assertEqual(describe.call_count, 4)  # walked afresh


class GeneSetProofTests(unittest.TestCase):
    def test_a_faction_and_its_genes_share_one_carrier_whose_proof_checks(self) -> None:
        with resolved_temp_dir() as root:
            ws, core = _with_faction(root), _vanilla(root)
            out = root / "proof"
            with redirect_stderr(io.StringIO()):
                result = gene_set.prove_set(ws, "faction:rebal_faction", out, vanilla_core=core)
            proof = json.loads((out / "set-isolation-proof.json").read_text(encoding="utf-8"))
            gene = json.loads((out / "gene.json").read_text(encoding="utf-8"))
            carrier = out / "work" / "carrier"
            info = json.loads((carrier / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(check(proof, gene, ws / "working"), [])  # the anchor's header; every carried file an input
            self.assertEqual((carrier / "data/world/factions/factions.csv").read_text(encoding="utf-8"),
                             "faction\ndata/world/factions/rebal.faction\n")
            self.assertTrue((carrier / "data/weapons/rebal_rail.wpn").is_file())
            self.assertTrue((carrier / "data/hullmods/FormShield.java").is_file())
            closure = sorted(p.name for p in (out / "closure").iterdir())
            self.assertFalse((root / "proof.closure.partial.jsonl").exists())
        carried = [c["anchor"] for c in proof["carried"]]
        self.assertEqual(carried[0], "faction:rebal_faction")
        self.assertEqual(sorted(carried[1:]), ["hullmod:shields_formshield", "weapon:rebal_rail"])
        self.assertEqual(len(closure), 3)
        self.assertEqual(info["id"], proof["carrier"]["id"])
        self.assertEqual(info["id"], f"gene_carrier_{proof['carrier']['set_identity'][:12]}")
        self.assertEqual((result["carried"], result["refused"]), (3, 0))
        self.assertEqual((proof["verdict"], result["verdict"], proof["failures"]), ("PASS", "PASS", []))
        self.assertEqual(proof["kind"], "set-isolation-proof")

    def test_a_refused_need_fails_the_set_and_is_listed(self) -> None:
        real = gene_set.walk

        def walk_with_a_refusal(*args, **kwargs):
            genes, refused = real(*args, **kwargs)
            return genes, {**refused, "market:rebal_port": "kind market cannot be closed yet"}

        with resolved_temp_dir() as root, mock.patch.object(gene_set, "walk", side_effect=walk_with_a_refusal), \
                redirect_stderr(io.StringIO()):
            result = gene_set.prove_set(_with_faction(root), "faction:rebal_faction", root / "proof", vanilla_core=_vanilla(root))
            proof = json.loads((root / "proof" / "set-isolation-proof.json").read_text(encoding="utf-8"))
        self.assertEqual((result["verdict"], proof["verdict"]), ("FAIL", "FAIL"))
        self.assertEqual(proof["refused"], [{"anchor": "market:rebal_port", "reason": "kind market cannot be closed yet"}])

    def test_a_knocked_out_gene_fails_the_set_naming_it(self) -> None:
        # Slice 12: the scan alone passed P3's set with a weapon, a hull or the faction removed (knock-out, 2026-11-20).
        real = gene_set.walk
        for dropped in ("weapon:rebal_rail", "hullmod:shields_formshield"):
            def walk_without(*args, _dropped=dropped, **kwargs):
                genes, refused = real(*args, **kwargs)
                return {a: g for a, g in genes.items() if a != _dropped}, refused

            with self.subTest(dropped=dropped), resolved_temp_dir() as root, \
                    mock.patch.object(gene_set, "walk", side_effect=walk_without), redirect_stderr(io.StringIO()):
                result = gene_set.prove_set(_with_faction(root), "faction:rebal_faction", root / "proof", vanilla_core=_vanilla(root))
                proof = json.loads((root / "proof" / "set-isolation-proof.json").read_text(encoding="utf-8"))
                self.assertEqual((result["verdict"], result["unresolved"]), ("FAIL", 1))
                self.assertEqual([(u["anchor"], u["named_by"]) for u in proof["unresolved_in_carrier"]],
                                 [(dropped, ["faction:rebal_faction"])])

    def test_two_star_systems_or_a_member_conflict_is_refused_before_building(self) -> None:
        systems = {"star-system:A": _gene("star-system:A", [], needs=["star-system:B"]), "star-system:B": _gene("star-system:B", [])}
        clash = {"faction:rebal_faction": _gene("faction:rebal_faction", [("x.png", "1" * 64)]),
                 "hull:h": _gene("hull:h", [("x.png", "2" * 64)])}
        with resolved_temp_dir() as root:
            for genes, anchor, message in ((systems, "star-system:A", "2 star systems"), (clash, "faction:rebal_faction", "x.png")):
                with self.subTest(message=message), mock.patch.object(gene_set, "walk", return_value=(genes, {})), \
                        self.assertRaisesRegex(ProofError, message):
                    gene_set.prove_set(root, anchor, root / f"out-{len(message)}", vanilla_core=root)
                self.assertFalse((root / f"out-{len(message)}" / "work").exists())

    def test_a_used_folder_or_a_missing_core_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            ws = _with_faction(root)
            _write(root / "used" / "x.txt", "x")
            with self.assertRaisesRegex(ProofError, "not empty"):
                gene_set.prove_set(ws, "faction:rebal_faction", root / "used", vanilla_core=_vanilla(root))
            with self.assertRaisesRegex(ProofError, "give --vanilla-core"):
                gene_set.prove_set(ws, "faction:rebal_faction", root / "fresh", vanilla_core=None)
            with redirect_stderr(io.StringIO()), self.assertRaisesRegex(ProofError, "ships no .faction file"):
                gene_set.prove_set(ws, "faction:nobody", root / "fresh", vanilla_core=_vanilla(root))  # the anchor itself refused


if __name__ == "__main__":
    unittest.main()
