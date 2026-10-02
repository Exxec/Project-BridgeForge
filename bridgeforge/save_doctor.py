"""`bridgeforge save-doctor`: why a save will not load, in one read-only pass (Salvor groundwork, 2026-10-02).

Salvor's first stage (docs/SAVE_TOOL_PROPOSAL.md) is diagnosis, and BridgeForge already has the pieces as separate
commands that each check one save against one mod. A player's question is different: "why does this save not load
with what I have installed?" This checks one save against a whole mods folder at once and reports, per problem
class, what it found and how recoverable that class usually is:

- MOD_MISSING: a mod enabled in the save is not installed (the commonest "corrupt" save). Reinstalling it is the fix;
  otherwise its content must be removed from a copy (Salvor stage 2).
- CLASS_UNRESOLVED: a class the save serializes is in no installed mod's jars nor the game's, and its package belongs
  to no installed mod: XStream will fail to load it. Same remedy.
- VERSION_CHANGED: an installed mod's version differs from the one the save was made with; usually fine, the usual
  suspect when it is not.
- NON_FINITE: a NaN or Infinity number in the save (a mod bug wrote it; RingBand orbits are the known case).
- TRUNCATED: campaign.xml does not end with its root element's closing tag (a crash or full disk mid-save). Not
  recoverable from the file; look for an older save.

Never writes anything. Every verdict is evidence for a person (or later Salvor), not a repair.
"""
from __future__ import annotations

import re
from pathlib import Path

from .save_compat import ModClassIndex, SaveCompatError, _package_of, _scan_save_tokens
from .save_reader import campaign_xml_path, parse_descriptor
from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1
RECOVERY = {
    "TRUNCATED": "low: the file is incomplete; use an older save or a backup",
    "MOD_MISSING": "high: reinstall the mod, or remove its content from a copy (Salvor stage 2)",
    "CLASS_UNRESOLVED": "high: reinstall the mod that provides it, or remove those entries from a copy",
    "NON_FINITE": "high for the file (reset the value on a copy); fix the mod bug that wrote it too",
    "VERSION_CHANGED": "informational: check this mod first if the save fails",
}
_NON_FINITE = re.compile(r">\s*(-?Infinity|NaN)\s*<")
_JAVA_KEYWORDS = frozenset(
    "abstract assert boolean break byte case catch char class const continue default do double else enum extends final "
    "finally float for goto if implements import instanceof int interface long native new null package private "
    "protected public return short static strictfp super switch synchronized this throw throws transient try void "
    "volatile while".split())


def _installed(mods_dir: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for info_path in sorted(Path(mods_dir).glob("*/mod_info.json")):
        info = _load_lenient_json_file(info_path) or {}
        if isinstance(info, dict) and info.get("id"):
            found[str(info["id"])] = {"folder": info_path.parent, "version": str(info.get("version") or ""), "name": str(info.get("name") or "")}
    return found


def _truncated(campaign_xml: Path) -> bool:
    with campaign_xml.open("rb") as handle:
        head = handle.read(4096).decode("utf-8", errors="replace")
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 4096))
        tail = handle.read().decode("utf-8", errors="replace").rstrip()
    root = re.search(r"<([A-Za-z_][\w.\-]*)[\s>]", re.sub(r"<\?xml[^>]*\?>", "", head, count=1))
    return not root or not tail.endswith(f"</{root.group(1)}>")


def diagnose(save: Path, mods_dir: Path, vanilla_core: Path | None = None) -> dict:
    campaign_xml = campaign_xml_path(save)
    descriptor = parse_descriptor(save)
    installed = _installed(mods_dir)
    problems: list[dict] = []

    enabled = descriptor.get("enabled_mods") or []
    for mod in enabled:
        mod_id = str(mod.get("id") or "")
        if mod_id not in installed:
            problems.append({"class": "MOD_MISSING", "mod": mod_id, "name": mod.get("name"), "version": mod.get("version")})
        elif installed[mod_id]["version"] != str(mod.get("version") or ""):
            problems.append({"class": "VERSION_CHANGED", "mod": mod_id, "save_version": mod.get("version"),
                             "installed_version": installed[mod_id]["version"]})

    truncated = _truncated(campaign_xml)
    if truncated:
        problems.append({"class": "TRUNCATED", "file": str(campaign_xml)})

    indexes = []
    for mod in enabled:
        entry = installed.get(str(mod.get("id") or ""))
        if entry:
            try:
                indexes.append(ModClassIndex(entry["folder"]))
            except SaveCompatError:
                pass
    vanilla = None
    if vanilla_core is not None:
        try:
            vanilla = ModClassIndex(Path(vanilla_core))
        except SaveCompatError:
            vanilla = None
    unresolved: dict[str, dict] = {}
    non_finite = 0
    if not truncated:
        for token, _is_class_attr, sample_path in _scan_save_tokens(campaign_xml):
            if "." not in token and "_-" not in token:
                continue  # bare names are XStream aliases or fields; only dotted class names are judged
            if not re.match(r"[a-z]", token):
                continue  # `WSR.V`: a dotted XStream alias the game registers (no WSR class exists), not a package
            if token.split(".", 1)[0] in _JAVA_KEYWORDS:
                continue  # `if.new`, `super.Object`: the game's obfuscator names classes and fields with keywords
            if any(index.resolve(token) for index in indexes) or (vanilla is not None and vanilla.resolve(token)):
                continue
            package = _package_of(token.replace("_-", "$"))
            if any(index.owns_package(package) for index in indexes) or (vanilla is not None and vanilla.owns_package(package)):
                continue  # a package someone installed owns: not this check's question (save-compat's)
            if package.startswith(("java.", "javax.", "com.fs.", "org.lwjgl.", "org.json.")) or not package:
                continue
            item = unresolved.setdefault(package, {"occurrences": 0, "examples": set(), "classes": set(), "sample_path": sample_path})
            item["occurrences"] += 1
            item["classes"].add(token)
            if len(item["examples"]) < 3:
                item["examples"].add(token)
        with campaign_xml.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if _NON_FINITE.search(line):
                    non_finite += 1
    for package, item in sorted(unresolved.items(), key=lambda kv: -kv[1]["occurrences"]):
        problems.append({"class": "CLASS_UNRESOLVED", "package": package, "occurrences": item["occurrences"],
                         "examples": sorted(item["examples"]), "classes": sorted(item["classes"]), "sample_path": item["sample_path"]})
    if non_finite:
        problems.append({"class": "NON_FINITE", "lines": non_finite})

    blocking = [p for p in problems if p["class"] in ("TRUNCATED", "MOD_MISSING", "CLASS_UNRESOLVED", "NON_FINITE")]
    verdict = "TRUNCATED" if truncated else ("WILL_LIKELY_FAIL" if blocking else "NO_KNOWN_PROBLEM")
    return {"schema_version": SCHEMA_VERSION, "mode": "READ_ONLY_SAVE_DOCTOR", "save": str(descriptor.get("save_dir")),
            "character": descriptor.get("character_name"), "game_version": descriptor.get("game_version"),
            "save_date": descriptor.get("save_date"), "mods_dir": str(mods_dir), "enabled_mods": len(enabled),
            "verdict": verdict, "problems": problems, "recovery": {p["class"]: RECOVERY[p["class"]] for p in problems},
            "note": "Read-only. A verdict is evidence, not a repair; Salvor's fixes would only ever write a copy."}
