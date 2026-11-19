"""The dossier's markdown: the index page and each part (split from dossier.py, ROADMAP-3 96.5 A6)."""
from __future__ import annotations


def _render_finding_line(entry: dict[str, object]) -> list[str]:
    loc = f"{entry['file']}:{entry['line']}" if entry["file"] and entry["line"] is not None else (entry["file"] or "(no file)")
    lines = [f"### {entry['id']} [{entry['classification']}/{entry['severity']}] - {loc}", "", entry["explanation"], "", f"- fixer available: {entry['fixer_available']}", f"- evidence: {', '.join(entry['evidence']) or '(none)'}"]
    snippet = entry.get("snippet")
    if snippet:
        lines.append("")
        if snippet.get("snippet_trimmed"):
            lines.append(f"(snippet trimmed to fit size cap; original span {snippet.get('original_start_line')}-{snippet.get('original_end_line')})")
        lines.append("```")
        for row in snippet["lines"]:
            lines.append(f"{row['line']}: {row['text']}")
        lines.append("```")
    lines.append("")
    return lines


def _render_part_markdown(mod_id: str | None, part_number: int, total_parts: int, entries: list[dict[str, object]]) -> str:
    lines = [f"# Dossier findings part {part_number}/{total_parts} - {mod_id or '(unknown mod)'}", ""]
    for entry in entries:
        lines.extend(_render_finding_line(entry))
    return "\n".join(lines) + "\n"


def _stringify_dependency(dep: object) -> str:
    if isinstance(dep, dict):
        label = dep.get("name") or dep.get("id") or "?"
        version = dep.get("version")
        return f"{label} {version}" if version else str(label)
    return str(dep)


def _format_build_tag(build_tag: object) -> str | None:
    if not isinstance(build_tag, dict):
        return None
    label = build_tag.get("label")
    build = build_tag.get("build")
    if label is None or build is None:
        return None
    return f"{label} r{build}"


def _format_kv(value: object) -> str:
    """Render a dict as `key=value, key2=value2` (never a Python repr), dropping bulky id lists."""
    if not isinstance(value, dict):
        return str(value)
    parts = []
    for key, val in value.items():
        if key in ("ids", "factions", "top_level_packages"):
            continue
        if isinstance(val, dict):
            val = f"({_format_kv(val)})"
        parts.append(f"{key}={val}")
    return ", ".join(parts) if parts else "(none)"


def _render_identity_markdown(identity: dict[str, object]) -> list[str]:
    name = identity.get("name") or identity.get("id") or "(unknown mod)"
    mod_id = identity.get("id") or "unknown"
    header = f"{name} ({mod_id})"
    build = _format_build_tag(identity.get("build_tag"))
    if build:
        header += f" — build {build}"
    dependencies = identity.get("dependencies") or []
    dependency_text = ", ".join(_stringify_dependency(d) for d in dependencies) if dependencies else "(none)"
    jars = identity.get("jars") or []
    jar_text = ", ".join(str(j) for j in jars) if jars else "(none)"
    return [
        f"- {header}",
        f"- mod_root: {identity.get('mod_root')}",
        f"- version: {identity.get('version')}",
        f"- game_version: {identity.get('game_version')}",
        f"- total_conversion: {identity.get('total_conversion')}",
        f"- mod_info_sha256: {identity.get('mod_info_sha256')}",
        f"- dependencies: {dependency_text}",
        f"- jars: {jar_text}",
    ]


def _render_inventory_markdown(inventory: dict[str, object]) -> list[str]:
    lines = []
    if inventory.get("detail_part"):
        lines.append(f"(full id lists moved to {inventory['detail_part']} to keep the index within --max-kb)")
    for key, value in inventory.items():
        if key == "detail_part":
            continue
        lines.append(f"- {key}: {_format_kv(value) if isinstance(value, dict) else value}")
    return lines


def _render_parts_table(parts: list[dict[str, object]]) -> list[str]:
    lines = ["| Part | Findings | Size | Classifications | Severities |", "| --- | --- | --- | --- | --- |"]
    for part in parts:
        size_kb = round(part["size_bytes"] / 1024, 1)
        classifications = ", ".join(part["classifications"]) or "(none)"
        severities = ", ".join(part["severities"]) or "(none)"
        lines.append(f"| {part['json_file']} / {part['markdown_file']} | {part['finding_count']} | {size_kb} KB | {classifications} | {severities} |")
    return lines


