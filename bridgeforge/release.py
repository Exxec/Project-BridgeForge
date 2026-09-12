from __future__ import annotations

import json
import zipfile
from pathlib import Path

from . import build_tag as build_tag_module
from .baseline import load_baseline_keys, split_by_baseline
from .copy_drift import _collect, _find_mod_root, compare_copies
from .jar_audit import audit_jar
from .models import TargetProfile
from .scanner import _load_lenient_json_file, scan_mod

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
        return {"schema_version": 1, "mods": {}, "default": {"local_only": False, "reason": None}}
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_for_mod(policy: dict[str, object], mod_id: str | None, mod_name: str | None) -> dict[str, object]:
    mods = policy.get("mods") or {}
    needles = [needle.lower() for needle in (mod_id, mod_name) if needle]
    for key, entry in mods.items():
        if str(key).lower() in needles:
            return entry
    return policy.get("default") or {"local_only": False, "reason": None}


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
    repo_root = Path(__file__).resolve().parent.parent
    candidate = repo_root / "In operation" / DEFAULT_SAVE_CORPUS_DIRNAME / (mod_id or root.name)
    return candidate if candidate.is_dir() else None


def _save_corpus_gate(root: Path, mod_id: str | None, corpus_dir: Path | None) -> dict[str, object]:
    corpus = Path(corpus_dir).expanduser().resolve() if corpus_dir is not None else _default_corpus_dir(root, mod_id)
    if corpus is None or not corpus.is_dir():
        return {"status": "SKIPPED", "not_supplied": True}
    saves = sorted(p for p in corpus.iterdir() if p.is_dir() or p.suffix.lower() == ".xml")
    if not saves:
        return {"status": "SKIPPED", "not_supplied": True, "reason": f"{corpus} has no save entries"}

    from .save_compat import SaveCompatError, check_save_compat

    try:
        from . import save_content_compat as _content_module  # lazy: may not exist yet (P3b-E)
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
        return f"{base}-{version}"
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


def _release_note(mod_id: str | None, mod_name: str | None, gates: dict[str, object]) -> str:
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

    gates = {
        "scan": scan_gate,
        "jar_audit": jar_gate,
        "build_tag": build_gate,
        "copy_drift": drift_gate,
        "save_corpus": corpus_gate,
        "licence": licence_gate,
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
    note_path.write_text(_release_note(mod_id, mod_name, gates), encoding="utf-8")
    result["written"] = [str(release_dir), str(zip_path), str(note_path)]
    result["release_dir"] = str(release_dir)
    result["zip_path"] = str(zip_path)
    result["release_note"] = str(note_path)
    return result
