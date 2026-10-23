"""Triage of `vanilla-path-shadowing` files against the reference rig the mod targets (ROADMAP item 73 D3, revised by item 75 R4).

A mod file at a vanilla data-relative path replaces RC8's file. The older install the mod was made for (its reference rig's
`starsector-core`) gives each shadow a provenance, never a verdict:

- every shadow gets a three-way view first: reference ("old vanilla") -> RC8 (what the game changed), reference -> mod (what the
  mod changed), RC8 -> mod (what the mod's file does to the current game). A report lists it in
  `<workspace>/reports/SHADOW_TRIAGE.md`; nothing else happens without a person;
- a file byte-identical to the reference rig's is provably an unchanged copy of old vanilla. That establishes where it came from,
  not that the author did not mean it to override RC8 (it can be a deliberate pin of an old behaviour). It is moved to
  `<workspace>/scratch/removed-shadow/<same path>` (the copy is the backup; `explain_proofs.kept_elsewhere` proves it) only
  after an owner approval recorded in the queue's `ESCALATION_RULINGS.jsonl` (the existing ruling store) for that mod and path,
  bound to the SHA-256 of the mod file, the reference file and the RC8 file. An approval whose hashes no longer match is
  stale and refused; a later `revoke-shadow-removal` entry ends it. Unapproved files, identical or not, are retained;
- a file that differs from the reference (the mod changed it) is never moved.

`triage` computes, `plan_changes` is the `vanilla-path-shadowing` fixer's step, `record_ruling` writes an approval or a revocation.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from datetime import date
from pathlib import Path

from bridgeforge.scan.scan_common import SHADOW_PATH_EXTENSIONS

MAX_DIFF_LINES = 15
REMOVED_SHADOW_FOLDER = "removed-shadow"
RULINGS_FILE = "ESCALATION_RULINGS.jsonl"
FINDING_ID = "vanilla-path-shadowing"
APPROVE, REVOKE = "approve-shadow-removal", "revoke-shadow-removal"


def destination_for(root: Path) -> Path:
    """`<workspace>/scratch/removed-shadow` for a workspace's `working/`, else `<root>.removed-shadow` beside it."""
    root = Path(root)
    return root.parent / "scratch" / REMOVED_SHADOW_FOLDER if root.name == "working" else root.parent / f"{root.name}.{REMOVED_SHADOW_FOLDER}"


def report_path_for(root: Path) -> Path:
    root = Path(root)
    return root.parent / "reports" / "SHADOW_TRIAGE.md" if root.name == "working" else root.parent / f"{root.name}.SHADOW_TRIAGE.md"


def rulings_path_for(root: Path) -> Path:
    """The queue's ruling store: beside the workspace folder (`<queue>/ESCALATION_RULINGS.jsonl`)."""
    root = Path(root).resolve()
    workspace = root.parent if root.name == "working" else root
    return workspace.parent / RULINGS_FILE


def mod_name_for(root: Path) -> str:
    root = Path(root).resolve()
    return root.parent.name if root.name == "working" else root.name


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _value_diff(old: Path, new: Path) -> list[str]:
    """Short readable lines: what changed from `old` to `new`."""
    if new.suffix.lower() == ".java":
        a = old.read_text(encoding="utf-8", errors="replace").splitlines()
        b = new.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = [line for line in difflib.unified_diff(a, b, "old", "new", lineterm="", n=0) if not line.startswith(("---", "+++", "@@"))]
    else:
        from .data_diff import DataDiffError, diff_data

        try:
            changes = diff_data(old, new)["changes"]
        except DataDiffError as exc:
            return [f"not comparable by value: {exc}"]
        lines = []
        for change in changes:
            label = change["path"] or "<value>"
            if change["change"] == "changed":
                lines.append(f"{label}: {json.dumps(change['a'], ensure_ascii=False)} -> {json.dumps(change['b'], ensure_ascii=False)}")
            elif change["change"] == "added":
                lines.append(f"{label}: added {json.dumps(change['b'], ensure_ascii=False)}")
            elif change["change"] == "removed":
                lines.append(f"{label}: removed {json.dumps(change['a'], ensure_ascii=False)}")
            else:
                lines.append(f"{label}: {change['change']}")
        if not lines:
            return ["same values (formatting differs)"]
    if not lines:
        return ["no difference"]
    return lines[:MAX_DIFF_LINES] + ([f"... {len(lines) - MAX_DIFF_LINES} more"] if len(lines) > MAX_DIFF_LINES else [])