def _render_jar_audit_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "jar_audit: not supplied"
    if data.get("error"):
        return f"jar_audit: error - {data['error']}"
    return (
        f"jar_audit: {data.get('status')}, matched {data.get('matched_jar')} "
        f"({data.get('rebuilt_class_count')} rebuilt / {data.get('original_class_count')} original class(es); "
        f"{data.get('removed_class_count')} removed, {data.get('changed_class_count')} changed, "
        f"{data.get('unchanged_class_count')} unchanged; "
        f"{len(data.get('bundled_library_packages') or [])} bundled package(s), "
        f"{len(data.get('unexpected_new_packages') or [])} unexpected new package(s), "
        f"{data.get('reflection_finding_count')} reflection finding(s))"
    )


def _render_copy_drift_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "copy_drift: not supplied"
    if data.get("error"):
        return f"copy_drift: error - {data['error']}"
    return (
        f"copy_drift: {data.get('status')}, {data.get('drift_count')} drifted file(s) "
        f"({len(data.get('missing_in_deployed') or [])} missing, {len(data.get('different') or [])} different, "
        f"{len(data.get('extra_in_deployed') or [])} extra)"
    )


def _render_log_triage_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "log_triage: not supplied"
    if data.get("error"):
        return f"log_triage: error - {data['error']}"
    return (
        f"log_triage: {_format_kv(data.get('counts') or {})}; "
        f"{len(data.get('top_fatal') or [])} top fatal, {len(data.get('top_mod_errors') or [])} top mod error(s)"
    )


def _render_runtime_footprint_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "runtime_footprint: not supplied"
    classes = data.get("classes") or {}
    objects = data.get("objects") or {}
    class_part = f"classes: {classes.get('status', classes.get('reason', 'unavailable'))}"
    if "referenced_class_count" in classes:
        class_part += f" ({classes['referenced_class_count']} referenced)"
    objects_part = "objects: available" if objects.get("available") else f"objects: unavailable ({objects.get('reason', 'n/a')})"
    return f"runtime_footprint: {class_part}; {objects_part}"


def _render_performance_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "performance: not supplied"
    if not data.get("available", True):
        return f"performance: unavailable ({data.get('reason')})"
    report = data.get("spw_report")
    parts = []
    if report:
        parts.append(f"{len(report.get('per_mod') or [])} mod entrie(s), startup {report.get('startup', {}).get('total_ms')} ms")
    elif data.get("spw_report_error"):
        parts.append(f"spw_report error: {data['spw_report_error']}")
    log_spam = data.get("log_spam")
    if log_spam:
        parts.append(f"{log_spam.get('total_spam_lines', 0)} spam line(s)")
    return "performance: " + ("; ".join(parts) if parts else "(no data)")


def _render_index_markdown(index: dict[str, object]) -> str:
    identity = index["identity"]
    inventory = index["inventory"]
    lines = [f"# BridgeForge dossier - {identity.get('name') or identity.get('id') or '(unknown mod)'}", ""]
    lines.append(f"Generated: {index['generated_at']}")
    lines.append(f"Dossier version: {index['dossier_version']}")
    lines.append("")
    lines.append("## Identity")
    lines.extend(_render_identity_markdown(identity))
    lines.append("")
    lines.append("## Inventory")
    lines.extend(_render_inventory_markdown(inventory))
    lines.append("")
    lines.append("## Findings")
    lines.append(f"- new: {index['finding_counts']['new']}, baselined: {index['finding_counts']['baselined']}, resolved: {index['finding_counts']['resolved']}")
    lines.append("")
    lines.append("## Parts")
    lines.extend(_render_parts_table(index["parts"]))
    lines.append("")
    lines.append("## Artifacts")
    lines.append(f"- {_render_jar_audit_line(index['artifacts']['jar_audit'])}")
    lines.append(f"- {_render_copy_drift_line(index['artifacts']['copy_drift'])}")
    lines.append(f"- {_render_log_triage_line(index['artifacts']['log_triage'])}")
    lines.append(f"- {_render_runtime_footprint_line(index['artifacts']['runtime_footprint'])}")
    lines.append(f"- {_render_performance_line(index['artifacts']['performance'])}")
    lines.append("")
    discovery = index.get("discovery") or {}
    for title, key in (
        ("Architecture", "architecture"), ("Behaviour", "behavior"),
        ("Risks", "risks"), ("Unknowns", "unknowns"),
        ("Coverage", "coverage"), ("Recommended tests", "tests"),
    ):
        lines.append(f"## {title}")
        entry = discovery.get(key, {"status": "NOT_SUPPLIED"})
        if entry.get("status") == "AVAILABLE":
            lines.append(f"- Available: `{entry['path']}` ({entry.get('count', 0)} entries)")
        else:
            lines.append(f"- {entry.get('status', 'NOT_SUPPLIED')}")
        lines.append("")
    lines.append("## Open questions")
    if index["open_questions"]:
        for question in index["open_questions"]:
            lines.append(f"- {question}")
    else:
        lines.append("(none)")
    lines.append("")
    return "\n".join(lines) + "\n"
