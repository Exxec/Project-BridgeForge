from __future__ import annotations

from .models import TargetProfile
from .scanner import scan_mod


def suggest_integration_scenarios(mod_directory, target: TargetProfile) -> dict:
    result = scan_mod(mod_directory, target)
    suggestions = []
    direct = result.migration_context.get("dependency_compatibility", {}).get("direct_api_dependencies", [])
    for item in direct:
        dependency = str(item["dependency"])
        suggestions.append({"scenario": "campaign-load-without-optional-dependency", "dependency": dependency, "classification": "REVIEW", "reason": "Direct optional-mod API imports were observed. Verify the mod's documented optional-integration behavior with the dependency absent."})
    if any(finding.id == "external-campaign-memory-key" for finding in result.findings):
        suggestions.append({"scenario": "campaign-load-with-integration-disabled", "dependency": "Nexerelin", "classification": "REVIEW", "reason": "External campaign memory state was read directly; verify null-safe behavior with the integration unavailable."})
    if any(finding.id == "campaign-ui-robot-input-injection" for finding in result.findings):
        suggestions.append({"scenario": "custom-ui-interaction", "classification": "REVIEW", "reason": "Robot input injection was observed; exercise the affected dialog/UI controls under an explicit staged runtime profile."})
    return {"schema_version": 1, "mode": "READ_ONLY_RUNTIME_SCENARIO_SUGGESTIONS", "mod": result.input_path.name, "suggestions": suggestions, "limitation": "Suggestions are static review prompts. They do not execute the game or establish runtime compatibility."}
