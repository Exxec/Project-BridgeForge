from __future__ import annotations

import io
import json
import shutil
import subprocess
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from bridgeforge.api_diff import ApiDiffError, annotate_errors, diff_api_jars, render_method, resolve_api_jar
from bridgeforge.cli import main
from bridgeforge.java_toolchain import DEFAULT_JAVAC_ARGS, parse_javac_errors
from tests.support import resolved_temp_dir

# A miniature of the real drift: SectorAPI.addMessage moved to CampaignUIAPI (RC8), createFleet was
# dropped outright, a clock class moved package, an overload changed and a constant was removed.
OLD_API = {
    "api/campaign/SectorAPI.java": """package api.campaign;
public interface SectorAPI {
    void addMessage(String text);
    Object createFleet(String faction, String fleetType);
    float getDays(int shift);
    CampaignUIAPI getCampaignUI();
}""",
    "api/campaign/CampaignUIAPI.java": """package api.campaign;
public interface CampaignUIAPI { boolean isShowingDialog(); }""",
    "api/campaign/ClockAPI.java": """package api.campaign;
public interface ClockAPI { long getTimestamp(); }""",
    "api/Consts.java": """package api;
public class Consts {
    public static final int OLD_LIMIT = 3;
    public static final int KEPT = 1;
    private int hidden;
    public Consts(int size) {}
    void packagePrivate() {}
}""",
}
NEW_API = {
    "api/campaign/SectorAPI.java": """package api.campaign;
public interface SectorAPI {
    float getDays(long shift);
    CampaignUIAPI getCampaignUI();
    int getPlayerLevel();
}""",
    "api/campaign/CampaignUIAPI.java": """package api.campaign;
public interface CampaignUIAPI { boolean isShowingDialog(); void addMessage(String text); }""",
    "api/time/ClockAPI.java": """package api.time;
public interface ClockAPI { long getTimestamp(); }""",
    "api/Consts.java": """package api;
public class Consts {
    public static final int KEPT = 1;
    public Consts(String name) {}
    Runnable make() { return new Runnable() { public void run() {} }; }
}""",
}
MOD_SCRIPT = """import api.campaign.SectorAPI;
import api.campaign.ClockAPI;
public class OldScript {
    void go(SectorAPI sector) {
        sector.addMessage("hello");
        sector.createFleet("pirates", "raiders");
        sector.getDays(1.5f);
        new api.Consts(4);
    }
}"""


class RenderTests(unittest.TestCase):
    def test_descriptors_render_as_java(self):
        self.assertEqual(render_method("a/SectorAPI", "addMessage", "(Ljava/lang/String;I)V"), "void addMessage(String, int)")
        self.assertEqual(render_method("a/B", "f", "([[J[La/Outer$Inner;)[Z"), "boolean[] f(long[][], Outer.Inner[])")
        self.assertEqual(render_method("a/Consts", "<init>", "(I)V"), "Consts(int)")
        self.assertEqual(render_method("a/B", "odd", "(Q)V"), "odd(Q)V")

    def test_inputs_must_be_an_api_jar_or_a_core_folder_holding_one(self):
        with resolved_temp_dir() as root:
            with self.assertRaises(ApiDiffError):
                resolve_api_jar(root)
            (root / "starfarer.api.jar").write_bytes(b"")
            self.assertEqual(resolve_api_jar(root), root / "starfarer.api.jar")


class AnnotationWithoutJdkTests(unittest.TestCase):
    CATALOGUE = {
        "removed_classes": [{"class": "api.campaign.ClockAPI", "same_name_elsewhere": ["api.time.ClockAPI"]}],
        "changed_classes": {"api.campaign.SectorAPI": {
            "methods_removed": [{"name": "addMessage", "descriptor": "(Ljava/lang/String;)V", "signature": "void addMessage(String)",
                                 "same_name_in_class": [], "same_signature_elsewhere": ["api.campaign.CampaignUIAPI.addMessage(String)"]}],
            "fields_removed": [], "methods_added": []}},
    }

    def test_errors_the_catalogue_does_not_explain_are_left_alone(self):
        errors = [
            {"kind": "missing-symbol", "message": "cannot find symbol", "detail": ["symbol: method other()", "location: variable s of type SectorAPI"]},
            {"kind": "incompatible-types", "message": "incompatible types", "detail": []},
            {"kind": "missing-symbol", "message": "cannot find symbol", "detail": ["symbol: variable x"]},
        ]
        self.assertEqual(annotate_errors(errors, self.CATALOGUE), 0)
        self.assertFalse(any("api_changes" in error for error in errors))

    def test_generic_receiver_type_still_matches(self):
        errors = [{"kind": "missing-symbol", "message": "cannot find symbol",
                   "detail": ["symbol: method addMessage(String)", "location: variable s of type SectorAPI<Foo>"]}]
        self.assertEqual(annotate_errors(errors, self.CATALOGUE), 1)
        self.assertEqual(errors[0]["api_changes"][0]["same_signature_elsewhere"], ["api.campaign.CampaignUIAPI.addMessage(String)"])


    def test_compile_check_cli_prints_the_leads(self):
        outcome = {"status": "FAIL", "error_count": 1, "files": ["data/scripts/A.java"], "error_counts_by_kind": {"missing-symbol": 1},
                   "errors": [{"file": "data/scripts/A.java", "line": 7, "kind": "missing-symbol", "message": "cannot find symbol",
                               "detail": ["symbol: method addMessage(String)", "location: variable s of type SectorAPI"]}]}
        with resolved_temp_dir() as root:
            catalogue = root / "api-diff.json"
            catalogue.write_text(json.dumps(self.CATALOGUE), encoding="utf-8")
            stdout = io.StringIO()
            with patch("bridgeforge.compile_check.compile_loose_scripts", return_value=outcome), redirect_stdout(stdout):
                code = main(["compile-check", str(root), "--api-diff", str(catalogue)])
        self.assertEqual(code, 1)
        self.assertIn("API CHANGE A.java:7: api.campaign.SectorAPI.addMessage(String) removed; candidates: "
                      "api.campaign.CampaignUIAPI.addMessage(String)", stdout.getvalue())


