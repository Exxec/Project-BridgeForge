"""saved-object-holds-market-ref (ROADMAP 60g(4)): the Station Augments save-cycle pattern."""
from __future__ import annotations

import unittest

from bridgeforge.saved_object_scan import entity_fields, saved_object_findings
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

AUGMENT = """package data.scripts;
public class Augment {
    private MarketAPI market;
    protected transient PlanetAPI planet;
    private static SectorEntityToken shared;
    private List<CampaignFleetAPI> fleets = new ArrayList<>();
    private String id;
    public Augment(MarketAPI market) { this.market = market; }
    void attach() { MarketAPI local = market; }
}
"""
STORE_BY_NEW = """package data.scripts;
public class Plugin {
    void onApplicationLoad() {
        Global.getSector().getMemoryWithoutUpdate().set("$aug", new Augment(null));
    }
}
"""
STORE_BY_VARIABLE = """package data.scripts;
public class Plugin {
    void onGameLoad() {
        Augment aug = new Augment(null);
        market.getMemoryWithoutUpdate().set("$aug", aug);
    }
}
"""
REGISTER_THIS = """package data.scripts;
public class Watcher implements EveryFrameScript {
    private SectorEntityToken station;
    Watcher() { Global.getSector().addScript(this); }
}
"""
TRANSIENT_LISTENER = """package data.scripts;
public class Quiet implements EveryFrameScript {
    private MarketAPI market;
    Quiet() { Global.getSector().addTransientScript(this); }
}
"""


def _findings(files: dict[str, str]):
    with resolved_temp_dir() as root:
        (root / "mod_info.json").write_text('{"id":"demo","version":"1"}', encoding="utf-8")
        for name, text in files.items():
            path = root / "data" / "scripts" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return [f for f in scan_mod(root).findings if f.id == "saved-object-holds-market-ref"]


class FieldTests(unittest.TestCase):
    def test_only_non_transient_non_static_entity_fields_count(self) -> None:
        text = AUGMENT
        begin = text.index("{")
        fields = entity_fields(text, begin, len(text.rstrip()))
        self.assertEqual(fields, ["MarketAPI market", "List<CampaignFleetAPI> fleets"])


class ScanTests(unittest.TestCase):
    def test_class_stored_in_a_memory_with_a_market_field_is_flagged(self) -> None:
        hits = _findings({"Augment.java": AUGMENT, "Plugin.java": STORE_BY_NEW})
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "REVIEW")
        self.assertEqual(hits[0].file, "data/scripts/Augment.java")
        self.assertIn("class:Augment", hits[0].evidence)
        self.assertIn("field:MarketAPI market", hits[0].evidence)

    def test_a_variable_stored_in_a_memory_variable_is_followed(self) -> None:
        text = STORE_BY_VARIABLE.replace("market.getMemoryWithoutUpdate()", "mem")
        text = text.replace("Augment aug", "MemoryAPI mem = Global.getSector().getMemoryWithoutUpdate();\n        Augment aug")
        hits = _findings({"Augment.java": AUGMENT, "Plugin.java": text})
        self.assertEqual([h.file for h in hits], ["data/scripts/Augment.java"])

    def test_a_script_registering_itself_is_flagged_but_a_transient_one_is_not(self) -> None:
        hits = _findings({"Watcher.java": REGISTER_THIS, "Quiet.java": TRANSIENT_LISTENER})
        self.assertEqual([h.file for h in hits], ["data/scripts/Watcher.java"])
        self.assertIn("field:SectorEntityToken station", hits[0].evidence)

    def test_an_unstored_class_with_market_fields_and_a_commented_store_are_not_flagged(self) -> None:
        commented = STORE_BY_NEW.replace("Global.getSector()", "// Global.getSector()")  # the whole statement is on that line
        hits = _findings({"Augment.java": AUGMENT, "Plugin.java": commented})
        self.assertEqual(hits, [])

    def test_pure_function_reports_how_the_class_is_saved(self) -> None:
        found = saved_object_findings({"A.java": AUGMENT, "P.java": STORE_BY_NEW})
        self.assertEqual(found[0]["how"], "stored in a memory or customData")


if __name__ == "__main__":
    unittest.main()
