from __future__ import annotations
import re
from pathlib import Path
from bridgeforge.scan.scanner import _blank_java_comments
from .common import FileChange, FixerError, _decode, _encode, _findings_of
from .interfaces import _insert_before_class_end


# ---------------------------------------------------------------------------
# Fixer: spawned-ship-captain-personality-risk (loose scripts only; ROADMAP 34.14)
# ---------------------------------------------------------------------------

_SPAWN_THREE_ARGS = re.compile(r"\bspawnShipOrWing\s*\(")
_BF_SPAWN_CAPTAIN = (
    "\n    // BridgeForge: a ship spawned without a captain has no personality, and RC8's Ship.getPersonality() NPEs\n"
    "    // on it. RC8's ChiralFigmentStats spawns ships with createPerson() + setPersonality (ROADMAP 34.14).\n"
    "    private static com.fs.starfarer.api.characters.PersonAPI bfSpawnCaptain() {\n"
    "        com.fs.starfarer.api.characters.PersonAPI captain = com.fs.starfarer.api.Global.getSettings().createPerson();\n"
    "        captain.setPersonality(com.fs.starfarer.api.impl.campaign.ids.Personalities.STEADY);\n"
    "        return captain;\n"
    "    }\n"
)


def _fix_spawned_ship_captain(root: Path, options: dict) -> list[FileChange]:
    """spawnShipOrWing("ship", loc, facing) -> spawnShipOrWing("ship", loc, facing, 0f, bfSpawnCaptain()), the
    overload with a captain (done by hand for Traverser's turrets, 2026-10-04). The 3-argument form has no
    travel-drive burn, so 0f keeps it. A 4-argument call keeps its own burn. Only the flagged lines change;
    wings are never flagged. Jar sources need patch-jar-class and are refused."""
    from bridgeforge.scan.scanner import _call_argument_count

    lines_by_file: dict[str, set[int]] = {}
    for finding in _findings_of(root, options, "spawned-ship-captain-personality-risk"):
        if finding.file and "!" not in finding.file and not finding.file.replace("\\", "/").startswith(("jars/", "src/")):
            if any(e == "call:spawnShipOrWing" for e in finding.evidence):
                lines_by_file.setdefault(finding.file, set()).update(
                    int(e.split(":", 1)[1]) for e in finding.evidence if e.startswith("line:"))
    changes: list[FileChange] = []
    for rel, lines in sorted(lines_by_file.items()):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        blank = _blank_java_comments(text, strings=True)
        edits = []
        for match in _SPAWN_THREE_ARGS.finditer(blank):
            if text.count("\n", 0, match.start()) + 1 not in lines:
                continue
            count = _call_argument_count(blank, match.start())
            if count not in (3, 4):
                continue
            depth, close = 0, None
            for i in range(match.end() - 1, len(blank)):
                depth += {"(": 1, ")": -1}.get(blank[i], 0)
                if depth == 0:
                    close = i
                    break
            if close is not None:
                edits.append((close, (", 0f" if count == 3 else "") + ", bfSpawnCaptain()"))
        if not edits:
            continue
        out = text
        for at, insert in sorted(edits, reverse=True):
            out = out[:at] + insert + out[at:]
        if "bfSpawnCaptain() {" not in out:
            last = _blank_java_comments(out, strings=True).rstrip().rfind("}")
            out = out[:last] + _BF_SPAWN_CAPTAIN + out[last:]
        changes.append(FileChange(path=path, before=raw, after=_encode(out, had_bom)))
    if not changes:
        raise FixerError("No flagged loose-script spawnShipOrWing call could be given a captain mechanically.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: hullmod-instance-state (loose scripts only; ROADMAP 34.1)
# ---------------------------------------------------------------------------


def _fix_black_hole_type_missing_flag(root: Path, options: dict) -> list[FileChange]:
    """Add `"isBlackHole":true,` after `"isStar":true` in each flagged planets.json star type. RC8's own black_hole entry carries
    exactly this pair (checked against starsector-core/data/config/planets.json, 2026-10-11); without it 0.98a draws a plain star."""
    findings = _findings_of(root, options, "black-hole-type-missing-flag")
    types = sorted({e.split(":", 1)[1] for f in findings for e in f.evidence if e.startswith("type:")})
    path = root / "data" / "config" / "planets.json"
    if not types or not path.is_file():
        raise FixerError("No planets.json star type is flagged as a black hole without isBlackHole.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    done = 0
    for type_id in types:
        start = re.search(r"[\"']" + re.escape(type_id) + r"[\"']\s*:\s*\{", text)
        if not start:
            continue
        star = re.compile(r"(?P<indent>[ \t]*)(?P<key>[\"']isStar[\"']\s*:\s*true)(?P<comma>\s*,)?").search(text, start.end())
        if not star:
            continue
        nxt = re.search(r"^[ \t]*[\"'][\w]+[\"']\s*:\s*\{", text[start.end():], re.M)
        if nxt and star.start() > start.end() + nxt.start():
            continue  # the isStar found belongs to a later type
        newline = "\r\n" if "\r\n" in text else "\n"
        indent = star.group("indent")
        if star.group("comma"):
            insert_at = star.end()
            text = text[:insert_at] + newline + indent + "\"isBlackHole\":true," + text[insert_at:]
        else:
            text = text[:star.end("key")] + "," + newline + indent + "\"isBlackHole\":true" + text[star.end("key"):]
        done += 1
    if not done:
        raise FixerError("Could not place isBlackHole in planets.json.")
    return [FileChange(path=path, before=raw, after=_encode(text, had_bom))]


# IDE-generated `throw new UnsupportedOperationException(...)` bodies in ShipSystemStatsScript's override hooks. RC8's
# BaseShipSystemScript answers -1 / -1 / -1 / -1 / null ("no override": use the .system file), read with javap and
# starfarer.api.zip on 2026-10-11 (BaseShipSystemScript.getActiveOverride returns -1). Neutrino's two system scripts had
# ten of these; the game calls the hooks for any system that names the class.
_PLACEHOLDER_HOOKS = re.compile(
    r"(?P<head>public\s+(?P<type>float|int)\s+(?P<name>get(?:Active|In|Out|Uses|Regen)Override)\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)\s*\{)"
    r"(?P<gap>\s*)throw\s+new\s+UnsupportedOperationException\s*\([^;]*\)\s*;[^\r\n]*")


def _fix_runtime_placeholder_hooks(root: Path, options: dict) -> list[FileChange]:
    """Replace the throwing bodies of ShipSystemStatsScript's five *Override hooks with BaseShipSystemScript's "no override"
    answer (-1). Any other placeholder is not mechanical (what it should return depends on the class) and is refused. Edits
    loose scripts and the `src/` tree alike; a class compiled into a jar still needs patch-jar-class."""
    files = sorted({f.file for f in _findings_of(root, options, "runtime-placeholder-unsupported-operation")
                    if f.file and f.file.endswith(".java") and "!" not in f.file})
    changes: list[FileChange] = []
    for rel in files:
        path = root / rel
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new_text, count = _PLACEHOLDER_HOOKS.subn(
            lambda m: f"{m['head']}{m['gap']}return {'-1f' if m['type'] == 'float' else '-1'};  // BridgeForge: BaseShipSystemScript's \"no override\"", text)
        if count:
            changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("No ShipSystemStatsScript override hook throws UnsupportedOperationException; other placeholders need a person or agent.")
    return changes


def _fix_hulk_death_effect_repeats(root: Path, options: dict) -> list[FileChange]:
    """Run a hull mod's wreck effect once per ship: `if (s.isHulk())` becomes `if (s.isHulk() && bfFirstDeath(s, "<Class>_deathDone"))`
    and a static helper keeps the flag in the ship's custom data (the guard SEEKER's Organic Hull had; RC8-27). Loose sources only;
    a class compiled into a jar needs a decompile and patch-jar-class, so those are refused."""
    from bridgeforge.scan.scanner import _HULK_IF, _hulk_block_spawns

    files = sorted({f.file for f in _findings_of(root, options, "hulk-death-effect-repeats") if f.file and "!" not in f.file and f.file.endswith(".java")})
    if not files:
        raise FixerError("No loose hull mod source repeats a wreck effect (jar classes need a decompile and patch-jar-class).")
    changes: list[FileChange] = []
    for rel in files:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        key = path.stem + "_deathDone"
        edits = [m for m in _HULK_IF.finditer(text) if _hulk_block_spawns(text, m.end())]
        if not edits:
            continue
        for match in reversed(edits):
            var = match["var"]
            guarded = f'if ({var}.isHulk() && bfFirstDeath({var}, "{key}")) {{'
            text = text[:match.start()] + guarded + text[match.end():]
        helper = ("private static boolean bfFirstDeath(com.fs.starfarer.api.combat.ShipAPI ship, String key) { "
                  "if (ship.getCustomData().containsKey(key)) { return false; } ship.setCustomData(key, Boolean.TRUE); return true; }")
        text = _insert_before_class_end(text, [helper], "run the wreck effect once per ship; RC8 calls a hull mod for a wreck every frame (RC8-27)")
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    if not changes:
        raise FixerError("The flagged wreck checks no longer spawn anything; nothing to guard.")
    return changes


def _fix_hullmod_instance_state(root: Path, options: dict) -> list[FileChange]:
    """Move a hull mod's flagged instance fields into a per-ship State in ship.getCustomData()
    (`hullmod_state.port_hullmod_state`, the rewrite done by hand for SEEKER and Sylphon on 2026-10-04). Jar
    classes and jar sources need patch-jar-class, so they are refused; so is any shape the port refuses."""
    from ..hullmod_state import HullModStateError, port_hullmod_state

    fields_by_file: dict[str, list[str]] = {}
    for finding in _findings_of(root, options, "hullmod-instance-state"):
        if finding.file:
            fields_by_file.setdefault(finding.file, []).extend(
                e.split(":", 1)[1] for e in finding.evidence if e.startswith("field:"))
    loose = {rel: names for rel, names in fields_by_file.items()
             if "!" not in rel and rel.endswith(".java") and not rel.replace("\\", "/").startswith(("jars/", "src/"))}
    if not loose:
        raise FixerError("No loose hull mod script keeps per-ship instance fields (jar classes need patch-jar-class).")
    changes: list[FileChange] = []
    refused: list[str] = []
    for rel, names in sorted(loose.items()):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        try:
            new_text = port_hullmod_state(text, sorted(set(names)), path.stem)
        except HullModStateError as exc:
            refused.append(f"{rel}: {exc}")
            continue
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("Not mechanical: " + "; ".join(refused[:5]))
    return changes