class RealJarTests(unittest.TestCase):
    """Old/new API jars compiled by a real javac; skipped cleanly when no JDK is on PATH."""

    def setUp(self):
        javac = shutil.which("javac")
        if javac is None:
            self.skipTest("no javac on PATH")
        self.javac = javac

    def _compile(self, root: Path, sources: dict[str, str], out: Path, classpath: Path | None = None) -> subprocess.CompletedProcess:
        files = []
        for relative, text in sources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            files.append(str(path))
        out.mkdir(parents=True, exist_ok=True)
        # The same javac arguments compile-check uses, so the error wording is what annotate_errors sees there.
        command = [self.javac, *DEFAULT_JAVAC_ARGS, "-d", str(out)] + (["-cp", str(classpath)] if classpath else []) + files
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def _jar(self, root: Path, name: str, sources: dict[str, str]) -> Path:
        classes = root / f"{name}-classes"
        completed = self._compile(root / f"{name}-src", sources, classes)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        jar = root / f"{name}.jar"
        with zipfile.ZipFile(jar, "w") as archive:
            for path in sorted(classes.rglob("*.class")):
                archive.write(path, path.relative_to(classes).as_posix())
        return jar

    def test_catalogue_records_removals_moves_and_signature_changes(self):
        with resolved_temp_dir() as root:
            result = diff_api_jars(self._jar(root, "old", OLD_API), self._jar(root, "new", NEW_API))
        self.assertEqual(result["mode"], "API_DIFF")
        self.assertEqual(result["removed_classes"], [{"class": "api.campaign.ClockAPI", "same_name_elsewhere": ["api.time.ClockAPI"]}])
        self.assertEqual(result["added_classes"], ["api.time.ClockAPI"])
        sector = {m["name"]: m for m in result["changed_classes"]["api.campaign.SectorAPI"]["methods_removed"]}
        self.assertEqual(sector["addMessage"]["same_signature_elsewhere"], ["api.campaign.CampaignUIAPI.addMessage(String)"])
        self.assertEqual(sector["createFleet"]["same_signature_elsewhere"], [])
        self.assertEqual(sector["getDays"]["same_name_in_class"], ["float getDays(long)"])
        self.assertEqual(result["changed_classes"]["api.campaign.SectorAPI"]["methods_added"], ["float getDays(long)", "int getPlayerLevel()"])
        consts = result["changed_classes"]["api.Consts"]
        self.assertEqual([f["signature"] for f in consts["fields_removed"]], ["int OLD_LIMIT"])  # private `hidden` is not API
        self.assertEqual([m["signature"] for m in consts["methods_removed"]], ["Consts(int)"])  # package-private method is not API
        self.assertEqual(consts["methods_removed"][0]["same_name_in_class"], ["Consts(String)"])
        self.assertNotIn("api.Consts$1", json.dumps(result))  # anonymous classes are skipped
        self.assertEqual(result["summary"]["methods_removed"], 4)

    def test_real_javac_errors_get_the_catalogue_leads(self):
        with resolved_temp_dir() as root:
            old_jar, new_jar = self._jar(root, "old", OLD_API), self._jar(root, "new", NEW_API)
            catalogue = diff_api_jars(old_jar, new_jar)
            completed = self._compile(root / "mod", {"OldScript.java": MOD_SCRIPT}, root / "mod-out", classpath=new_jar)
        self.assertNotEqual(completed.returncode, 0)
        errors = parse_javac_errors(completed.stderr)
        self.assertEqual(annotate_errors(errors, catalogue), 5, completed.stderr)
        leads = {hint.get("removed") or hint.get("removed_class"): hint for error in errors for hint in error.get("api_changes", [])}
        self.assertEqual(leads["api.campaign.ClockAPI"]["same_name_elsewhere"], ["api.time.ClockAPI"])
        self.assertEqual(leads["api.campaign.SectorAPI.addMessage(String)"]["same_signature_elsewhere"], ["api.campaign.CampaignUIAPI.addMessage(String)"])
        self.assertEqual(leads["api.campaign.SectorAPI.createFleet(String, String)"]["same_signature_elsewhere"], [])
        self.assertEqual(leads["api.campaign.SectorAPI.getDays(int)"]["same_name_in_class"], ["float getDays(long)"])
        self.assertEqual(leads["api.Consts.Consts(int)"]["same_name_in_class"], ["Consts(String)"])

    def test_cli_writes_the_catalogue_and_takes_core_folders(self):
        with resolved_temp_dir() as root:
            old_core, new_core = root / "old-core", root / "new-core"
            old_core.mkdir()
            new_core.mkdir()
            shutil.copy(self._jar(root, "old", OLD_API), old_core / "starfarer.api.jar")
            shutil.copy(self._jar(root, "new", NEW_API), new_core / "starfarer.api.jar")
            output = root / "reports" / "api-diff.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["api-diff", str(old_core), str(new_core), "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertIn("4 methods and 1 fields removed", stdout.getvalue())
            self.assertIn("SectorAPI.addMessage(String)  -> api.campaign.CampaignUIAPI.addMessage(String)", stdout.getvalue())
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["summary"]["classes_removed"], 1)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["api-diff", str(root / "missing"), str(new_core)]), 2)


if __name__ == "__main__":
    unittest.main()
