"""94.G1 WP3 (GR-4): the cross-repository check. Each sister repository's genome entry against BridgeForge's section 12, and its
gene contract pin against the contract WP2 writes.

Section 12 of docs/FEATURE_GENOME_ROADMAP.md is a table: repository, phases, entry (a GitHub link to the roadmap file that
carries the entry) and pull request. For each row:
- the entry file must cite every phase the row lists, and no 94.Gn that ROADMAP-3 lacks ("every genome entry in a sister
  roadmap names an existing 94.Gn"); other existing phases it mentions (the track's range, a neighbour) are noted only;
- section 12 names every entry: each row must link a readable entry file;
- it must cite GD-2, GR-1 and GR-4 and link docs/FEATURE_GENOME_ROADMAP.md, as section 12 says each entry was checked to;
- pin drift: a sister pins the contract by writing CONTRACT.json's SHA-256 to `PIN_PATH` in its repository. No pin is
  reported, not failed: D3 (owner 2026-11-17) adds the conformance test when the sister's phase starts. A pin that differs
  from `bridgeforge gene contract`'s is drift.

The checks work on text; `github_reader` (through `gh api`) and `clone_reader` (a local checkout) only fetch it.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from .trace import id_pattern

PIN_PATH = "bridgeforge-pins/gene-contract.sha256"
GENOME_DOC = "docs/FEATURE_GENOME_ROADMAP.md"
REQUIRED_TOKENS = ("GD-2", "GR-1", "GR-4")
PHASE = re.compile(r"(?<![\w.])94\.G\d+(?![\w]|\.\d)")
ENTRY_LINK = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/blob/([\w.-]+)/([^)#\s]+)")
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")

Reader = Callable[[str, str, str, str], "str | None"]  # (owner, repo, ref, path) -> text, or None when absent


def section12(doc_text: str) -> list[dict]:
    """The rows of section 12: repository, listed phases and the entry file's owner, repo, ref and path."""
    lines = doc_text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("## 12.")), None)
    if start is None:
        return []
    rows = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Repository"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        link = ENTRY_LINK.search(cells[2])
        rows.append({"repository": cells[0], "phases": sorted(set(PHASE.findall(cells[1]))),
                     "owner": link.group(1) if link else None, "repo": link.group(2) if link else None,
                     "ref": link.group(3) if link else None, "path": link.group(4) if link else None})
    return rows


def known_phases(roadmap_text: str) -> set[str]:
    """The 94.Gn items ROADMAP-3 defines."""
    return set(re.findall(r"^- (94\.G\d+) ", roadmap_text, re.MULTILINE))


def check_entry(row: dict, entry_text: str | None, known: set[str], pin_text: str | None, current_pin: str) -> dict:
    """Problems (fail the check) and notes (reported) for one sister repository."""
    problems, notes = [], []
    if row.get("path") is None:
        return {"repository": row["repository"], "problems": ["section 12 gives no GitHub link to the entry"], "notes": []}
    if entry_text is None:
        return {"repository": row["repository"], "problems": [f"entry file {row['path']} could not be read"], "notes": []}
    cited = set(PHASE.findall(entry_text))
    for phase in sorted(cited - known):
        problems.append(f"cites {phase}, which ROADMAP-3 does not define")
    for phase in sorted(set(row["phases"]) - cited):
        problems.append(f"does not cite {phase}, which section 12 lists for it")
    others = sorted((cited & known) - set(row["phases"]))
    if others:  # the track's range ("94.G1-94.G7") or a neighbouring phase named in prose: reported, not a failure
        notes.append(f"also mentions {', '.join(others)} (not its phases in section 12)")
    for token in REQUIRED_TOKENS:
        if not id_pattern(token).search(entry_text):
            problems.append(f"does not cite {token}")
    if "FEATURE_GENOME_ROADMAP" not in entry_text:
        problems.append(f"does not link {GENOME_DOC}")
    pinned = HEX64.search(pin_text or "")
    if pin_text is None:
        notes.append(f"no gene contract pin at {PIN_PATH} (D3: added when the sister's phase starts)")
    elif not pinned:
        problems.append(f"{PIN_PATH} holds no SHA-256")
    elif pinned.group(0) != current_pin:
        problems.append(f"pin drift: {PIN_PATH} pins {pinned.group(0)[:16]}..., the contract is {current_pin[:16]}... "
                        "(update the sister's copy of docs/contracts/gene/ and its pin)")
    else:
        notes.append("gene contract pin current")
    return {"repository": row["repository"], "entry": f"{row['owner']}/{row['repo']}@{row['ref']}:{row['path']}",
            "phases": row["phases"], "cited": sorted(cited), "problems": problems, "notes": notes}


def check_sisters(doc_text: str, roadmap_text: str, read: Reader, current_pin: str) -> dict:
    rows = section12(doc_text)
    known = known_phases(roadmap_text)
    results = []
    for row in rows:
        entry = read(row["owner"], row["repo"], row["ref"], row["path"]) if row.get("path") else None
        pin = read(row["owner"], row["repo"], row["ref"], PIN_PATH) if row.get("path") else None
        results.append(check_entry(row, entry, known, pin, current_pin))
    return {"rows": len(rows), "known_phases": sorted(known), "current_pin": current_pin, "results": results,
            "ok": bool(rows) and not any(r["problems"] for r in results)}


def github_reader(owner: str, repo: str, ref: str, path: str) -> str | None:
    """A file's text from GitHub through `gh api` (the user's own authentication); None when the file is absent."""
    result = subprocess.run(["gh", "api", f"repos/{owner}/{repo}/contents/{path}?ref={ref}",
                             "-H", "Accept: application/vnd.github.raw"], capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    if result.returncode != 0:
        if "404" in result.stderr or "Not Found" in result.stderr:
            return None
        raise RuntimeError(f"gh api {owner}/{repo}:{path} failed: {result.stderr.strip()[:200]}")
    return result.stdout


def clone_reader(clones: dict[str, Path]) -> Reader:
    """Read from local checkouts, keyed by repository name; a repository without a clone falls back to None (unread)."""
    def read(owner: str, repo: str, ref: str, path: str) -> str | None:
        root = clones.get(repo)
        if root is None:
            return None
        target = Path(root) / path
        return target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
    return read


def render(result: dict) -> str:
    lines = [f"{result['rows']} sister repositories in section 12; 94.G phases defined: {', '.join(result['known_phases'])}; "
             f"contract pin {result['current_pin'][:16]}..."]
    for r in result["results"]:
        state = "FAIL" if r["problems"] else "OK"
        lines.append(f"  {state:<4} {r['repository']}: {r.get('entry', '')}")
        lines += [f"         problem: {p}" for p in r["problems"]]
        lines += [f"         note: {n}" for n in r["notes"]]
    return "\n".join(lines)
