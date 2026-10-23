from __future__ import annotations
import re
from pathlib import Path
from ..scanner import CUSTOM_UI_PLUGIN_PATTERN, _blank_java_comments
from .common import FileChange, FixerError, _decode, _encode, _findings_of


# ---------------------------------------------------------------------------
# Fixer: target-interface-method-missing (loose scripts only)
# ---------------------------------------------------------------------------

# RC8 defaults, read from starfarer.api.jar with javap (2026-09-14): BaseShipSystemScript returns -1f /
# -1 / null ("no override", i.e. what a pre-0.95 script did implicitly). Fully qualified types avoid
# touching imports.
_SHIP_SYSTEM_DEFAULTS = (
    ("getActiveOverride", "public float getActiveOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1f; }"),
    ("getInOverride", "public float getInOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1f; }"),
    ("getOutOverride", "public float getOutOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1f; }"),
    ("getRegenOverride", "public float getRegenOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1f; }"),
    ("getUsesOverride", "public int getUsesOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1; }"),
    ("getDisplayNameOverride", "public String getDisplayNameOverride(com.fs.starfarer.api.plugins.ShipSystemStatsScript.State state, float effectLevel) { return null; }"),
)
# RC8 defaults for HullModEffect, read from starfarer.api.jar/BaseHullMod with javap (2026-09-14,
# 2026-09-22): showInRefitScreenModPickerFor defaults to visible; isSModEffectAPenalty defaults to
# false (an S-mod of this hullmod is a bonus, not a penalty).
_HULL_MOD_EFFECT_DEFAULTS = (
    ("showInRefitScreenModPickerFor", "public boolean showInRefitScreenModPickerFor(com.fs.starfarer.api.combat.ShipAPI ship) { return true; }"),
    ("isSModEffectAPenalty", "public boolean isSModEffectAPenalty() { return false; }"),
)


def _insert_before_class_end(text: str, members: list[str], note: str) -> str:
    end = text.rstrip().rfind("}")
    if end < 0 or not members:
        return text
    newline = "\r\n" if "\r\n" in text else "\n"
    block = newline + f"    // BridgeForge: {note}" + newline + newline.join(f"    {member}" for member in members) + newline
    return text[:end] + block + text[end:]




def _fix_target_interface_method_missing(root: Path, options: dict) -> list[FileChange]:
    """Bring loose scripts up to RC8's callback signatures (they fail to compile at load otherwise).

    - ShipSystemStatsScript: add the six *Override methods with BaseShipSystemScript's defaults.
    - OnHitEffectPlugin.onHit: insert the ApplyDamageResultAPI parameter before CombatEngineAPI.
    - HullModEffect: add showInRefitScreenModPickerFor/isSModEffectAPenalty, BaseHullMod's defaults.
    Bodies are untouched. Classes compiled into a jar need the jar rebuilt, so those are refused.
    """

    files = sorted({f.file for f in _findings_of(root, options, "target-interface-method-missing") if f.file})
    loose = [rel for rel in files if rel.startswith("data/")]
    if not loose:
        detail = f" (jar sources need a rebuild: {', '.join(files[:5])})" if files else ""
        raise FixerError(f"No loose data/ script has a missing RC8 interface method{detail}.")
    changes: list[FileChange] = []
    for rel in loose:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new = text
        if re.search(r"\bimplements\s+(?:[^{]*?\b)?ShipSystemStatsScript\b", new):
            missing = [stub for name, stub in _SHIP_SYSTEM_DEFAULTS if not re.search(rf"\b{name}\s*\(", new)]
            new = _insert_before_class_end(new, missing, "RC8 ShipSystemStatsScript overrides, BaseShipSystemScript defaults (no override)")
        if re.search(r"\bimplements\s+(?:[^{]*?\b)?OnHitEffectPlugin\b", new) and not re.search(r"\bonHit\s*\([^)]*\bApplyDamageResultAPI\b", new):
            new = re.sub(
                r"(\bonHit\s*\([^)]*?,)(\s*)((?:final\s+)?(?:[\w.]+\.)?CombatEngineAPI\s+\w+\s*\))",
                r"\1\2com.fs.starfarer.api.combat.listeners.ApplyDamageResultAPI damageResult,\2\3",
                new,
                count=1,
            )
        if re.search(r"\bimplements\s+(?:[^{]*?\b)?HullModEffect\b", new):
            missing = [stub for name, stub in _HULL_MOD_EFFECT_DEFAULTS if not re.search(rf"\b{name}\s*\(", new)]
            new = _insert_before_class_end(new, missing, "RC8 HullModEffect method(s), BaseHullMod defaults")
        if new != text:
            changes.append(FileChange(path=path, before=raw, after=_encode(new, had_bom)))
    if not changes:
        raise FixerError("The flagged loose scripts could not be rewritten mechanically; fix them by hand.")
    return changes


