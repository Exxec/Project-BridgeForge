from __future__ import annotations

import json
import zipfile
from pathlib import Path

from . import build_tag as build_tag_module
from .baseline import load_baseline_keys, split_by_baseline
from .copy_drift import _collect, _find_mod_root, compare_copies
from bridgeforge.bytecode.jar_audit import audit_jar
from .models import TargetProfile
from bridgeforge.scan.scanner import _load_lenient_json_file, scan_mod
from .behavior_evaluation import check_expected_changes, evaluate_behavior_release
from .archive_intake import _normalized_member_name

"""Release pipeline (roadmap P8 + P3b-M).

`release_mod` runs every release gate read-only, and writes the packaged zip / `Done/`-style
layout / release note **only** when `apply=True` and every gate passes -- never partially, and
never as a side effect of a dry run. It never writes into `Done/` itself; the caller decides
`out_dir` (default a fresh temp-ish `release/` directory next to the mod), and moving a passed
release into `Done/` is a deliberate, separate step outside this module.
"""

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "release_policy.json"
DEFAULT_SAVE_CORPUS_DIRNAME = "save_corpus"


class ReleaseError(ValueError):
    """Raised when the mod, original jar, or baseline cannot be resolved."""


# ---------------------------------------------------------------------------
# Policy / licence gate
# ---------------------------------------------------------------------------


def _load_policy(policy_path: Path | None) -> dict[str, object]:
    path = Path(policy_path).expanduser().resolve() if policy_path is not None else DEFAULT_POLICY_PATH
    if not path.is_file():
        raise ReleaseError(f"Required release licence policy is missing: {path}")
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ReleaseError(f"Cannot read release licence policy: {path}: {exc}") from exc
    if not isinstance(policy, dict) or policy.get("schema_version", 1) != 1:
        raise ReleaseError("Release policy must be a schema-1 object")
    mods, default = policy.get("mods", {}), policy.get("default", {})
    if not isinstance(mods, dict) or not isinstance(default, dict):
        raise ReleaseError("Release policy mods/default must be objects")
    _overlay_policy_fragments(policy, path)
    for entry in [default, *mods.values()]:
        if not isinstance(entry, dict) or not isinstance(entry.get("local_only", False), bool):
            raise ReleaseError("Release policy entries must be objects with boolean local_only")
    for key, entry in mods.items():
        problem = _paths_problem(entry.get("paths"))
        if problem:
            raise ReleaseError(f"Release policy entry {key!r}: {problem}")
    return policy


def _prefix_problem(prefix: object) -> str | None:
    """Why `prefix` is not a path relative to a mod root in posix form, or None (94.G1 WP4)."""
    if not isinstance(prefix, str) or not prefix.strip("/"):
        return "a path prefix is a non-empty string"
    if "\\" in prefix or prefix.startswith("/") or ":" in prefix or ".." in prefix.split("/"):
        return f"path prefix {prefix!r} must be relative to the mod root, in posix form, without '..'"
    # Refused rather than normalized: a stored prefix that can never match would protect nothing (review 2026-11-19).
    if prefix != prefix.strip() or any(segment in ("", ".") for segment in prefix.rstrip("/").split("/")):
        return f"path prefix {prefix!r} has surrounding spaces, an empty segment or a '.' segment; write it as a/b/c"
    return None


def _paths_problem(paths: object) -> str | None:
    if paths is None:
        return None
    if not isinstance(paths, list):
        return "paths is a list"
    for item in paths:
        if not isinstance(item, dict) or not isinstance(item.get("local_only"), bool) or not str(item.get("reason") or "").strip():
            return "each path exception is an object with prefix, boolean local_only and a reason"
        problem = _prefix_problem(item.get("prefix"))
        if problem:
            return problem
    return None


# Decisions are fragments (ROADMAP-3 96.5 A7): Test1's `archive` and White_Legion's sessions both wrote release_policy.json, so
# two branches edited the same file. A decision is now one file in release_policy.d/ beside it, named after the mod: two
# machines deciding about different mods never touch the same file. `_load_policy` lays them over the file;
# `release-notes assemble` folds them in.
POLICY_FRAGMENT_DIR = "release_policy.d"
_DECISION_KEYS = ("local_only", "reason", "recorded_on", "paths")


