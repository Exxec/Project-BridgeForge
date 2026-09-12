from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.save_summary import redacted_summary
from tests.save_fixtures import write_descriptor, write_mod_data, write_mod_info, write_text

SAVE_HEADER = '<?xml version="1.0" ?>\n<CampaignEngine z="1">\n'
SAVE_FOOTER = "</CampaignEngine>\n"


class RedactedSummaryTests(unittest.TestCase):
    def test_no_player_data_and_writes_to_given_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save_TopSecretPlayerName_12345"
            write_descriptor(
                save_dir,
                [{"id": "samplemod", "name": "Sample [BF r2]", "version": "1.0"}],
                character_name="TopSecretPlayerName",
            )
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_data(mod_dir, hulls=("samplemod_hull",))
            xml = (
                SAVE_HEADER
                + "<st>samplemod_hull</st>\n"
                + '<FMmbr z="2" sid="samplemod_hull" sN="Secret Ship Name"></FMmbr>\n'
                + SAVE_FOOTER
            )
            write_text(save_dir / "campaign.xml", xml)
            out_path = Path(directory) / "out" / "summary.json"

            summary = redacted_summary(save_dir, [mod_dir], out_path=out_path)

            self.assertTrue(out_path.is_file())
            on_disk = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, summary)

            raw = out_path.read_text(encoding="utf-8")
            self.assertNotIn("TopSecretPlayerName", raw)
            self.assertNotIn("Secret Ship Name", raw)

            self.assertNotEqual(summary["save_id_hash"], str(save_dir))
            self.assertEqual(len(summary["save_id_hash"]), 16)
            self.assertEqual(summary["mods"][0]["id"], "samplemod")
            check = summary["checks"][0]
            self.assertEqual(check["mod_id"], "samplemod")
            self.assertEqual(check["content_compat_status"], "LOADS")

    def test_writes_only_to_caller_given_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            write_descriptor(save_dir, [{"id": "samplemod", "version": "1.0"}])
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_text(save_dir / "campaign.xml", SAVE_HEADER + SAVE_FOOTER)
            out_path = Path(directory) / "chosen_location.json"

            redacted_summary(save_dir, [mod_dir], out_path=out_path)

            other_candidates = list(save_dir.glob("*summary*")) + list(mod_dir.glob("*summary*"))
            self.assertEqual(other_candidates, [])
            self.assertTrue(out_path.is_file())


if __name__ == "__main__":
    unittest.main()
