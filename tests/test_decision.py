"""ROADMAP 80.4: `decision apply` runs only the ticked actions of a decision draft."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.decision import DecisionError, apply_draft, parse_checkboxes, template
from bridgeforge.models import Finding
from tests.support import resolved_temp_dir

TODAY = "2026-10-21"
REASON = "re-created for RC8 as TEM_Crusade (plan 5a)"
FINDINGS = [Finding(id="dropped-feature", category="c", severity="low", classification="REVIEW", confidence="high",
                    explanation="e", file="events.json", evidence=["tem_crusade"])]
BOXES = ["Accept the core findings", "Record the removals", "Schedule C4", "Add the live run"]


def _scan(_working: Path) -> list[Finding]:
    return FINDINGS


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _draft(root: Path, ticked: list[str], drop: str | None = None) -> Path:
    ws = root / "ws"
    (ws / "working" / "reports").mkdir(parents=True)
    (ws / "working" / "mod_info.json").write_text(json.dumps({"id": "ws", "version": "1.0"}), encoding="utf-8")
    (root / "ROADMAP.md").write_text("# Plan\n- C4 player reputation\n- other\n", encoding="utf-8")
    actions = [
        {"when": BOXES[0], "type": "accept_findings", "workspace": ".", "selectors": ["dropped-feature"], "reason": REASON},
        {"when": BOXES[1], "type": "record_removals", "workspace": ".",
         "entries": [{"category": "classes", "item": "a.B", "reason": "replaced", "source": "owner"}]},
        {"when": BOXES[2], "type": "schedule", "file": "../ROADMAP.md", "anchor": "C4 player", "line": "Recreate texts"},
        {"when": BOXES[3], "type": "rig_step", "gates_repo": ".", "gate": {"id": "live", "status": "NOT_TESTED"}},
    ]
    boxes = "\n".join(f"- [{'x' if b in ticked else ' '}] {b}" for b in BOXES if b != drop)
    path = ws / "DRAFT.md"
    block = json.dumps({"schema": 1, "actions": actions})
    path.write_text(f"# Draft\n\n{boxes}\n\n```bf-decision\n{block}\n```\n", encoding="utf-8")
    return path


class ApplyDraftTests(unittest.TestCase):
    def test_runs_only_ticked_actions(self) -> None:
        with resolved_temp_dir() as root:
            draft = _draft(root, [BOXES[0], BOXES[2]])
            result = apply_draft(draft, today=TODAY, scan=_scan)
            statuses = [r["status"] for r in result["results"]]
            baseline = json.loads((root / "ws" / "working" / "reports" / "baseline.json").read_text(encoding="utf-8"))
            roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8").splitlines()
            text = draft.read_text(encoding="utf-8")
            self.assertFalse((root / "ws" / "working" / "reports" / "REMOVALS.json").exists())
            self.assertFalse((root / "ws" / "gates.json").exists())
        self.assertEqual(statuses, ["changed", "skipped", "changed", "skipped"])
        self.assertEqual(len(baseline["findings"]), 1)
        self.assertEqual(roadmap[2], f"- {TODAY}: Recreate texts")
        self.assertIn(f"## Applied {TODAY}", text)

    def test_all_ticked_writes_removals_and_gate(self) -> None:
        with resolved_temp_dir() as root:
            apply_draft(_draft(root, BOXES), today=TODAY, scan=_scan)
            removals = json.loads((root / "ws" / "working" / "reports" / "REMOVALS.json").read_text(encoding="utf-8"))
            gates = json.loads((root / "ws" / "gates.json").read_text(encoding="utf-8"))
        self.assertEqual(removals["removals"][0]["date"], TODAY)
        self.assertEqual(gates["gates"][0]["id"], "live")

    def test_missing_box_refuses_before_any_change(self) -> None:
        with resolved_temp_dir() as root:
            draft = _draft(root, BOXES, drop=BOXES[3])
            before = draft.read_text(encoding="utf-8")
            with self.assertRaisesRegex(DecisionError, "Add the live run"):
                apply_draft(draft, today=TODAY, scan=_scan)
            self.assertEqual(draft.read_text(encoding="utf-8"), before)
            self.assertFalse((root / "ws" / "working" / "reports" / "baseline.json").exists())

    def test_second_run_changes_nothing(self) -> None:
        with resolved_temp_dir() as root:
            draft = _draft(root, BOXES)
            apply_draft(draft, today=TODAY, scan=_scan)
            before = _snapshot(root)
            again = apply_draft(draft, today="2026-10-22", scan=_scan)
            after = _snapshot(root)
        self.assertFalse(again["changed"])
        self.assertEqual(before, after)

    def test_dry_run_changes_nothing_but_reports(self) -> None:
        with resolved_temp_dir() as root:
            draft = _draft(root, BOXES)
            before = _snapshot(root)
            result = apply_draft(draft, dry_run=True, today=TODAY, scan=_scan)
            after = _snapshot(root)
        self.assertTrue(result["changed"])
        self.assertEqual(before, after)

    def test_bad_anchor_and_bad_block_are_errors(self) -> None:
        with resolved_temp_dir() as root:
            draft = _draft(root, [BOXES[2]])
            (root / "ROADMAP.md").write_text("nothing\n", encoding="utf-8")
            with self.assertRaisesRegex(DecisionError, "anchor"):
                apply_draft(draft, today=TODAY, scan=_scan)
            draft.write_text("- [x] a\n", encoding="utf-8")
            with self.assertRaisesRegex(DecisionError, "bf-decision"):
                apply_draft(draft, today=TODAY, scan=_scan)


class SurfaceTests(unittest.TestCase):
    def test_checkbox_labels_ignore_case_and_spacing(self) -> None:
        self.assertEqual(parse_checkboxes("- [X]  Foo   Bar\n- [ ] baz"), {"foo bar": True, "baz": False})

    def test_template_cli_prints_it(self) -> None:
        self.assertIn("```bf-decision", template("port-dropped-feature"))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["decision", "template", "port-dropped-feature"]), 0)
        self.assertEqual(out.getvalue(), template("port-dropped-feature"))

    def test_cli_apply_json_and_refusal(self) -> None:
        with resolved_temp_dir() as root:
            draft = _draft(root, [BOXES[2]])
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["decision", "apply", str(draft), "--dry-run", "--json"]), 0)
            self.assertTrue(json.loads(out.getvalue())["dry_run"])
            draft.write_text("nothing", encoding="utf-8")
            self.assertEqual(main(["decision", "apply", str(draft)]), 2)


if __name__ == "__main__":
    unittest.main()
