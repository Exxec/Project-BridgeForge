from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .baseline import load_baseline_keys, split_by_baseline
from .build_tag import DEFAULT_LABEL, BuildTagError, build_tag
from .copy_drift import _find_mod_root
from .fixers import SUPPORTED_FINDINGS
from .models import Finding, TargetProfile
from bridgeforge.file_hash import sha256_file_or_none as _mod_info_sha256  # 96.5 A10
from bridgeforge.scan.scanner import scan_mod

# The inventory and artifact sections and the markdown live beside this module (96.5 A6).
from .dossier_render import _render_index_markdown, _render_part_markdown
from .dossier_sections import (_build_inventory, _copy_drift_artifact, _jar_audit_artifact, _log_triage_artifact,
                               _performance_artifact, _runtime_footprint_artifact, _truncate_line)

DOSSIER_VERSION = 1
DEFAULT_MAX_KB = 40.0
DEFAULT_CONTEXT_LINES = 5
MAX_EVIDENCE_ITEMS = 4
PROTECTED_OUTPUT_DIR_NAMES = {"in operation", "done"}

_CLASSIFICATION_RANK = {"MANUAL": 0, "REVIEW": 1, "UNKNOWN": 2, "SAFE": 3}
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_LINE_EVIDENCE_RE = re.compile(r"^line:(\d+)$")

# Findings that tell the reader to leave something unchanged, or that are purely informational,
# do not belong in open_questions -- they are not judgment calls for a triager to act on. Most of
# these are already excluded by the classification/severity rule below (SAFE or info-severity),
# but non-strict-json-trailing-comma is REVIEW/medium ("retain it unchanged") and needs an explicit
# id. Listed here anyway for documentation even where redundant with the general rule.
_OPEN_QUESTION_NOISE_IDS = {
    "non-strict-json-trailing-comma",
    "json-hash-comment",
    "json-slash-comment",
    "json-single-quoted-string",
    "json-unquoted-key",
    "json-bareword-value",
    "json-java-number-suffix",
}
# General rule: a SAFE-classified or info-severity finding is retain-as-is/informational by
# construction and is excluded from open_questions regardless of id.
_OPEN_QUESTION_NOISE_CLASSIFICATIONS = {"SAFE"}
_OPEN_QUESTION_NOISE_SEVERITIES = {"info"}
# When the same finding id appears in at least this many distinct files, collapse its
# open_questions lines into one summary line instead of one per file.
_OPEN_QUESTION_COLLAPSE_FILE_THRESHOLD = 3


class DossierError(ValueError):
    """Raised when a dossier cannot be built or its output would be unsafe to write."""


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def _current_build_tag(root: Path) -> dict[str, object] | None:
    """Read (never write) the current `[BF rN]` build tag by consulting build_tag's own bump logic.

    `build_tag()` never writes to disk; it always computes the *next* build number (current + 1
    when no --set is given). So the tag already on disk is simply one less than that, and "no tag
    yet" is the case where the computed build is 1 (i.e. current was 0).
    """
    try:
        computed = build_tag(root, label=DEFAULT_LABEL)
    except BuildTagError:
        return None
    build = computed.get("build")
    if not isinstance(build, int) or build <= 1:
        return None
    return {"label": DEFAULT_LABEL, "build": build - 1}



def _build_identity(root: Path, metadata: dict[str, object]) -> dict[str, object]:
    mod_info_path = root / "mod_info.json"
    return {
        "mod_root": str(root),
        "id": metadata.get("id"),
        "name": metadata.get("name"),
        "version": metadata.get("version"),
        "build_tag": _current_build_tag(root),
        "game_version": metadata.get("gameVersion") or metadata.get("game_version"),
        "dependencies": metadata.get("dependencies") or [],
        "jars": metadata.get("jars") or [],
        "total_conversion": metadata.get("totalConversion") is True,
        "mod_info_sha256": _mod_info_sha256(mod_info_path),
    }


# ---------------------------------------------------------------------------
# Findings -> entries (with context snippets), sorting, size-fitting, packing
# ---------------------------------------------------------------------------


def _extract_line(evidence: list[str]) -> int | None:
    for item in evidence:
        match = _LINE_EVIDENCE_RE.match(item)
        if match:
            return int(match.group(1))
    return None


