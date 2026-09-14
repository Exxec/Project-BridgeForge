"""Generated reference docs: docs/CHECKS.md (checks) and docs/COMMANDS.md (CLI), read from the source.

CHECKS.md comes from `ast`, so it can't drift. It lists:
- every `.add(id=...)` finding (including table-driven ids such as LEGACY_API_RULES) and every
  revival-audit `_issue(...)`;
- their classification and severity (both branches of a conditional), the emitting `module:function`,
  the first sentence of the explanation, the test modules that name the id, and the docs/BUG_CLASSES.md
  classes that cite it;
- scanner.py's private helpers with signatures.

COMMANDS.md walks the real argparse parser, nested subcommands included. `tests/test_checks_index.py`
fails when either file is stale, and holds the untested-finding ratchet
(tests/untested_checks_baseline.json). Regenerate with `bridgeforge docs-index`.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER_MODULE = "scanner.py"
UNTESTED_BASELINE = Path("tests") / "untested_checks_baseline.json"


@dataclass
class Check:
    id: str
    classifications: set[str] = field(default_factory=set)
    severities: set[str] = field(default_factory=set)
    where: set[str] = field(default_factory=set)
    explanation: str = ""


@dataclass
class Catalogue:
    checks: dict[str, Check]
    issues: dict[str, Check]
    tests: dict[str, list[str]]
    bug_classes: dict[str, list[str]]

    @property
    def untested(self) -> list[str]:
        return sorted(key for key in self.checks if not self.tests.get(key))


def _values(node: ast.AST | None) -> set[str]:
    """Literal strings a keyword can take: both branches of `a if c else b`; f-strings as patterns."""
    if node is None:
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _values(node.body) | _values(node.orelse)
    if isinstance(node, ast.JoinedStr):
        return {"".join(part.value if isinstance(part, ast.Constant) else "{...}" for part in node.values)}
    return {"(computed)"}


def _render_text(node: ast.AST | None) -> str:
    """Readable text of an explanation expression: f-string parts joined, `+` chains concatenated."""
    if node is None:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value if isinstance(part, ast.Constant) else "{...}" for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _render_text(node.left) + _render_text(node.right)
    if isinstance(node, ast.IfExp):
        return _render_text(node.body)
    return next((sub.value for sub in ast.walk(node) if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value.strip()), "")


def _first_sentence(node: ast.AST | None) -> str:
    text = " ".join(_render_text(node).split())
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    return sentence if len(sentence) <= 160 else sentence[:157].rstrip() + "..."


def _string_tables(tree: ast.Module) -> dict[str, list[tuple[str, ...]]]:
    """Module-level `NAME = {key: ("id", "explanation"), ...}` tables (scanner's LEGACY_API_RULES)."""
    tables: dict[str, list[tuple[str, ...]]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Dict):
            rows = []
            for value in node.value.values:
                if isinstance(value, ast.Tuple) and all(isinstance(elt, ast.Constant) and isinstance(elt.value, str) for elt in value.elts):
                    rows.append(tuple(elt.value for elt in value.elts))
            if rows and len(rows) == len(node.value.values):
                tables[node.targets[0].id] = rows
    return tables


class _Collector(ast.NodeVisitor):
    def __init__(self, module: str, tables: dict[str, list[tuple[str, ...]]] | None = None) -> None:
        self.module = module
        self.tables = tables or {}
        self.bindings: dict[str, list[str]] = {}
        self.stack: list[str] = []
        self.checks: list[tuple[str, dict]] = []
        self.issues: list[tuple[str, dict]] = []

    def _function(self, node: ast.AST) -> None:
        self.stack.append(node.name)  # type: ignore[attr-defined]
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_For(self, node: ast.For) -> None:
        # `for key, (rule_id, explanation) in TABLE.items():` binds each name to that column of TABLE.
        bound: dict[str, list[str]] = {}
        iterator = node.iter
        if (isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Attribute) and iterator.func.attr == "items"
                and isinstance(iterator.func.value, ast.Name) and iterator.func.value.id in self.tables
                and isinstance(node.target, ast.Tuple) and len(node.target.elts) == 2 and isinstance(node.target.elts[1], ast.Tuple)):
            rows = self.tables[iterator.func.value.id]
            for index, elt in enumerate(node.target.elts[1].elts):
                if isinstance(elt, ast.Name):
                    bound[elt.id] = [row[index] if index < len(row) else "" for row in rows]
        saved = dict(self.bindings)
        self.bindings.update(bound)
        self.generic_visit(node)
        self.bindings = saved

    def visit_Call(self, node: ast.Call) -> None:
        where = f"{self.module}:{self.stack[0] if self.stack else '<module>'}"
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        if isinstance(node.func, ast.Attribute) and node.func.attr == "add" and "id" in keywords:
            id_node, explanation_node = keywords["id"], keywords.get("explanation")
            common = {"where": where, "classification": _values(keywords.get("classification")), "severity": _values(keywords.get("severity"))}
            if isinstance(id_node, ast.Name) and id_node.id in self.bindings:
                explanations = self.bindings.get(explanation_node.id, []) if isinstance(explanation_node, ast.Name) else []
                for index, check_id in enumerate(self.bindings[id_node.id]):
                    text = explanations[index] if index < len(explanations) else ""
                    self.checks.append((check_id, {**common, "explanation": _first_sentence(ast.Constant(text)) if text else _first_sentence(explanation_node)}))
            else:
                for check_id in _values(id_node):
                    self.checks.append((check_id, {**common, "explanation": _first_sentence(explanation_node)}))
        elif isinstance(node.func, ast.Name) and node.func.id == "_issue" and len(node.args) >= 3:
            for issue_id in _values(node.args[0]):
                self.issues.append((issue_id, {"where": where, "severity": _values(node.args[1]), "explanation": _first_sentence(node.args[2])}))
        self.generic_visit(node)


