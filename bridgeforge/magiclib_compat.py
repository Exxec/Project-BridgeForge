from __future__ import annotations


def scan_magiclib_compat(result) -> None:
    """Read-only findings for MagicLib's documented Activators migration."""
    imports = [fact for fact in result.source_facts if fact["kind"] == "import"]
    for fact in imports:
        value = fact["value"]
        if value.startswith("activators."):
            result.add(id="magiclib-activators-package", category="magiclib-compatibility", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation="MagicLib's documented Combat Activators migration moves activators imports to org.magiclib.subsystems. This is a blocked evidence-contract candidate, not an executable rule.", file=fact["file"], evidence=[value, "candidate: org.magiclib.subsystems"])
        if value.endswith(".CombatActivator"):
            result.add(id="magiclib-combat-activator", category="magiclib-compatibility", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation="MagicLib documents CombatActivator → MagicSubsystem. Verify lifecycle semantics and compile against the selected MagicLib before any review-gated migration.", file=fact["file"], evidence=[value, "candidate: MagicSubsystem"])
        if value.endswith(".ActivatorManager"):
            result.add(id="magiclib-activator-manager", category="magiclib-compatibility", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation="MagicLib documents ActivatorManager → MagicSubsystemsManager. This remains a blocked evidence-contract candidate.", file=fact["file"], evidence=[value, "candidate: MagicSubsystemsManager"])
    types = {}
    for fact in result.source_facts:
        if fact["kind"] == "variable_declaration" and "\x1f" in fact["value"]:
            declared, name = fact["value"].split("\x1f", 1); types[(fact["file"], name)] = declared
        if fact["kind"] == "method_invocation" and fact["value"].endswith(".advanceEveryFrame"):
            result.add(id="magiclib-activator-lifecycle", category="magiclib-compatibility", severity="high", classification="MANUAL", confidence="HIGH", explanation="MagicLib documents that advanceEveryFrame() and advance(float) became advance(float, boolean isPaused). Moving logic changes pause semantics, so no source rewrite is inferred.", file=fact["file"], evidence=[fact["value"]])
    for fact in result.source_facts:
        if fact["kind"] == "method_invocation" and "." in fact["value"]:
            receiver, method = fact["value"].rsplit(".", 1)
            if method == "addActivator" and types.get((fact["file"], receiver)) in {"ActivatorManager", "activators.ActivatorManager"}:
                result.add(id="magiclib-add-activator", category="magiclib-compatibility", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation="AST/type evidence identifies an ActivatorManager receiver. MagicLib documents addActivator → addSubsystemToShip; this is a blocked evidence-contract candidate only.", file=fact["file"], evidence=[fact["value"], "candidate: addSubsystemToShip"])