def read_rulings(path: Path) -> list[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def approval_state(rulings: list[dict], mod: str, relative: str, hashes: dict[str, str]) -> str:
    """`approved`, `stale` (an approval exists but the files changed since) or `none`. The latest entry for the mod and
    path decides; an unknown hash set never matches."""
    latest = None
    for entry in rulings:
        if entry.get("finding") == FINDING_ID and entry.get("ruling") in (APPROVE, REVOKE) and entry.get("file") == relative and mod in (entry.get("mods") or []):
            latest = entry
    if latest is None or latest["ruling"] == REVOKE:
        return "none"
    return "approved" if latest.get("sha256") == hashes else "stale"


def triage(root: Path, vanilla_core: Path, reference_core: Path, rulings: list[dict] | None = None) -> dict:
    """Every shadow in root/data (mod file differs from RC8's at the same path), each with its three-way diffs, hashes and
    approval state. `kind`: `identical` (byte-identical to the reference file), `changed`, or `no-reference`."""
    root, vanilla_core, reference_core = (Path(p).expanduser().resolve() for p in (root, vanilla_core, reference_core))
    mod = mod_name_for(root)
    shadows: list[dict] = []
    data_root = root / "data"
    for path in sorted(data_root.rglob("*")) if data_root.is_dir() else []:
        relative = path.relative_to(root)
        if not path.is_file() or path.suffix.lower() not in SHADOW_PATH_EXTENSIONS or "disabled_files" in relative.parts:
            continue
        current = vanilla_core / relative
        if not current.is_file():
            continue
        try:
            if path.read_bytes() == current.read_bytes():
                continue  # identical to RC8: vanilla-file-identical-copy, not a shadow
            reference = reference_core / relative
            rel = relative.as_posix()
            entry = {"path": rel, "kind": "no-reference", "approval": "none", "hashes": {"mod": _sha(path), "rc8": _sha(current)},
                     "mod_vs_rc8": _value_diff(current, path)}
            if reference.is_file():
                entry["hashes"]["reference"] = _sha(reference)
                entry["kind"] = "identical" if entry["hashes"]["mod"] == entry["hashes"]["reference"] else "changed"
                entry["reference_vs_rc8"] = _value_diff(reference, current)
                entry["reference_vs_mod"] = _value_diff(reference, path)
            if entry["kind"] == "identical":
                entry["approval"] = approval_state(rulings or [], mod, rel, entry["hashes"])
            shadows.append(entry)
        except OSError:
            continue
    return {"mod": mod, "shadows": shadows}


def record_ruling(root: Path, vanilla_core: Path, reference_core: Path, relative: str, *, reason: str, revoke: bool = False,
                  rulings_file: Path | None = None, today: str | None = None) -> dict:
    """Append an owner approval (or a revocation) to the queue's ruling store. An approval is bound to the hashes of the mod,
    reference and RC8 files as they are now and only for a file that is byte-identical to the reference's."""
    if not reason.strip():
        raise ValueError("a shadow-removal ruling needs a reason.")
    result = triage(root, vanilla_core, reference_core)
    found = next((s for s in result["shadows"] if s["path"] == relative), None)
    if found is None:
        raise ValueError(f"{relative} is not a vanilla-path shadow in this mod.")
    if not revoke and found["kind"] != "identical":
        raise ValueError(f"{relative} is not byte-identical to the reference file ({found['kind']}); only an identical copy can be approved for removal.")
    entry = {"date": today or date.today().isoformat(), "finding": FINDING_ID, "ruling": REVOKE if revoke else APPROVE, "reason": reason.strip(),
             "mods": [result["mod"]], "file": relative, "sha256": found["hashes"]}
    path = Path(rulings_file) if rulings_file else rulings_path_for(root)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def render_report(result: dict, reference_core: Path) -> str:
    shadows = result["shadows"]
    count = {key: sum(1 for s in shadows if s["kind"] == key) for key in ("identical", "changed", "no-reference")}
    lines = ["# Vanilla path shadowing: triage against the reference rig", "",
             f"Reference core (old vanilla): `{reference_core}`", "",
             "Identity with old vanilla shows where a file came from, not that the author did not mean it to override RC8. Nothing is",
             f"moved without an approval recorded for the mod and path (`bridgeforge shadow-triage --approve`); approved files go to scratch/{REMOVED_SHADOW_FOLDER}/.",
             "", f"- Identical to the reference file: {count['identical']}", f"- Changed by the mod: {count['changed']}",
             f"- Not in the reference core: {count['no-reference']}", ""]
    for shadow in shadows:
        lines += [f"## `{shadow['path']}`", "", f"Kind: {shadow['kind']}" + (f"; approval: {shadow['approval']}" if shadow["kind"] == "identical" else ""), ""]
        sections = [("Old vanilla -> current RC8 (what the game changed)", "reference_vs_rc8"), ("Old vanilla -> mod (what the mod changed)", "reference_vs_mod"),
                    ("RC8 -> mod (what this file does to the current game)", "mod_vs_rc8")]
        for title, key in sections:
            if key in shadow:
                lines += [f"{title}:", ""] + [f"    {line}" for line in shadow[key]] + [""]
    return "\n".join(lines)


def plan_changes(root: Path, vanilla_core: Path, options: dict) -> list:
    """The `vanilla-path-shadowing` fixer's D3 step as FileChanges: the triage report, and the move of each identical file that has a
    current approval. A stale approval refuses the fix. The reference core is `options["reference_core"]`, else the registered rig
    whose version is the mod's gameVersion; with neither there is nothing to triage and nothing is returned."""
    from .fixers import FileChange, FixerError
    from .reference_rigs import reference_core_for_game_version
    from bridgeforge.scan.scan_json import _load_lenient_json_file

    root = Path(root)
    reference = options.get("reference_core")
    if not reference:
        info = _load_lenient_json_file(root / "mod_info.json") if (root / "mod_info.json").is_file() else None
        reference = reference_core_for_game_version(info.get("gameVersion") if isinstance(info, dict) else None, repo_root=options.get("repo_root"))
    if not reference:
        return []
    reference = Path(reference).expanduser().resolve()
    rulings = read_rulings(options.get("shadow_rulings") or rulings_path_for(root))
    result = triage(root, vanilla_core, reference, rulings)
    stale = [s["path"] for s in result["shadows"] if s["approval"] == "stale"]
    if stale:
        raise FixerError(f"The approval for {', '.join(stale)} is stale (the mod, reference or RC8 file changed since it was given); review the triage report and approve again.")
    destination = destination_for(root)
    changes: list = []
    for shadow in result["shadows"]:
        if shadow["approval"] != "approved":
            continue
        target = destination / shadow["path"]
        if target.exists():
            raise FixerError(f"{target} already exists; move or remove it before rerunning this fixer.")
        data = (root / shadow["path"]).read_bytes()
        changes.append(FileChange(path=target, before=b"", after=data, existed_before=False))
        changes.append(FileChange(path=root / shadow["path"], before=data, after=b"", removed=True))
    moved = {c.path.relative_to(root).as_posix() for c in changes if c.removed}
    result = {**result, "shadows": [s for s in result["shadows"] if s["path"] not in moved]}
    report = report_path_for(root)
    if result["shadows"]:
        text = render_report(result, reference).encode("utf-8")
        before = report.read_bytes() if report.is_file() else b""
        if text != before:
            changes.append(FileChange(path=report, before=before, after=text, existed_before=report.is_file()))
    return changes
