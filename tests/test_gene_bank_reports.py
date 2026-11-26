"""94.G3 slice 3a: read-only lineage and licence reports over the gene bank (docs/GENE_BANK_DESIGN.md). Synthetic banks."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from bridgeforge.genome.bank import Bank, BankError, run_bank_cli
from bridgeforge.genome.bank_reports import TRIVIAL_STRING_CHARS, licences, lineage, write_report
from tests.support import resolved_temp_dir, write_text as _write

COPIED = b"a sprite both mods ship, byte for byte"
LONG_TEXT = json.dumps("A description long enough that two mods holding it is a copy, not chance.").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeBank:
    """A bank folder written by hand: records, entries, manifests and blobs, the parts the reports read."""

    def __init__(self, root: Path):
        self.root = root / "Genes"
        self.current: list[str] = []
        self.n = 0

    def blob(self, data: bytes) -> str:
        digest = _sha(data)
        path = self.root / "blobs" / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return digest

    def record(self, mod_id: str | None, anchor: str, *, version: str = "1.0", folder: str = "working", members: dict | None = None,
               donor: dict | None = None, decision: str = "UNRECORDED", mod_decision: str | None = None,
               local_only_members: list[str] | None = None, mod_name: str | None = None, current: bool = True,
               source_path: str | None = None) -> str:
        self.n += 1
        members = {path: self.blob(data) for path, data in (members or {}).items()}
        donor = {path: self.blob(data) for path, data in (donor or {}).items()}
        manifest = {"provenance": {"mod_id": mod_id, "mod_name": mod_name or mod_id, "author": "a"},
                    "members": [{"what": "file", "path": path, "sha256": digest} for path, digest in members.items()],
                    "licence": {"decision": decision, "reason": "r", "mod_decision": mod_decision or decision,
                                "local_only_members": local_only_members or []}}
        text = json.dumps(manifest, sort_keys=True).encode("utf-8")
        mh = _sha(text)
        _write(self.root / "manifests" / mh[:2] / f"{mh}.json", text.decode("utf-8"))
        rid = f"{self.n:064x}"
        record = {"manifest": mh, "identity": f"{self.n:064x}", "kind": anchor.split(":", 1)[0], "anchor": anchor,
                  "source": {"mod_id": mod_id, "mod_version": version, "folder": folder,
                             "path": source_path or f"In operation/{mod_id}/{folder}"},
                  "build": "0.98.5a-RC7", "licence": decision, "members": members, "donor": donor, "needs_genes": [],
                  "needs_refused": {}}
        _write(self.root / "records" / f"{rid}.json", json.dumps(record, sort_keys=True))
        if current:
            self.current.append(rid)
        return rid

    def finish(self) -> Bank:
        entries = [{"path": f"p{i}", "folder": "working", "anchor": "a", "build": "0.98.5a-RC7", "records": [rid]}
                   for i, rid in enumerate(self.current)]
        _write(self.root / "entries.json", json.dumps(entries, sort_keys=True))
        _write(self.root / "ROOT", "f" * 64 + "\n")
        return Bank(self.root)


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


class LineageTests(unittest.TestCase):
    def _bank(self, root: Path) -> Bank:
        fake = FakeBank(root)
        fake.record("mod_a", "hull:a_ship", members={"graphics/s.png": COPIED, "data/a.json#/desc": LONG_TEXT})
        fake.record("mod_b", "hull:b_ship", members={"graphics/other/s.png": COPIED, "data/b.json#/text": LONG_TEXT})
        # The same mod in two releases holding one blob: an allele, not lineage.
        fake.record("mod_a", "hullmod:a_mod", version="1.1", members={"data/m.csv [a_mod]": b"row of mod a"})
        fake.record("mod_a", "hullmod:a_mod", version="1.0", folder="original", members={"data/m.csv [a_mod]": b"row of mod a"})
        # Two genes of one release holding one blob: neither an allele nor lineage.
        fake.record("mod_b", "hullmod:b1", members={"data/x.csv [b1]": b"one release, two genes"})
        fake.record("mod_b", "hullmod:b2", members={"data/x.csv [b2]": b"one release, two genes"})
        # A member on one side, a donor need on the other (the 2026-11-26 count on Test1's bank).
        fake.record("mod_a", "hullmod:tanks", members={"data/config/settings.json#/days": b"3"})
        fake.record("mod_c", "faction:c", members={"data/c.faction": b"faction c"},
                    donor={"data/world/factions/default_ship_roles.json#/combatLarge/c_ship": b"3",
                           "data/config/hull_styles.json#/SHARED": b'{"style": "a donor both sides need"}'})
        fake.record("mod_b", "hull:b_styled", members={"data/hulls/b_styled.ship": b"b styled"},
                    donor={"data/config/hull_styles.json#/SHARED": b'{"style": "a donor both sides need"}'})
        # Trivial values both sides hold as members.
        fake.record("mod_b", "hullmod:flags", members={"data/config/settings.json#/on": b"true", "data/config/settings.json#/id": b'"b_id"'})
        fake.record("mod_c", "hullmod:c_flags", members={"data/config/settings.json#/enabled": b"true",
                                                          "data/config/settings.json#/tag": b'"b_id"'})
        # A history record only: never counted.
        fake.record("mod_d", "hull:d_ship", members={"graphics/s.png": COPIED}, current=False)
        return fake.finish()

    def test_a_member_blob_two_mod_ids_hold_is_shared_and_coincidences_are_counted_apart(self) -> None:
        with resolved_temp_dir() as root:
            report = lineage(self._bank(root))
        self.assertEqual(report["counts"]["shared_blobs"], 2)
        self.assertEqual(report["counts"]["across_copies_of_one_mod"], 1)  # mod_a 1.1 and 1.0; not mod_b's two genes
        # The donor-only overlap counts once whether a member holds it on one side or no member holds it at all.
        self.assertEqual(report["counts"]["excluded"], {"donor_side": 2, "trivial_value": 2, "vanilla_file": 0})
        (group,) = report["shared"]
        self.assertEqual(group["mods"], ["mod_a", "mod_b"])
        holders = sorted((h["mod_id"], h["anchor"], h["path"]) for blob in group["blobs"] for h in blob["holders"])
        self.assertEqual(holders, [("mod_a", "hull:a_ship", "data/a.json#/desc"), ("mod_a", "hull:a_ship", "graphics/s.png"),
                                   ("mod_b", "hull:b_ship", "data/b.json#/text"), ("mod_b", "hull:b_ship", "graphics/other/s.png")])
        self.assertNotIn("mod_d", json.dumps(report))  # history records are outside the report, as outside the ROOT
        self.assertNotIn("copied", json.dumps(report).lower())  # a hash carries no direction

    def test_a_blob_equal_to_a_vanilla_data_file_is_excluded_when_a_core_is_given(self) -> None:
        with resolved_temp_dir() as root:
            bank = self._bank(root)
            _write(root / "core" / "data" / "graphics_copy" / "s.png", COPIED.decode("utf-8"))
            report = lineage(bank, vanilla_core=root / "core")
        self.assertEqual((report["counts"]["shared_blobs"], report["counts"]["excluded"]["vanilla_file"]), (1, 1))

    def test_a_short_string_is_trivial_and_a_long_one_is_not(self) -> None:
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            short = json.dumps("x" * TRIVIAL_STRING_CHARS).encode("utf-8")
            longer = json.dumps("y" * (TRIVIAL_STRING_CHARS + 1)).encode("utf-8")
            for mod in ("mod_a", "mod_b"):
                fake.record(mod, f"hullmod:{mod}", members={"data/s.json#/short": short, "data/s.json#/long": longer,
                                                             "data/s.json#/empty": b"[]", "data/blank.txt": b""})
            report = lineage(fake.finish())
        self.assertEqual((report["counts"]["shared_blobs"], report["counts"]["excluded"]["trivial_value"]), (1, 3))

    def test_a_text_file_equal_to_vanilla_after_normalisation_is_vanilla(self) -> None:
        # Members of text files are hashed normalised (no BOM, LF, no trailing spaces): so must vanilla's files be.
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            text = b"id,name\nfx_a,Alpha\nfx_b,Beta"
            for mod in ("mod_a", "mod_b"):
                fake.record(mod, f"hullmod:{mod}", members={"data/config/table.csv": text})
            bank = fake.finish()
            vanilla = root / "core" / "data" / "config" / "table.csv"
            vanilla.parent.mkdir(parents=True)
            vanilla.write_bytes(b"\xef\xbb\xbfid,name \r\nfx_a,Alpha\r\nfx_b,Beta\r\n\r\n")
            report = lineage(bank, vanilla_core=root / "core")
        self.assertEqual((report["counts"]["shared_blobs"], report["counts"]["excluded"]["vanilla_file"]), (0, 1))

    def test_two_mods_without_an_id_stay_two_and_a_bad_source_does_not_crash(self) -> None:
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            fake.record(None, "hull:x", members={"graphics/s.png": COPIED}, source_path="In operation/X/working")
            fake.record(None, "hull:y", members={"graphics/s.png": COPIED}, source_path="In operation/Y/working")
            broken = fake.record("mod_z", "hull:z", members={"graphics/z.png": b"z"})
            bank = fake.finish()
            path = bank.root / "records" / f"{broken}.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(json.dumps({**record, "source": None}), encoding="utf-8")
            report = lineage(bank)
            licence_report = licences(bank)
        (group,) = report["shared"]
        self.assertEqual(group["mods"], ["(no mod id: In operation/X/working)", "(no mod id: In operation/Y/working)"])
        self.assertEqual((report["counts"]["mod_ids"], licence_report["counts"]["current_records"]), (3, 3))

    def test_an_unreadable_current_record_is_counted_and_a_missing_shared_blob_is_a_bank_error(self) -> None:
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            fake.record("mod_a", "hull:a", members={"graphics/s.png": COPIED})
            fake.record("mod_b", "hull:b", members={"graphics/s.png": COPIED})
            gone = fake.record("mod_c", "hull:c", members={"graphics/c.png": b"c"})
            bank = fake.finish()
            (bank.root / "records" / f"{gone}.json").write_text("{not json", encoding="utf-8")
            counted = lineage(bank)["counts"]
            blob = bank.root / "blobs" / _sha(COPIED)[:2] / _sha(COPIED)
            blob.unlink()
            with self.assertRaisesRegex(BankError, "gene bank verify"):
                lineage(bank)
        self.assertEqual((counted["current_records"], counted["unreadable_current_records"]), (2, 1))

    def test_the_report_changes_nothing_in_the_bank(self) -> None:
        with resolved_temp_dir() as root:
            bank = self._bank(root)
            before = _snapshot(bank.root)
            out = write_report(bank, root / "reports" / "lineage.json", lineage(bank))
            after = _snapshot(bank.root)
            written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(before, after)
        self.assertEqual((written["report"], written["root"]), ("lineage", "f" * 64))


class LicenceTests(unittest.TestCase):
    def test_narrowed_genes_and_drift_from_todays_ledger_are_flagged_not_fixed(self) -> None:
        with resolved_temp_dir() as root:
            policy = root / "policy" / "release_policy.json"
            art = {"prefix": "graphics/other_author", "local_only": True, "reason": "another author's sprites"}
            _write(policy, json.dumps({"schema_version": 1, "default": {"local_only": False, "reason": None},
                                       "mods": {"mod_b": {"local_only": True, "reason": "author asked", "recorded_on": "2026-11-26"},
                                                "mod_e": {"local_only": False, "reason": "MIT", "recorded_on": "2026-11-26",
                                                          "paths": [art]},
                                                "mod_f": {"local_only": True, "reason": "no licence", "recorded_on": "2026-11-26"}}}))
            fake = FakeBank(root)
            fake.record("mod_a", "hull:a_ship", members={"graphics/x.png": b"x"}, decision="LOCAL_ONLY",
                        mod_decision="UNRECORDED", local_only_members=["graphics/x.png"])
            fake.record("mod_b", "hull:b_ship", members={"graphics/y.png": b"y"}, decision="UNRECORDED")
            # Releasable, narrowed by today's path exception exactly as when it was banked: narrowed, and no drift.
            fake.record("mod_e", "hull:e_ship", members={"graphics/other_author/e.png": b"e"}, decision="LOCAL_ONLY",
                        mod_decision="RELEASABLE", local_only_members=["graphics/other_author/e.png"])
            # Local-only as a whole mod: LOCAL_ONLY, but not narrowed, and no drift.
            fake.record("mod_f", "hull:f_ship", members={"graphics/f.png": b"f"}, decision="LOCAL_ONLY")
            bank = fake.finish()
            before = _snapshot(bank.root)
            report = licences(bank, policy_path=policy)
            after = _snapshot(bank.root)
        self.assertEqual(before, after)
        self.assertEqual(report["counts"]["by_decision"], {"LOCAL_ONLY": 3, "UNRECORDED": 1})
        self.assertEqual(sorted(row["anchor"] for row in report["narrowed"]), ["hull:a_ship", "hull:e_ship"])
        self.assertEqual(report["by_mod"]["mod_e"], {"LOCAL_ONLY": 1})
        # mod_a's member is local-only by its banked manifest, but today's policy has no such path: drift, flagged.
        drift = {row["anchor"]: (row["banked"], row["ledger_today"]) for row in report["drift"]}
        self.assertEqual(drift, {"hull:a_ship": ("LOCAL_ONLY", "UNRECORDED"), "hull:b_ship": ("UNRECORDED", "LOCAL_ONLY")})


class RealBankTests(unittest.TestCase):
    def test_both_reports_over_a_put_bank_leave_its_root_and_verify_unchanged(self) -> None:
        from bridgeforge.genome.bank import put
        from tests.test_gene_bank import _base

        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            stored = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            bank = Bank(root / "Genes")
            before = _snapshot(bank.root)
            lineage_report = lineage(bank, vanilla_core=core)
            licence_report = licences(bank)
            write_report(bank, root / "reports" / "lineage.json", lineage_report)
            write_report(bank, root / "reports" / "licences.json", licence_report)
            after, problems = _snapshot(bank.root), bank.verify()
        self.assertEqual((before, problems), (after, []))
        self.assertEqual((lineage_report["root"], licence_report["root"]), (stored["root"], stored["root"]))
        self.assertEqual((lineage_report["counts"]["current_records"], lineage_report["counts"]["shared_blobs"]), (1, 0))
        self.assertEqual(licence_report["counts"]["by_decision"], {"UNRECORDED": 1})
        self.assertEqual(licence_report["drift"], [])  # the ledger has not changed since the put


class ReportOutputTests(unittest.TestCase):
    def test_an_out_file_inside_the_bank_is_refused_and_nothing_is_written(self) -> None:
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            fake.record("mod_a", "hull:a_ship", members={"graphics/s.png": COPIED})
            bank = fake.finish()
            before = _snapshot(bank.root)
            with self.assertRaises(BankError):
                write_report(bank, bank.root / "lineage.json", lineage(bank))
            with self.assertRaises(BankError):
                write_report(bank, bank.root / "blobs" / "x.json", lineage(bank))
            after = _snapshot(bank.root)
        self.assertEqual(before, after)

    @unittest.skipUnless(sys.platform == "win32", "Windows path forms")
    def test_windows_spellings_of_the_bank_folder_are_refused(self) -> None:
        # Windows strips a trailing space from a path segment, and \\?\ skips normalisation; both name the bank
        # but resolve to text that never equals it (review of slice 3a).
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            fake.record("mod_a", "hull:a_ship", members={"graphics/s.png": COPIED})
            bank = fake.finish()
            before = _snapshot(bank.root)
            for out in (Path(str(bank.root) + " ") / "lineage.json", Path("\\\\?\\" + str(bank.root.resolve())) / "lineage.json"):
                with self.subTest(out=str(out)), self.assertRaises(BankError):
                    write_report(bank, out, lineage(bank))
            after = _snapshot(bank.root)
        self.assertEqual(before, after)

    def test_the_cli_writes_both_reports_and_refuses_an_out_inside_the_bank(self) -> None:
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            fake.record("mod_a", "hull:a_ship", members={"graphics/s.png": COPIED})
            fake.record("mod_b", "hull:b_ship", members={"graphics/s.png": COPIED})
            bank = fake.finish()
            runs = {}
            for command, out in (("lineage", root / "out" / "lineage.json"), ("licences", root / "out" / "licences.json"),
                                 ("lineage", bank.root / "inside.json")):
                args = SimpleNamespace(bank_command=command, bank=bank.root, out=out, vanilla_core=None)
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = run_bank_cli(args)
                runs[(command, out.name)] = (code, stdout.getvalue(), stderr.getvalue(), out.is_file())
        self.assertEqual(runs[("lineage", "lineage.json")][0], 0)
        self.assertIn("1 shared blob", runs[("lineage", "lineage.json")][1])
        self.assertEqual(runs[("licences", "licences.json")][0], 0)
        self.assertEqual(runs[("lineage", "inside.json")][0], 2)
        self.assertFalse(runs[("lineage", "inside.json")][3])


if __name__ == "__main__":
    unittest.main()