def _merge(table: dict[str, Check], key: str, info: dict) -> None:
    item = table.setdefault(key, Check(key))
    item.classifications |= info.get("classification", set())
    item.severities |= info["severity"]
    item.where.add(info["where"])
    item.explanation = item.explanation or info["explanation"]


def collect(source: str, module: str) -> tuple[dict[str, Check], dict[str, Check]]:
    """(scan findings, revival-audit issues) defined in one module's source."""
    tree = ast.parse(source)
    collector = _Collector(module, _string_tables(tree))
    collector.visit(tree)
    checks: dict[str, Check] = {}
    issues: dict[str, Check] = {}
    for key, info in collector.checks:
        _merge(checks, key, info)
    for key, info in collector.issues:
        _merge(issues, key, info)
    return checks, issues


def bug_class_links(markdown: str) -> dict[str, list[str]]:
    """finding id -> the docs/BUG_CLASSES.md classes whose check column names it in backticks."""
    links: dict[str, set[str]] = {}
    for line in markdown.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if len(cells) < 6 or not re.match(r"[A-Z]", cells[0]):
            continue
        classes = [part.strip() for part in cells[0].split("/") if part.strip()]
        for finding_id in re.findall(r"`([a-z][a-z0-9-]*)`", cells[3]):
            links.setdefault(finding_id, set()).update(classes)
    return {key: sorted(value) for key, value in links.items()}


def _tests_naming(identifier: str, test_texts: dict[str, str]) -> list[str]:
    needle = identifier.split("{...}")[0]
    if not needle or needle == "(computed)":
        return []
    return sorted(name for name, text in test_texts.items() if f'"{needle}' in text or f"'{needle}" in text)


def gather(repo_root: Path = REPO_ROOT) -> Catalogue:
    checks: dict[str, Check] = {}
    issues: dict[str, Check] = {}
    for path in sorted((repo_root / "bridgeforge").glob("*.py")):
        module_checks, module_issues = collect(path.read_text(encoding="utf-8"), path.name)
        for table, found in ((checks, module_checks), (issues, module_issues)):
            for key, item in found.items():
                merged = table.setdefault(key, Check(key))
                merged.classifications |= item.classifications
                merged.severities |= item.severities
                merged.where |= item.where
                merged.explanation = merged.explanation or item.explanation
    # The generated docs and this index's own tests don't count as coverage.
    test_texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted((repo_root / "tests").glob("test_*.py")) if path.stem != "test_checks_index"}
    tests = {key: _tests_naming(key, test_texts) for key in list(checks) + list(issues)}
    registry = repo_root / "docs" / "BUG_CLASSES.md"
    links = bug_class_links(registry.read_text(encoding="utf-8")) if registry.is_file() else {}
    return Catalogue(checks, issues, tests, links)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _join(values) -> str:
    return ", ".join(sorted(values)) or "-"


def _helpers(source: str) -> list[tuple[str, str, str]]:
    rows = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_") and not node.name.startswith("_scan_"):
            signature = f"({ast.unparse(node.args)})" + (f" -> {ast.unparse(node.returns)}" if node.returns else "")
            doc = ast.get_docstring(node) or ""
            rows.append((node.name, signature, " ".join(doc.split("\n\n")[0].split())))
    return sorted(rows)