def _extract_id_values(evidence: list[str]) -> list[str]:
    values = []
    for item in evidence:
        if ":" not in item or item.startswith("line:"):
            continue
        _key, _sep, value = item.partition(":")
        value = value.strip()
        if value:
            values.append(value)
    return values


def _snippet_for_finding(root: Path, finding: Finding, line: int | None, context_lines: int) -> dict[str, object] | None:
    if not finding.file:
        return None
    path = root / finding.file
    if not path.is_file():
        return None
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not raw_lines:
        return None
    if line is not None:
        start = max(1, line - context_lines)
        end = min(len(raw_lines), line + context_lines)
        lines = [{"line": n, "text": _truncate_line(raw_lines[n - 1])} for n in range(start, end + 1)]
        return {"start_line": start, "end_line": end, "matched_line": line, "match_kind": "line", "lines": lines}
    if path.suffix.lower() == ".csv":
        candidates = _extract_id_values(finding.evidence)
        for index, text in enumerate(raw_lines, start=1):
            if index == 1:
                continue  # header row
            if any(value and value in text for value in candidates):
                return {"start_line": index, "end_line": index, "matched_line": index, "match_kind": "csv-id", "lines": [{"line": index, "text": _truncate_line(text)}]}
    return None


def _build_finding_entries(root: Path, findings: list[Finding], context_lines: int) -> list[dict[str, object]]:
    entries = []
    for finding in findings:
        line = _extract_line(finding.evidence)
        entries.append(
            {
                "id": finding.id,
                "category": finding.category,
                "classification": finding.classification,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "file": finding.file,
                "line": line,
                "explanation": finding.explanation,
                "evidence": list(finding.evidence[:MAX_EVIDENCE_ITEMS]),
                "fixer_available": finding.id in SUPPORTED_FINDINGS,
                "snippet": _snippet_for_finding(root, finding, line, context_lines),
            }
        )
    entries.sort(
        key=lambda e: (
            _CLASSIFICATION_RANK.get(e["classification"], 99),
            _SEVERITY_RANK.get(e["severity"], 99),
            e["file"] or "",
            e["line"] if e["line"] is not None else -1,
            e["id"],
        )
    )
    return entries


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _fit_entry(entry: dict[str, object], budget_bytes: int) -> dict[str, object]:
    """Shrink one finding entry in place until it fits `budget_bytes`, marking what was trimmed.

    Nothing is dropped outright: context lines are thinned (farthest from the flagged line first),
    then the remaining line's text, then evidence, then the explanation -- each a last resort after
    the previous one is exhausted. The original snippet span is preserved once trimming starts.
    """
    snippet = entry.get("snippet")
    original_start = snippet["start_line"] if snippet else None
    original_end = snippet["end_line"] if snippet else None
    trimmed = False
    guard = 0
    while len(_json_bytes(entry)) > budget_bytes and guard < 10_000:
        guard += 1
        if snippet and len(snippet["lines"]) > 1:
            anchor = snippet.get("matched_line", snippet["lines"][len(snippet["lines"]) // 2]["line"])
            drop_index = max(range(len(snippet["lines"])), key=lambda i: abs(snippet["lines"][i]["line"] - anchor))
            del snippet["lines"][drop_index]
            snippet["start_line"] = snippet["lines"][0]["line"]
            snippet["end_line"] = snippet["lines"][-1]["line"]
            trimmed = True
            continue
        if snippet and snippet["lines"] and len(snippet["lines"][0]["text"]) > 20:
            snippet["lines"][0]["text"] = snippet["lines"][0]["text"][:20] + "…"
            trimmed = True
            continue
        if len(entry["evidence"]) > 1:
            entry["evidence"] = entry["evidence"][:1]
            trimmed = True
            continue
        if len(entry["explanation"]) > 80:
            entry["explanation"] = entry["explanation"][:80] + "…"
            trimmed = True
            continue
        break
    if trimmed and snippet is not None:
        snippet["snippet_trimmed"] = True
        snippet["original_start_line"] = original_start
        snippet["original_end_line"] = original_end
    return entry


def _part_payload(mod_id: str | None, part_number: int, total_parts: int, entries: list[dict[str, object]]) -> dict[str, object]:
    return {"dossier_version": DOSSIER_VERSION, "mod_id": mod_id, "part": part_number, "total_parts": total_parts, "findings": entries}


def _pack_entries(mod_id: str | None, entries: list[dict[str, object]], max_kb: float) -> list[list[dict[str, object]]]:
    if not entries:
        return []
    max_bytes = int(max_kb * 1024)
    wrapper_bytes = len(_json_bytes(_part_payload(mod_id, 1, 1, [])))
    entry_budget = max(200, max_bytes - wrapper_bytes - 64)
    fitted = [_fit_entry(entry, entry_budget) for entry in entries]

    parts: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    for entry in fitted:
        candidate = current + [entry]
        if current and len(_json_bytes(_part_payload(mod_id, 1, 1, candidate))) > max_bytes:
            parts.append(current)
            current = [entry]
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


# ---------------------------------------------------------------------------
# open_questions
# ---------------------------------------------------------------------------


def _short_explanation(explanation: object) -> str:
    short = str(explanation).strip().split(". ")[0]
    if len(short) > 160:
        short = short[:160] + "…"
    return short


def _is_open_question_noise(entry: dict[str, object]) -> bool:
    return (
        entry["id"] in _OPEN_QUESTION_NOISE_IDS
        or entry["classification"] in _OPEN_QUESTION_NOISE_CLASSIFICATIONS
        or entry["severity"] in _OPEN_QUESTION_NOISE_SEVERITIES
    )


def _open_questions(entries: list[dict[str, object]]) -> list[str]:
    """Build open_questions, collapsing an id repeated across many files into one summary line.

    Noise findings (see `_is_open_question_noise`) never appear here -- they stay in the parts.
    A finding id spread across >= `_OPEN_QUESTION_COLLAPSE_FILE_THRESHOLD` distinct files collapses
    to one line with a file count and a short "e.g." sample; otherwise each (id, file) gets its own
    line, same as before.
    """
    by_id: dict[str, list[dict[str, object]]] = {}
    id_order: list[str] = []
    for entry in entries:
        if entry["classification"] not in ("MANUAL", "REVIEW", "UNKNOWN") or entry["fixer_available"]:
            continue
        if _is_open_question_noise(entry):
            continue
        if entry["id"] not in by_id:
            by_id[entry["id"]] = []
            id_order.append(entry["id"])
        by_id[entry["id"]].append(entry)

    lines: list[str] = []
    for finding_id in id_order:
        group = by_id[finding_id]
        files_seen: list[str] = []
        for entry in group:
            if entry["file"] and entry["file"] not in files_seen:
                files_seen.append(entry["file"])

        if len(files_seen) >= _OPEN_QUESTION_COLLAPSE_FILE_THRESHOLD:
            short = _short_explanation(group[0]["explanation"])
            shown = files_seen[:3]
            remainder = len(files_seen) - len(shown)
            sample = ", ".join(shown)
            if remainder > 0:
                sample += f" +{remainder} more"
            lines.append(f"{finding_id} ×{len(files_seen)} files: {short} (e.g. {sample})")
            continue

        grouped: dict[str, dict[str, object]] = {}
        sub_order: list[str] = []
        for entry in group:
            key = entry["file"] or ""
            if key not in grouped:
                grouped[key] = {"file": entry["file"], "line": entry["line"], "explanation": entry["explanation"], "count": 0}
                sub_order.append(key)
            grouped[key]["count"] += 1
        for key in sub_order:
            item = grouped[key]
            location = f"{item['file']}:{item['line']}" if item["file"] and item["line"] is not None else (item["file"] or "unknown location")
            short = _short_explanation(item["explanation"])
            suffix = f" (x{item['count']})" if item["count"] > 1 else ""
            lines.append(f"{finding_id} at {location}: {short}{suffix}")
    return lines


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------


def build_dossier(
    mod_dir: Path,
    *,
    vanilla_core: Path | None = None,
    baseline: Path | None = None,
    original_jar: Path | None = None,
    rig: Path | None = None,
    log: Path | None = None,
    save: Path | None = None,
    perf: Path | None = None,
    perf_mod_prefixes: list[str] | None = None,
    discovery_dir: Path | None = None,
    max_kb: float = DEFAULT_MAX_KB,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> dict[str, object]:
    """Build a size-capped, deterministic triage dossier: an index dict plus a list of finding parts."""
    root = _find_mod_root(mod_dir)
    scan_result = scan_mod(root, TargetProfile(), vanilla_core)
    metadata = scan_result.metadata or {}

    if baseline is not None:
        baseline_keys = load_baseline_keys(baseline)
        new_findings, resolved_count = split_by_baseline(scan_result.findings, baseline_keys)
        baselined_count = len(scan_result.findings) - len(new_findings)
    else:
        new_findings = list(scan_result.findings)
        resolved_count = 0
        baselined_count = 0

    entries = _build_finding_entries(root, new_findings, context_lines)
    open_questions = _open_questions(entries)
    mod_id = metadata.get("id") if isinstance(metadata.get("id"), str) else None
    packed_parts = _pack_entries(mod_id, entries, max_kb)
    total_parts = len(packed_parts)

    part_payloads = []
    part_manifest = []
    for number, part_entries in enumerate(packed_parts, start=1):
        payload = _part_payload(mod_id, number, total_parts, part_entries)
        json_bytes = _json_bytes(payload)
        json_file = f"dossier.part-{number:02d}.json"
        markdown_file = f"dossier.part-{number:02d}.md"
        part_payloads.append(
            {
                "json_file": json_file,
                "markdown_file": markdown_file,
                "json_text": json_bytes.decode("utf-8"),
                "markdown_text": _render_part_markdown(mod_id, number, total_parts, part_entries),
                "size_bytes": len(json_bytes),
            }
        )
        part_manifest.append(
            {
                "json_file": json_file,
                "markdown_file": markdown_file,
                "size_bytes": len(json_bytes),
                "finding_count": len(part_entries),
                "classifications": sorted({e["classification"] for e in part_entries}),
                "severities": sorted({e["severity"] for e in part_entries}),
                "finding_ids": sorted({e["id"] for e in part_entries}),
                "files": sorted({e["file"] for e in part_entries if e["file"]}),
            }
        )

    inventory = _build_inventory(root, scan_result.compiled_class_names)
    identity = _build_identity(root, metadata)
    artifacts = {
        "jar_audit": _jar_audit_artifact(root, scan_result.jars, original_jar),
        "copy_drift": _copy_drift_artifact(root, rig),
        "log_triage": _log_triage_artifact(log),
        "runtime_footprint": _runtime_footprint_artifact(root, save, vanilla_core),
        "performance": _performance_artifact(perf, log, perf_mod_prefixes),
    }
    discovery_specs = {
        "architecture": ("archaeology/architecture.json", "nodes"),
        "behavior": ("behavior.json", "behaviors"),
        "risks": ("risks.json", "risks"),
        "unknowns": ("unknowns.json", "unknowns"),
        "coverage": ("coverage.json", "coverage"),
        "tests": ("tests.json", "tests"),
    }
    discovery: dict[str, object] = {}
    discovery_root = discovery_dir.expanduser().resolve() if discovery_dir is not None else None
    for name, (relative, list_key) in discovery_specs.items():
        path = discovery_root / relative if discovery_root is not None else None
        if path is None or not path.is_file():
            discovery[name] = {"status": "NOT_SUPPLIED"}
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries_for_count = payload.get(list_key, []) if isinstance(payload, dict) else []
            discovery[name] = {"status": "AVAILABLE", "path": str(path), "count": len(entries_for_count) if isinstance(entries_for_count, list) else 0}
        except (OSError, json.JSONDecodeError) as exc:
            discovery[name] = {"status": "INVALID", "path": str(path), "error": str(exc)}

    index: dict[str, object] = {
        "dossier_version": DOSSIER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity": identity,
        "inventory": inventory,
        "finding_counts": {"new": len(new_findings), "baselined": baselined_count, "resolved": resolved_count},
        "parts": part_manifest,
        "artifacts": artifacts,
        "discovery": discovery,
        "open_questions": open_questions,
    }

    # If the inventory's detail lists alone push the index over --max-kb, move them into a
    # dedicated part and leave only counts (plus a pointer) in the index.
    max_bytes = int(max_kb * 1024)
    if len(_json_bytes(index)) > max_bytes:
        detail = {"dossier_version": DOSSIER_VERSION, "mod_id": mod_id, "part": "inventory", "inventory": inventory}
        detail_json_file = "dossier.part-00-inventory.json"
        detail_markdown_file = "dossier.part-00-inventory.md"
        detail_json_bytes = _json_bytes(detail)
        detail_markdown = "\n".join([f"# Inventory detail - {mod_id or '(unknown mod)'}", "", "```json", json.dumps(inventory, indent=2, sort_keys=True), "```", ""])
        part_payloads.insert(
            0,
            {
                "json_file": detail_json_file,
                "markdown_file": detail_markdown_file,
                "json_text": detail_json_bytes.decode("utf-8"),
                "markdown_text": detail_markdown,
                "size_bytes": len(detail_json_bytes),
            },
        )
        slim_inventory = {}
        for key, value in inventory.items():
            if isinstance(value, dict):
                slim_inventory[key] = {k: v for k, v in value.items() if k not in ("ids", "factions", "top_level_packages")}
            else:
                slim_inventory[key] = value
        slim_inventory["detail_part"] = detail_json_file
        index["inventory"] = slim_inventory

    index_markdown = _render_index_markdown(index)

    return {
        "index": index,
        "index_markdown": index_markdown,
        "parts": part_payloads,
        "summary": {
            "new_finding_count": len(new_findings),
            "baselined_count": baselined_count,
            "resolved_count": resolved_count,
            "open_question_count": len(open_questions),
            "part_count": len(part_payloads),
            "part_sizes_kb": [round(part["size_bytes"] / 1024, 2) for part in part_payloads],
            "index_size_kb": round(len(_json_bytes(index)) / 1024, 2),
        },
    }


def _default_output_dir(mod_id: str | None, root: Path) -> Path:
    return Path.cwd() / "bridgeforge-dossier" / (mod_id or root.name)


def _refuse_protected_output(output_dir: Path) -> None:
    lowered = {part.strip().lower() for part in output_dir.parts}
    if lowered & PROTECTED_OUTPUT_DIR_NAMES:
        raise DossierError(f"Refusing to write a dossier under a protected directory (In operation/Done): {output_dir}")


def write_dossier(
    mod_dir: Path,
    output: Path | None = None,
    *,
    vanilla_core: Path | None = None,
    baseline: Path | None = None,
    original_jar: Path | None = None,
    rig: Path | None = None,
    log: Path | None = None,
    save: Path | None = None,
    perf: Path | None = None,
    perf_mod_prefixes: list[str] | None = None,
    discovery_dir: Path | None = None,
    max_kb: float = DEFAULT_MAX_KB,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> dict[str, object]:
    """Build a dossier and write dossier.json/.md plus any dossier.part-*.json/.md to `output`."""
    root = _find_mod_root(mod_dir)
    result = build_dossier(
        root,
        vanilla_core=vanilla_core,
        baseline=baseline,
        original_jar=original_jar,
        rig=rig,
        log=log,
        save=save,
        perf=perf,
        perf_mod_prefixes=perf_mod_prefixes,
        discovery_dir=discovery_dir,
        max_kb=max_kb,
        context_lines=context_lines,
    )
    mod_id = result["index"]["identity"].get("id")
    output_dir = Path(output).expanduser().resolve() if output is not None else _default_output_dir(mod_id, root)
    _refuse_protected_output(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stale in output_dir.glob("dossier.part-*"):
        if stale.is_file():
            stale.unlink()

    index_path = output_dir / "dossier.json"
    index_md_path = output_dir / "dossier.md"
    index_path.write_text(json.dumps(result["index"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    index_md_path.write_text(result["index_markdown"], encoding="utf-8")

    written_parts = []
    for part in result["parts"]:
        json_path = output_dir / part["json_file"]
        md_path = output_dir / part["markdown_file"]
        json_path.write_text(part["json_text"] + "\n", encoding="utf-8")
        md_path.write_text(part["markdown_text"], encoding="utf-8")
        written_parts.append({"json": json_path, "markdown": md_path, "size_bytes": part["size_bytes"]})

    return {
        "output_dir": output_dir,
        "index_json": index_path,
        "index_markdown": index_md_path,
        "parts": written_parts,
        "summary": result["summary"],
    }
