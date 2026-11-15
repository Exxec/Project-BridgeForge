"""Fixers that rewrite a mod's jar bytecode or extend forwarding classes for a newer target (ROADMAP-3 item 89, 2026-11-15)."""
from __future__ import annotations

from pathlib import Path


def _fix_jar_call_signature_changed(root: Path, options: dict) -> list:
    """jar-call-signature-changed: push the documented constant and call the target's new signature
    (bridgeforge.jar_call_rewrites). Needs `options["vanilla_core"]`: the rules are gated on the target's own API jar."""
    from . import common as _f
    from ..jar_call_rewrites import rewrite_jar

    core = options.get("vanilla_core")
    if not core:
        raise _f.FixerError("jar-call-signature-changed needs the target core (--vanilla-core): its rules are gated on it.")
    jars = sorted({f.file.split("!", 1)[0] for f in _f._findings_of(root, options, "jar-call-signature-changed") if f.file})
    changes = []
    for rel in jars:
        path = root / rel
        raw = path.read_bytes()
        new, _records = rewrite_jar(path, Path(core))
        if new is not None and new != raw:
            changes.append(_f.FileChange(path=path, before=raw, after=new))
    if not changes:
        raise _f.FixerError("No jar call with a known new signature found.")
    return changes


def _fix_forwarding_class_method_missing(root: Path, options: dict) -> list:
    """forwarding-class-method-missing: append a forward to the class's delegate field for each method the target's
    interface requires (bridgeforge.forwarding_methods). Needs `options["vanilla_core"]`. A file under jars/src or src/ is
    a jar's source: rebuild the class afterwards (patch-jar-class)."""
    from . import common as _f
    from ..forwarding_methods import add_forwards
    from ..linkage import core_index

    core = options.get("vanilla_core")
    if not core:
        raise _f.FixerError("forwarding-class-method-missing needs the target core (--vanilla-core).")
    index = core_index(str(Path(core).resolve()))
    target = Path(core).resolve().parent.name
    files = sorted({f.file for f in _f._findings_of(root, options, "forwarding-class-method-missing") if f.file})
    changes = []
    for rel in files:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _f._decode(raw)
        new, count = add_forwards(text, index, target)
        if count:
            changes.append(_f.FileChange(path=path, before=raw, after=_f._encode(new, had_bom)))
    if not changes:
        raise _f.FixerError("No forwarding class with a single delegate found to extend.")
    return changes
