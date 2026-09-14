"""Save baselines must give every observation a unique subject (Flu-X behavior-diff, 2026-09-13).

Every faction's known lists share the path /CampaignEngine/factionManager/factions/e/Faction/knownX,
so behavior-diff refused the baseline with "duplicate observation field".
"""

import tempfile
import unittest
from pathlib import Path

from bridgeforge.behavior_discovery import build_save_baseline

CAMPAIGN = """<CampaignEngine z="1">
  <factionManager z="2">
    <factions z="3">
      <e z="4">
        <Faction z="5">
          <id>alpha</id>
          <knownShips z="6">
            <st>a</st>
            <st>b</st>
          </knownShips>
        </Faction>
      </e>
      <e z="7">
        <Faction z="8">
          <id>beta</id>
          <knownShips z="9">
            <st>c</st>
          </knownShips>
        </Faction>
      </e>
      <e z="10">
        <Faction z="11">
          <knownShips z="12">
            <st>d</st>
          </knownShips>
        </Faction>
      </e>
      <e z="13">
        <Faction z="14">
          <knownShips z="15">
            <st>e</st>
          </knownShips>
        </Faction>
      </e>
    </factions>
  </factionManager>
</CampaignEngine>
"""


class SaveBaselineSubjectTests(unittest.TestCase):
    def test_known_lists_name_their_faction_and_never_collide(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "save_x"
            save.mkdir()
            (save / "campaign.xml").write_bytes(CAMPAIGN.encode("utf-8"))
            baseline = build_save_baseline(save, build="r1", scenario="fixture")
        known = [o for o in baseline["observations"] if o["observation"] == "save.known-list"]
        subjects = [o["subject"] for o in known]
        self.assertEqual(len(subjects), len(set(subjects)), subjects)
        by_owner = {s: o["fields"]["size"] for s, o in zip(subjects, known) if s.endswith("]")}
        # Path-independent: a faction written somewhere else in another save keeps its subject.
        self.assertEqual(by_owner, {"knownShips[alpha]": 2, "knownShips[beta]": 1})
        self.assertEqual(sum(1 for s in subjects if "#" in s), 1)  # the two owner-less lists are numbered


if __name__ == "__main__":
    unittest.main()