def _fix_missing_custom_ui_button_pressed_callback(root: Path, options: dict) -> list[FileChange]:
    """Add a no-op `buttonPressed(Object)` to CustomUIPanelPlugin blocks that lack it (P15, 2026-09-26).

    RC8's CustomUIPanelPlugin declares buttonPressed(Object) (the scanner's evidence), so an
    implementation without it fails to compile and the panel never opens. A panel with no buttons
    never receives the call, so an empty body keeps behaviour; a panel that has buttons needed a
    handler the old API didn't have, and the live test says whether it matters. Each block is found
    with the scanner's own brace-aware walk; an unbalanced block is refused. Loose data/ scripts
    only: jar sources need the jar rebuilt.
    """

    files = sorted({f.file for f in _findings_of(root, options, "missing-custom-ui-button-pressed-callback") if f.file})
    loose = [rel for rel in files if rel.startswith("data/")]
    if not loose:
        raise FixerError("No loose data/ script lacks buttonPressed(Object)" + (f" (jar sources need a rebuild: {', '.join(files[:5])})" if files else "") + ".")
    changes = []
    for rel in loose:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        inserts = []
        for match in CUSTOM_UI_PLUGIN_PATTERN.finditer(text):
            opening = match.end() - 1 if text[match.end() - 1] == "{" else text.find("{", match.end())
            depth, closing = 0, -1
            for index in range(max(opening, 0), len(text)) if opening >= 0 else ():
                depth += {"{": 1, "}": -1}.get(text[index], 0)
                if depth == 0 and text[index] == "}":
                    closing = index
                    break
            if closing < 0:
                raise FixerError(f"{path}: a CustomUIPanelPlugin block has unbalanced braces; add buttonPressed(Object) by hand.")
            if not re.search(r"\bbuttonPressed\s*\(", text[opening:closing]):
                line_start = text.rfind("\n", 0, closing) + 1
                indent = re.match(r"[ \t]*", text[line_start:]).group(0)
                inserts.append((closing, f"{indent}    // Required by the 0.98a CustomUIPanelPlugin interface; added by BridgeForge as a no-op (the old API had no button callback).\n"
                                         f"{indent}    public void buttonPressed(Object buttonId) {{}}\n{indent}"))
        new = text
        for position, snippet in sorted(inserts, reverse=True):
            before = new[:position].rstrip(" \t")
            new = before + ("" if before.endswith("\n") else "\n") + snippet + new[position:]
        changes.append(FileChange(path=path, before=raw, after=_encode(new, had_bom)))
    return changes


def _fix_rc8_signature_changed(root: Path, options: dict) -> list[FileChange]:
    """Rewrite old-form calls to RC8's exact form (bridgeforge.signature_rewrites; ROADMAP 41). A file under jars/src
    or src/ is the jar's bundled source: rebuild the jar (patch-jar-class) after this."""
    from ..signature_rewrites import rewrite

    files = sorted({f.file for f in _findings_of(root, options, "rc8-signature-changed") if f.file})
    changes = []
    for rel in files:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new, count = rewrite(text, _blank_java_comments(text, strings=True))
        if count:
            changes.append(FileChange(path=path, before=raw, after=_encode(new, had_bom)))
    if not changes:
        raise FixerError("No old-form call with an exact RC8 equivalent found.")
    return changes