def policy_fragments(policy_path: Path | None = None) -> list[Path]:
    folder = (Path(policy_path) if policy_path is not None else DEFAULT_POLICY_PATH).parent / POLICY_FRAGMENT_DIR
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def _matching_key(mods: dict, mod_id: str) -> str:
    return next((existing for existing in mods if str(existing).lower() == mod_id.lower()), mod_id)


def _overlay_policy_fragments(policy: dict, path: Path) -> None:
    mods = policy.setdefault("mods", {})
    for fragment in policy_fragments(path):
        try:
            data = json.loads(fragment.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise ReleaseError(f"Cannot read release decision {fragment}: {exc}") from exc
        if not isinstance(data, dict) or not str(data.get("mod") or "").strip():
            raise ReleaseError(f"Release decision {fragment} must be an object naming its mod")
        key = _matching_key(mods, str(data["mod"]))
        entry = {name: data[name] for name in _DECISION_KEYS if name in data}
        if "paths" not in data and (mods.get(key) or {}).get("paths"):
            entry["paths"] = mods[key]["paths"]  # written by a checkout older than WP4: it cannot have meant to drop them
        mods[key] = entry


def _fragment_mod(fragment: Path) -> str | None:
    """The mod a fragment file records, lower-cased, or None when there is no such file."""
    if not fragment.is_file():
        return None
    try:
        return str(json.loads(fragment.read_text(encoding="utf-8")).get("mod") or "").lower()
    except (ValueError, OSError, AttributeError):
        return ""


def assemble_policy(policy_path: Path | None = None, *, dry_run: bool = False) -> list[str]:
    """Fold the pending decision fragments into release_policy.json and delete them; the fragment names folded."""
    from .safeio import atomic_write_text

    path = Path(policy_path) if policy_path is not None else DEFAULT_POLICY_PATH
    fragments = policy_fragments(path)
    if fragments and not dry_run:
        policy = _load_policy(path)
        atomic_write_text(path, json.dumps(policy, indent=2, ensure_ascii=False) + "\n", newline="")
        for fragment in fragments:
            fragment.unlink()
    return [fragment.name for fragment in fragments]


def policy_entry(policy: dict[str, object], mod_id: str | None, mod_name: str | None) -> dict[str, object] | None:
    """The mod's own release_policy.json entry (matched by id or name, case-insensitively), or None."""
    mods = policy.get("mods") or {}
    needles = [needle.lower() for needle in (mod_id, mod_name) if needle]
    for key, entry in mods.items():
        if str(key).lower() in needles:
            return entry
    return None


def _policy_for_mod(policy: dict[str, object], mod_id: str | None, mod_name: str | None) -> dict[str, object]:
    entry = policy_entry(policy, mod_id, mod_name)
    return entry if entry is not None else (policy.get("default") or {"local_only": False, "reason": None})


def record_policy_decision(mod_id: str, *, local_only: bool, reason: str, on: str | None = None,
                           policy_path: Path | None = None, paths: list[dict] | None = None) -> dict[str, object]:
    """Record one mod's publishing decision (read by the release gate and dependency-substitutes) as a fragment,
    release_policy.d/<mod>.json beside release_policy.json (96.5 A7). An existing entry, matched case-insensitively, keeps
    its key."""
    import re
    from datetime import date

    if not mod_id.strip():
        raise ReleaseError("a mod id is required")
    if not reason or not reason.strip():
        raise ReleaseError("a reason is required: record the evidence the decision rests on")
    path = Path(policy_path).expanduser().resolve() if policy_path is not None else DEFAULT_POLICY_PATH
    mods = _load_policy(path).setdefault("mods", {})
    key = _matching_key(mods, mod_id)
    previous = mods.get(key)
    current = {"local_only": bool(local_only), "reason": reason.strip(), "recorded_on": on or date.today().isoformat()}
    kept_paths = paths if paths is not None else (previous or {}).get("paths")
    if kept_paths is not None:  # a new decision keeps the mod's path exceptions: the fragment replaces the whole entry (94.G1 WP4)
        problem = _paths_problem(kept_paths)
        if problem:
            raise ReleaseError(problem)
        current["paths"] = kept_paths
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", key).strip("._") or "mod"
    fragment = path.parent / POLICY_FRAGMENT_DIR / f"{name}.json"
    if _fragment_mod(fragment) not in (None, key.lower()):  # `a b` and `a_b` would share a_b.json (review 2026-11-19)
        import hashlib

        fragment = fragment.with_name(f"{name}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:8]}.json")
    # LF as the repository keeps it: a plain write_text gave Test1's copy CRLF (2026-11-17).
    from .safeio import atomic_write_text

    atomic_write_text(fragment, json.dumps({"mod": key, **current}, indent=2, ensure_ascii=False) + "\n", newline="")
    return {"mod": key, "previous": previous, "current": current, "file": str(fragment)}


def record_path_exception(mod_id: str, prefix: str, *, reason: str | None = None, remove: bool = False,
                          policy_path: Path | None = None) -> dict[str, object]:
    """Mark `prefix` of a mod local-only (or remove that mark), keeping its recorded decision (94.G1 WP4). The mod needs a
    recorded decision first: an exception refines a decision, it does not stand in for one."""
    problem = _prefix_problem(prefix)
    if problem:
        raise ReleaseError(problem)
    prefix = prefix.rstrip("/")
    entry = policy_entry(_load_policy(policy_path), mod_id, mod_id)
    if entry is None:
        raise ReleaseError(f"{mod_id} has no recorded decision; record one with `release-policy set` before a path exception")
    paths = [item for item in entry.get("paths") or [] if item["prefix"].rstrip("/").casefold() != prefix.casefold()]
    if not remove:
        if not reason or not reason.strip():
            raise ReleaseError("a reason is required: record the evidence the exception rests on")
        paths.append({"prefix": prefix, "local_only": True, "reason": reason.strip()})
    elif len(paths) == len(entry.get("paths") or []):
        raise ReleaseError(f"{mod_id} has no path exception {prefix!r}")
    return record_policy_decision(mod_id, local_only=bool(entry.get("local_only")), reason=str(entry.get("reason") or ""),
                                  on=entry.get("recorded_on"), policy_path=policy_path, paths=sorted(paths, key=lambda p: p["prefix"]))


# The owner's standing reason for local-only revivals (owner decision 2026-09-27).
OWNER_STANDING_REASON = ("revived for the owner's local archive (live-validated {date}); not published without the author's permission "
                         "(owner decision 2026-09-27)")


def apply_standing_licence(mod_id: str | None, name: str | None, *, live_date: str, policy_path: Path | None = None) -> bool:
    """Record the owner's standing local-only decision (2026-09-27) for a revival with no decision yet; True when one was
    written. A recorded decision, LOCAL_ONLY or RELEASABLE, is never changed. `probe-group record --archive` and, since
    ROADMAP-3 96.6, `archive` both apply it."""
    from .substitutes import revival_licence

    if not mod_id or revival_licence(mod_id, name, policy_path).get("decision") in ("LOCAL_ONLY", "RELEASABLE"):
        return False
    record_policy_decision(mod_id, local_only=True, reason=OWNER_STANDING_REASON.format(date=live_date), policy_path=policy_path)
    return True


def _licence_gate(mod_id: str | None, mod_name: str | None, policy_path: Path | None) -> dict[str, object]:
    policy = _load_policy(policy_path)
    entry = _policy_for_mod(policy, mod_id, mod_name)
    local_only = bool(entry.get("local_only"))
    return {"status": "FAIL" if local_only else "PASS", "local_only": local_only, "reason": entry.get("reason")}


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def _scan_gate(root: Path, baseline: Path, vanilla_core: Path | None):
    scan_result = scan_mod(root, TargetProfile(), vanilla_core)
    baseline_keys = load_baseline_keys(baseline)
    new_findings, resolved_count = split_by_baseline(scan_result.findings, baseline_keys)
    new_manual = [f for f in new_findings if f.classification == "MANUAL"]
    gate = {
        "status": "FAIL" if new_manual else "PASS",
        "new_finding_count": len(new_findings),
        "resolved_count": resolved_count,
        "new_manual_count": len(new_manual),
        "new_manual": [{"id": f.id, "file": f.file, "explanation": f.explanation} for f in new_manual],
    }
    return gate, scan_result


def _jar_gate(root: Path, jars: list[dict[str, object]], original: Path) -> dict[str, object]:
    if not jars:
        return {"status": "REVIEW", "reason": "mod has no loaded jar to audit against --original", "jars": []}
    results = []
    overall = "PASS"
    for jar in jars:
        jar_path = root / str(jar["path"])
        try:
            audit = audit_jar(jar_path, original)
        except ValueError as exc:
            results.append({"jar": jar["path"], "error": str(exc)})
            overall = "FAIL"
            continue
        removed = [c["class"] for c in audit["removed_classes"]]
        bundled = [p["package"] for p in audit["bundled_library_packages"]]
        unexpected = [p["package"] for p in audit["unexpected_new_packages"]]
        reflection = [f["class"] for f in audit["reflection_findings"]]
        results.append(
            {
                "jar": jar["path"],
                "status": audit["status"],
                "removed_classes": removed,
                "bundled_library_packages": bundled,
                "unexpected_new_packages": unexpected,
                "reflection_findings": reflection,
            }
        )
        if bundled or unexpected or reflection:
            overall = "FAIL"
        elif removed and overall == "PASS":
            overall = "REVIEW"
    return {"status": overall, "jars": results}


def _build_tag_gate(root: Path) -> dict[str, object]:
    try:
        computed = build_tag_module.build_tag(root, label=build_tag_module.DEFAULT_LABEL)
    except build_tag_module.BuildTagError as exc:
        return {"status": "FAIL", "reason": str(exc)}
    build = computed.get("build")
    if not isinstance(build, int) or build <= 1:
        return {"status": "FAIL", "reason": "no [BF rN] build tag present yet -- run build-tag first"}
    return {"status": "PASS", "build": build - 1}


def _copy_drift_gate(root: Path, rig: Path | None) -> dict[str, object]:
    if rig is None:
        return {"status": "SKIPPED", "not_supplied": True}
    try:
        result = compare_copies(root, rig)
    except ValueError as exc:
        return {"status": "FAIL", "error": str(exc)}
    return {"status": result["status"], "drift_count": result["drift_count"]}


def _default_corpus_dir(root: Path, mod_id: str | None) -> Path | None:
    from .paths import data_root

    candidate = data_root() / "In operation" / DEFAULT_SAVE_CORPUS_DIRNAME / (mod_id or root.name)
    return candidate if candidate.is_dir() else None


def _save_corpus_gate(root: Path, mod_id: str | None, corpus_dir: Path | None) -> dict[str, object]:
    corpus = Path(corpus_dir).expanduser().resolve() if corpus_dir is not None else _default_corpus_dir(root, mod_id)
    if corpus is None or not corpus.is_dir():
        return {"status": "SKIPPED", "not_supplied": True}
    saves = sorted(p for p in corpus.iterdir() if p.is_dir() or p.suffix.lower() == ".xml")
    if not saves:
        return {"status": "SKIPPED", "not_supplied": True, "reason": f"{corpus} has no save entries"}

    from bridgeforge.save.save_compat import SaveCompatError, check_save_compat

    try:
        from bridgeforge.save import save_content_compat as _content_module  # lazy: may not exist yet (P3b-E)
    except ImportError:
        _content_module = None

    results = []
    overall = "PASS"
    for save in saves:
        entry: dict[str, object] = {"save": str(save)}
        try:
            compat = check_save_compat(save, root)
            entry["save_compat"] = compat["status"]
            if compat["status"] == "WILL_FAIL":
                overall = "FAIL"
        except (SaveCompatError, ValueError) as exc:
            entry["save_compat"] = "ERROR"
            entry["save_compat_error"] = str(exc)
            if overall == "PASS":
                overall = "REVIEW"

        if _content_module is None:
            entry["save_content_compat"] = "UNAVAILABLE"
        else:
            fn = getattr(_content_module, "check_save_content_compat", None) or getattr(_content_module, "check_content_compat", None)
            if fn is None:
                entry["save_content_compat"] = "UNAVAILABLE"
            else:
                try:
                    content = fn(save, root)
                    status = content.get("status") if isinstance(content, dict) else None
                    entry["save_content_compat"] = status or "UNKNOWN"
                    if status == "WILL_FAIL":
                        overall = "FAIL"
                except Exception as exc:  # a lazy dependency's own bugs must never break release_mod
                    entry["save_content_compat"] = "ERROR"
                    entry["save_content_compat_error"] = str(exc)
                    if overall == "PASS":
                        overall = "REVIEW"
        results.append(entry)
    return {"status": overall, "corpus_dir": str(corpus), "saves": results}


# ---------------------------------------------------------------------------
# Packaging
# ---------------------------------------------------------------------------


def _release_basename(mod_id: str | None, version: object, root: Path) -> str:
    base = mod_id or root.name
    if isinstance(version, str) and version:
        base = f"{base}-{version}"
    if "/" in base or "\\" in base or _normalized_member_name(base) != base or len(base) > 180:
        raise ReleaseError("Release id/version must form a single portable filename component")
    return base


def _unlisted_jars(root: Path, files: dict[str, Path], metadata: dict[str, object]) -> list[str]:
    """jars/*.jar files mod_info.json doesn't load (e.g. Omega's `*_old.jar` leftovers): never shipped."""
    listed = {str(entry).replace("\\", "/").lstrip("./") for entry in metadata.get("jars", []) or [] if isinstance(entry, str)}
    return sorted(relative for relative in files if relative.startswith("jars/") and relative.endswith(".jar") and relative not in listed)


def _write_release_layout(root: Path, out_dir: Path, basename: str, exclude: list[str]) -> tuple[Path, Path]:
    files = _collect(root)  # data/jars/graphics/sounds + mod_info.json; backups/src excluded
    for relative in exclude:
        files.pop(relative, None)
    release_dir = out_dir / basename
    release_dir.mkdir(parents=True, exist_ok=True)
    for relative, path in files.items():
        dest = release_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
    zip_path = out_dir / f"{basename}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(files):
            archive.write(files[relative], arcname=relative)  # already forward-slash (Path.as_posix())
    return release_dir, zip_path


def _release_note(mod_id: str | None, mod_name: str | None, gates: dict[str, object], expected_changes: list[dict[str, object]] | None = None) -> str:
    lines = [f"# Release note: {mod_name or mod_id or '(unknown mod)'}", ""]
    build_gate = gates["build_tag"]
    if build_gate.get("build") is not None:
        lines.append(f"- Build tag: {build_tag_module.DEFAULT_LABEL} r{build_gate['build']}")
    lines.append(f"- Gate: scan -- {gates['scan']['status']} ({gates['scan']['new_finding_count']} new finding(s), {gates['scan']['new_manual_count']} MANUAL)")
    lines.append(f"- Gate: jar-audit -- {gates['jar_audit']['status']}")
    lines.append(f"- Gate: build-tag -- {build_gate['status']}")
    lines.append(f"- Gate: copy-drift -- {gates['copy_drift']['status']}")
    lines.append(f"- Gate: save-corpus -- {gates['save_corpus']['status']}")
    lines.append(f"- Gate: licence -- {gates['licence']['status']}" + (f" ({gates['licence']['reason']})" if gates["licence"].get("reason") else ""))
    lines.append(f"- Gate: expected-changes -- {gates['expected_changes']['status']}")
    lines.append(f"- Gate: behavior -- {gates['behavior']['status']}")
    approved = [item for item in (expected_changes or []) if item.get("status") == "APPROVED"]
    if approved:
        lines.extend(["", "## Changes from the original", ""])
        by_build: dict[str, list[dict[str, object]]] = {}
        for item in approved:
            by_build.setdefault(str(item.get("build")), []).append(item)
        for build in sorted(by_build):
            lines.append(f"### {build}")
            lines.append("")
            for item in sorted(by_build[build], key=lambda entry: str(entry.get("id", ""))):
                lines.append(f"- {item.get('id')}: {item.get('summary')} -- {item.get('why')}")
            lines.append("")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------


def release_mod(
    mod_dir: Path,
    *,
    original: Path,
    baseline: Path,
    out_dir: Path,
    vanilla_core: Path | None = None,
    rig: Path | None = None,
    corpus_dir: Path | None = None,
    policy_path: Path | None = None,
    behavior_diff_path: Path | None = None,
    behavior_risks_path: Path | None = None,
    behavior_unknowns_path: Path | None = None,
    expected_changes_path: Path | None = None,
    require_behavior_evidence: bool = False,
    apply: bool = False,
) -> dict[str, object]:
    """Run every release gate read-only; write the packaged release only if `apply` and all pass."""
    root = _find_mod_root(mod_dir)
    metadata = _load_lenient_json_file(root / "mod_info.json")
    metadata = metadata if isinstance(metadata, dict) else {}
    mod_id = metadata.get("id") if isinstance(metadata.get("id"), str) else None
    mod_name = metadata.get("name") if isinstance(metadata.get("name"), str) else None
    version = metadata.get("version")
    if not isinstance(version, str):
        version = None

    scan_gate, scan_result = _scan_gate(root, baseline, vanilla_core)
    jar_gate = _jar_gate(root, scan_result.jars, original)
    build_gate = _build_tag_gate(root)
    drift_gate = _copy_drift_gate(root, rig)
    corpus_gate = _save_corpus_gate(root, mod_id, corpus_dir)
    licence_gate = _licence_gate(mod_id, mod_name, policy_path)
    if behavior_diff_path is not None:
        behavior_gate = evaluate_behavior_release(behavior_diff_path, risks_path=behavior_risks_path, unknowns_path=behavior_unknowns_path)
    elif require_behavior_evidence:
        behavior_gate = {"status": "FAIL", "blocking_reasons": ["behavior-evidence-not-supplied"]}
    else:
        behavior_gate = {"status": "SKIPPED", "not_supplied": True}
    expected_entries: list[dict[str, object]] = []
    if expected_changes_path is not None:
        expected_gate = check_expected_changes(expected_changes_path)
        expected_entries = expected_gate.pop("changes")
    else:
        expected_gate = {"status": "SKIPPED", "not_supplied": True}

    gates = {
        "scan": scan_gate,
        "jar_audit": jar_gate,
        "build_tag": build_gate,
        "copy_drift": drift_gate,
        "save_corpus": corpus_gate,
        "licence": licence_gate,
        "expected_changes": expected_gate,
        "behavior": behavior_gate,
    }
    blocking_gates = [name for name, gate in gates.items() if gate["status"] == "FAIL"]
    all_clear = not blocking_gates

    result: dict[str, object] = {
        "schema_version": 1,
        "mode": "RELEASE_PIPELINE",
        "mod_dir": str(root),
        "mod_id": mod_id,
        "mod_name": mod_name,
        "version": version,
        "gates": gates,
        "blocking_gates": blocking_gates,
        "apply": apply,
        "status": "RELEASED" if (apply and all_clear) else ("BLOCKED" if blocking_gates else "DRY_RUN_READY"),
        "written": [],
        "excluded_unlisted_jars": _unlisted_jars(root, _collect(root), metadata),
    }

    if not (apply and all_clear):
        return result

    out_dir_path = Path(out_dir).expanduser().resolve()
    out_dir_path.mkdir(parents=True, exist_ok=True)
    basename = _release_basename(mod_id, version, root)
    release_dir, zip_path = _write_release_layout(root, out_dir_path, basename, result["excluded_unlisted_jars"])
    note_path = out_dir_path / f"{basename}-RELEASE_NOTE.md"
    note_path.write_text(_release_note(mod_id, mod_name, gates, expected_entries), encoding="utf-8")
    result["written"] = [str(release_dir), str(zip_path), str(note_path)]
    result["release_dir"] = str(release_dir)
    result["zip_path"] = str(zip_path)
    result["release_note"] = str(note_path)
    return result
