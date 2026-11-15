"""Jar calls whose target gained one trailing parameter, rewritten in the bytecode (2026-11-15, 0.98.5a-RC3).

`target-impact` RC8 -> 0.98.5a-RC3 found `new ShipAIConfig()` in 24 jars, several with no source to recompile. The
source rule (`signature_rewrites.TARGET_RULES`) writes `new ShipAIConfig(null)`; this does the same to compiled
classes: push the constant right before the call and call the new descriptor (`bytecode.append_constant_argument`,
ASM). Each rule is gated on the target core's own API jar, exactly as its source twin, and carries the same evidence:

- `ShipAIConfig.<init>()V` -> `<init>(Lcom/fs/starfarer/api/combat/ShipAPI;)V` with null: RC8's no-argument constructor
  set the defaults the new one keeps for a null ship (both versions' `starfarer.api.zip`).
- `ShipAPI.isBeingIgnored()Z` -> `isBeingIgnored(Z)Z` with false: RC8's javadoc "ignored by enemy ships"; 0.98.5a
  returns false for byAlly=true.

The jar is rebuilt entry by entry with each entry's original ZipInfo, as `patch-jar-class` does (live-proven); only the
rewritten classes' bytes change. Entries are read with `zipsafe.read_limited`.
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .signature_rewrites import _PORTRAIT_OLD
from .zipsafe import MAX_CLASS_BYTES, read_limited

_API = "com/fs/starfarer/api/"
INVOKESPECIAL, INVOKESTATIC, INVOKEINTERFACE = 183, 184, 185


@dataclass(frozen=True)
class CallRule:
    name: str
    owner: str
    member: str
    descriptor: str
    opcode: int
    new_descriptor: str
    constant: str  # "null" or "false"

    @property
    def gate(self) -> tuple[str, tuple[str, str], tuple[str, str]]:
        return (self.owner, (self.member, self.descriptor), (self.member, self.new_descriptor))

    def label(self) -> str:
        return f"{self.owner.replace('/', '.')}.{self.member}{self.descriptor} -> {self.new_descriptor} ({self.constant})"


RULES = (
    CallRule("ShipAIConfig", _API + "combat/ShipAIConfig", "<init>", "()V", INVOKESPECIAL, f"(L{_API}combat/ShipAPI;)V", "null"),
    CallRule("isBeingIgnored", _API + "combat/ShipAPI", "isBeingIgnored", "()Z", INVOKEINTERFACE, "(Z)Z", "false"),
    # null is RC8's behaviour: 0.98.5a picks with the Random only when one is given (signature_rewrites, item 91).
    CallRule("pickPortraitPreferNonDuplicate", _API + "impl/campaign/events/OfficerManagerEvent", "pickPortraitPreferNonDuplicate",
             _PORTRAIT_OLD, INVOKESTATIC, _PORTRAIT_OLD.replace(";)", ";Ljava/util/Random;)"), "null"),
)


def active_rules(vanilla_core: Path | None) -> list[CallRule]:
    from .signature_rewrites import _gate_open

    return [rule for rule in RULES if _gate_open(rule.gate, vanilla_core)]


def matching_rule(owner: str, member: str, descriptor: str, vanilla_core: Path | None) -> CallRule | None:
    """The active rule for one unresolved reference (as `linkage` reports it), or None."""
    return next((r for r in active_rules(vanilla_core) if (r.owner, r.member, r.descriptor) == (owner, member, descriptor)), None)


def _class_entries(jar: Path, rules: list[CallRule]) -> dict[str, list[CallRule]]:
    """{jar entry: rules whose call it makes}, from the constant pool (no JVM)."""
    from .linkage import parse_class

    found: dict[str, list[CallRule]] = {}
    with zipfile.ZipFile(jar) as archive:
        for info in archive.infolist():
            if not info.filename.endswith(".class"):
                continue
            parsed = parse_class(read_limited(archive, info, MAX_CLASS_BYTES))
            if parsed is None:
                continue
            hits = [r for r in rules if ("method", r.owner, r.member, r.descriptor) in parsed.refs]
            if hits:
                found[info.filename] = hits
    return found


def rewrite_jar(jar: Path, vanilla_core: Path | None) -> tuple[bytes | None, list[dict]]:
    """(new jar bytes or None when nothing applies, one record per rewritten class and rule)."""
    from .bytecode.bytecode import append_constant_argument, inspect_bytecode

    rules = active_rules(vanilla_core)
    if not rules:
        return None, []
    targets = _class_entries(jar, rules)
    if not targets:
        return None, []
    replaced: dict[str, bytes] = {}
    records: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="bf-jar-calls-") as directory, zipfile.ZipFile(jar) as archive:
        work = Path(directory)
        for index, (entry, hits) in enumerate(sorted(targets.items())):
            current = work / f"{index}-0.class"
            current.write_bytes(read_limited(archive, archive.getinfo(entry), MAX_CLASS_BYTES))
            for step, rule in enumerate(hits, 1):
                references = inspect_bytecode([current])["classes"][0]["references"]
                count = sum(1 for ref in references if ref.get("kind") == "method" and ref.get("owner") == rule.owner
                            and ref.get("name") == rule.member and ref.get("descriptor") == rule.descriptor and ref.get("opcode") == rule.opcode)
                if not count:
                    continue  # referenced through another opcode (invokevirtual on a subclass): not this rule's shape
                following = work / f"{index}-{step}.class"
                done = append_constant_argument(current, following, rule.owner, rule.member, rule.descriptor, rule.opcode,
                                                 rule.new_descriptor, rule.constant, count)
                records.append({"class": entry, "rule": rule.name, "calls": done, "change": rule.label()})
                current = following
            if current.name != f"{index}-0.class":
                replaced[entry] = current.read_bytes()
        if not replaced:
            return None, []
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
            for info in archive.infolist():
                target.writestr(info, replaced.get(info.filename) or read_limited(archive, info))
    return buffer.getvalue(), records