def build_checks_index(repo_root: Path = REPO_ROOT) -> str:
    catalogue = gather(repo_root)
    checks, issues = catalogue.checks, catalogue.issues
    modules = {where.split(":")[0] for check in checks.values() for where in check.where}
    lines = [
        "# BridgeForge checks",
        "",
        "Generated by `bridgeforge docs-index` from the source. Do not edit by hand: `tests/test_checks_index.py` fails when this file is stale.",
        "",
        f"- {len(checks)} scan finding ids in {len(modules)} modules; {len(catalogue.untested)} are not named by any test (the ratchet in `{UNTESTED_BASELINE.as_posix()}` only lets that list shrink).",
        f"- {len(issues)} revival-audit issue ids.",
        "- *Where* is `module:function`. *Tests* lists the test modules that name the id. *Bug classes* are the `docs/BUG_CLASSES.md` rows that cite it.",
        "- `{...}` marks a computed part of an id or text; `(computed)` is a value chosen at run time.",
        "",
        "## Scan findings",
        "",
        "| Finding id | Classification | Severity | Where | Tests | Bug classes | What it means |",
        "|---|---|---|---|---|---|---|",
    ]
    for key in sorted(checks):
        check = checks[key]
        lines.append(f"| `{_cell(key)}` | {_join(check.classifications)} | {_join(check.severities)} | {_cell(', '.join(sorted(check.where)))} | {_join(catalogue.tests.get(key, []))} | {_join(catalogue.bug_classes.get(key, []))} | {_cell(check.explanation)} |")
    lines += ["", "## revival-audit issues", "", "| Issue id | Severity | Tests | What it means |", "|---|---|---|---|"]
    for key in sorted(issues):
        lines.append(f"| `{_cell(key)}` | {_join(issues[key].severities)} | {_join(catalogue.tests.get(key, []))} | {_cell(issues[key].explanation)} |")
    lines += ["", f"## Scanner helpers (`bridgeforge/{HELPER_MODULE}`)", "", "Private helpers checks reuse. Read Starsector JSON only through `_load_lenient_json_file`.", "", "| Helper | Signature | Purpose |", "|---|---|---|"]
    for name, signature, doc in _helpers((repo_root / "bridgeforge" / HELPER_MODULE).read_text(encoding="utf-8")):
        lines.append(f"| `{name}` | `{_cell(signature)}` | {_cell(doc) or '-'} |")
    return "\n".join(lines) + "\n"


def _subcommands(parser: argparse.ArgumentParser, prefix: str = "") -> list[tuple[str, str, argparse.ArgumentParser]]:
    """(path, help, parser) for every subcommand, depth first, in definition order."""
    found = []
    for action in parser._actions:  # argparse has no public accessor for subparsers
        if isinstance(action, argparse._SubParsersAction):
            helps = {choice.dest: choice.help or "" for choice in action._choices_actions}
            for name, sub in action.choices.items():
                path = f"{prefix} {name}".strip()
                found.append((path, helps.get(name, ""), sub))
                found.extend(_subcommands(sub, path))
    return found


def _argument_rows(parser: argparse.ArgumentParser) -> list[str]:
    rows = []
    for action in parser._actions:
        if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        name = ", ".join(action.option_strings) if action.option_strings else f"`{action.metavar or action.dest}`"
        if action.option_strings:
            name = f"`{name}`" + (f" {action.metavar or action.dest.upper()}" if action.nargs != 0 else "")
        notes = []
        if action.required and action.option_strings:
            notes.append("required")
        if isinstance(action, argparse._AppendAction):
            notes.append("repeatable")
        if action.nargs in ("+", "*"):
            notes.append(f"nargs {action.nargs}")
        if action.choices and not isinstance(action.choices, dict):
            notes.append("one of " + ", ".join(str(choice) for choice in action.choices))
        if action.default not in (None, False, argparse.SUPPRESS, []) and action.option_strings:
            notes.append(f"default {action.default}")
        help_text = " ".join((action.help or "").split())
        rows.append(f"| {_cell(name)} | {_cell('; '.join(notes)) or '-'} | {_cell(help_text) or '-'} |")
    return rows


def build_commands_index() -> str:
    from .cli import build_parser

    parser = build_parser()
    commands = _subcommands(parser)
    lines = [
        "# BridgeForge commands",
        "",
        "Generated by `bridgeforge docs-index` from the argument parser. Do not edit by hand: `tests/test_checks_index.py` fails when this file is stale.",
        "",
        f"{len(commands)} commands and subcommands. Run as `python -m bridgeforge <command> ...`; exit codes: 0 ok, 1 an attention status, 2 a usage or input error.",
        "",
        "| Command | What it does |",
        "|---|---|",
    ]
    lines += [f"| [`{path}`](#{path.replace(' ', '-')}) | {_cell(' '.join(help_text.split())) or '-'} |" for path, help_text, _ in commands]
    for path, help_text, sub in commands:
        lines += ["", f"## {path}", ""]
        if help_text:
            lines += [" ".join(help_text.split()), ""]
        rows = _argument_rows(sub)
        lines += ["| Argument | Notes | Help |", "|---|---|---|", *rows] if rows else ["No arguments."]
    return "\n".join(lines) + "\n"


def write_reference_docs(repo_root: Path = REPO_ROOT, *, check_only: bool = False) -> dict[str, object]:
    outputs = {repo_root / "docs" / "CHECKS.md": build_checks_index(repo_root), repo_root / "docs" / "COMMANDS.md": build_commands_index()}
    stale, written = [], []
    for target, text in outputs.items():
        current = target.read_text(encoding="utf-8").splitlines() if target.is_file() else None
        if current != text.splitlines():
            stale.append(str(target))
            if not check_only:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
                written.append(str(target))
    return {"schema_version": SCHEMA_VERSION, "mode": "DOCS_INDEX", "status": "STALE" if (stale and check_only) else "OK", "stale": stale, "written": written, "untested": gather(repo_root).untested}


def write_untested_baseline(repo_root: Path = REPO_ROOT) -> Path:
    """Record the current untested finding ids (used once to start the ratchet)."""
    path = repo_root / UNTESTED_BASELINE
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "untested": gather(repo_root).untested}, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path
