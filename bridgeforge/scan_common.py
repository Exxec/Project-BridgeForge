"""Shared scanner constants and tiny path helpers (split out of scanner.py, ROADMAP item 70 H2.2)."""
from __future__ import annotations

import re
from pathlib import Path


CLASS_MAJOR_TO_JAVA = {51: 7, 52: 8, 55: 11, 61: 17, 65: 21, 69: 25}


MAX_JAR_ENTRIES = 10_000


MAX_JAR_UNCOMPRESSED_BYTES = 256 * 1024 * 1024


MAX_JAR_COMPRESSION_RATIO = 100


LARGE_BUNDLED_JAR_BYTES = 25 * 1024 * 1024


LIBRARY_PATTERNS = {
    "LazyLib": re.compile(r"lazylib", re.I),
    "MagicLib": re.compile(r"magiclib", re.I),
    "AshLib": re.compile(r"ashlib", re.I),
    "GraphicsLib": re.compile(r"graphicslib", re.I),
    "LunaLib": re.compile(r"lunalib", re.I),
    "Nexerelin": re.compile(r"nexerelin", re.I),
    "Kotlin runtime": re.compile(r"kotlin-(stdlib|reflect)|kotlinx-coroutines", re.I),
    "Gson": re.compile(r"gson", re.I),
}


LIBRARY_PACKAGES = {
    "LazyLib": ("org.lazywizard.lazylib",),
    # MagicLib's legacy API is data.scripts.util.Magic* (MagicLib 1.5.6 ships 32 such classes); other
    # data.scripts.util classes belong to whichever mod ships them (AI-War's AIW_StringHelper, 2026-09-15).
    "MagicLib": ("org.magiclib", "data.scripts.util.Magic"),
    "Nexerelin": ("exerelin.",),
}


EXTERNAL_MOD_API_PACKAGES = {
    "Console Commands": ("org.lazywizard.console.",),
    "Industrial Evolution": ("com.fs.starfarer.api.impl.campaign.ids.IndEvo_ids", "indevo.ids."),
    "MagicLib": ("data.scripts.util.Magic",),
}


EXTERNAL_CAMPAIGN_MEMORY_PREFIXES = {
    "Nexerelin": "$nex_",
}


LEGACY_API_RULES = {
    "com.fs.starfarer.api.util.Misc.getHyperspaceTerrain": (
        "legacy-api-hyperspace-terrain",
        "A legacy Starsector utility reference was found. Confirm its replacement against the target API before changing it.",
    ),
    "sun.misc": (
        "internal-jvm-api",
        "An internal JVM API import was found; it may not be supported by the selected Java runtime.",
    ),
    "java.security.SecurityManager": (
        "security-manager",
        "SecurityManager APIs are obsolete on modern Java runtimes and require manual review.",
    ),
}


RUNTIME_PLACEHOLDER_PATTERN = re.compile(
    r"\bthrow\s+new\s+(?:java\.lang\.)?UnsupportedOperationException\s*\(", re.M
)


PERCENT_MULTIPLIER_PATTERN = re.compile(
    r"\.modifyPercent\s*\(\s*[^,]+,\s*1f\s*-\s*[A-Za-z_$][\w$]*\s*\*\s*0\.01f\s*\)"
)


HARDCODED_SYSTEM_LOOKUP_PATTERN = re.compile(r"\bgetStarSystem\s*\(\s*\"([^\"]+)\"\s*\)")


HARDCODED_ENTITY_LOOKUP_PATTERN = re.compile(r"\bgetEntityById\s*\(\s*\"([^\"]+)\"\s*\)")


CAMPAIGN_SYSTEM_CREATION_PATTERN = re.compile(r"\b(?:createStarSystem|addStarSystem)\s*\(\s*\"([^\"]+)\"")


# addPlanet/initStar take the entity id first (javap, RC8 LocationAPI/StarSystemAPI, 2026-10-04).
CAMPAIGN_ENTITY_CREATION_PATTERN = re.compile(r"\b(?:addCustomEntity|addEntity|addPlanet|initStar)\s*\(\s*\"([^\"]+)\"")


MISSION_FLEET_REFERENCE_PATTERN = re.compile(
    r"\baddToFleet\s*\(\s*FleetSide\.(?:PLAYER|ENEMY)\s*,\s*\"([^\"]+)\"\s*,\s*FleetMemberType\.(SHIP|FIGHTER_WING)"
)


CUSTOM_UI_PLUGIN_PATTERN = re.compile(r"\b(?:implements\s+CustomUIPanelPlugin|new\s+CustomUIPanelPlugin\s*\(\s*\)\s*\{)")


CUSTOM_DIALOG_DELEGATE_PATTERN = re.compile(r"\bimplements\s+CustomDialogDelegate\b")


RELEASE_BLOCKING_TODO_PATTERN = re.compile(
    r"//[^\r\n]*\b(?:TODO|FIXME)\b[^\r\n]*\b(?:remove|delete|disable)\b[^\r\n]*\b(?:final|release)\b",
    re.I,
)


ROBOT_INPUT_INJECTION_PATTERN = re.compile(r"\bnew\s+(?:java\.awt\.)?Robot\s*\(")


_INTERFACE_BASE_CLASSES = {"HullModEffect": "BaseHullMod", "ShipSystemStatsScript": "BaseShipSystemScript"}


TARGET_INTERFACE_CONTRACTS = {
    "LevelupPlugin": {
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?LevelupPlugin\b"),
        "method": re.compile(r"\bpublic\s+int\s+getBonusXPUseMultAtMaxLevel\s*\(\s*\)"),
        "signature": "int getBonusXPUseMultAtMaxLevel()",
        "suggestion": "For a settings-driven level-up curve, return (int) Global.getSettings().getFloat(\"bonusXPUseMultAtMaxLevel\").",
    },
    "OnHitEffectPlugin.onHit": {
        "interface": "OnHitEffectPlugin",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?OnHitEffectPlugin\b"),
        "method": re.compile(r"\bonHit\s*\([^)]*\bApplyDamageResultAPI\b[^)]*\)"),
        "signature": "void onHit(..., ApplyDamageResultAPI, CombatEngineAPI)",
        "suggestion": "The target callback inserts ApplyDamageResultAPI before CombatEngineAPI; preserve the existing effect body and validate it in combat.",
    },
    "AutofireAIPlugin.getTargetMissile": {
        "interface": "AutofireAIPlugin",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?AutofireAIPlugin\b"),
        "method": re.compile(r"\b(?:[\w.]+\.)?MissileAPI\s+getTargetMissile\s*\(\s*\)"),
        "signature": "MissileAPI getTargetMissile()",
        "suggestion": "Return the tracked missile target when the legacy AI has one; a null return requires combat validation.",
    },
    "ShipSystemStatsScript.getActiveOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bfloat\s+getActiveOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "float getActiveOverride(ShipAPI)",
        "suggestion": "Establish the intended active duration override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getInOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bfloat\s+getInOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "float getInOverride(ShipAPI)",
        "suggestion": "Establish the intended activation-in duration override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getOutOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bfloat\s+getOutOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "float getOutOverride(ShipAPI)",
        "suggestion": "Establish the intended activation-out duration override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getUsesOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bint\s+getUsesOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "int getUsesOverride(ShipAPI)",
        "suggestion": "Establish the intended uses override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getRegenOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bfloat\s+getRegenOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "float getRegenOverride(ShipAPI)",
        "suggestion": "Establish the intended regeneration override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getDisplayNameOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bString\s+getDisplayNameOverride\s*\(\s*(?:[\w.]+\.)?(?:ShipSystemStatsScript\.)?State\s+\w+\s*,\s*float\s+\w+\s*\)"),
        "signature": "String getDisplayNameOverride(ShipSystemStatsScript.State, float)",
        "suggestion": "Return the intended dynamic display name or the target default sentinel, then validate combat UI text.",
    },
    "HullModEffect.showInRefitScreenModPickerFor": {
        "interface": "HullModEffect",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?HullModEffect\b"),
        "method": re.compile(r"\bboolean\s+showInRefitScreenModPickerFor\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "boolean showInRefitScreenModPickerFor(ShipAPI)",
        "suggestion": "Prefer extending the target BaseHullMod where behavior permits; otherwise establish picker visibility explicitly and run the full compile for all remaining obligations.",
    },
    "HullModEffect.isSModEffectAPenalty": {
        "interface": "HullModEffect",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?HullModEffect\b"),
        "method": re.compile(r"\bboolean\s+isSModEffectAPenalty\s*\(\s*\)"),
        "signature": "boolean isSModEffectAPenalty()",
        "suggestion": "Vanilla's own BaseHullMod returns false (an S-mod of this hullmod is a bonus, not a penalty; javap-verified, 2026-09-22). Prefer extending the target BaseHullMod where behavior permits; otherwise establish this explicitly.",
    },
}


MEMORY_SELF_STORE_PATTERN = re.compile(
    r"(?:\b\w*(?:memory|mem)\w*\s*|\.getMemoryWithoutUpdate\(\)\s*)\.set\s*\(\s*[^,]+\s*,\s*this\b",
    re.I,
)


FACTION_SPECIAL_ROLE_KEYS = {"doctrine", "includeDefault", "fallback", "fallback2"}


OBSOLETE_FIGHTER_ROLE_NAMES = {"interceptor", "fighter", "bomber"}


BLACK_HOLE_HINT_PATTERN = re.compile(r"black[_\s]?hole|bhole", re.I)


SHADOW_PATH_EXTENSIONS = {".system", ".ship", ".wpn", ".variant", ".skin", ".java"}


GAME_VERSION_RC_PATTERN = re.compile(r"^\d+(?:\.\d+)*[a-zA-Z]*-RC\d+$")


# RC8 script-sandbox classloader forbids these at load time (SecurityException:
# "File access and reflection are not allowed to scripts"). java.lang.ReflectiveOperationException
# and java.io.IOException are deliberately NOT in these sets/prefixes; they load fine.
FORBIDDEN_REFLECT_PREFIX = "java/lang/reflect/"


FORBIDDEN_NIO_FILE_PREFIX = "java/nio/file/"


FORBIDDEN_IO_CLASSES = {
    "java/io/File",
    "java/io/FileInputStream",
    "java/io/FileOutputStream",
    "java/io/FileReader",
    "java/io/FileWriter",
    "java/io/RandomAccessFile",
}


FORBIDDEN_SANDBOX_SOURCE_PATTERN = re.compile(
    r"\bjava\.lang\.reflect\.[A-Za-z_$][\w$]*"
    r"|\bjava\.nio\.file\.[A-Za-z_$][\w$]*"
    r"|\bjava\.io\.(?:File|FileInputStream|FileOutputStream|FileReader|FileWriter|RandomAccessFile)\b"
)


BUNDLED_LIBRARY_PACKAGE_PREFIXES = {
    "GraphicsLib": ("org/dark/",),
    # Only lazylib: org/lazywizard/console/ is Console Commands (lw_console). The wider prefix made
    # revive declare LazyLib for ClearCommands, whose jar only calls Console Commands (2026-09-27;
    # every class in LazyLib 3.0.0's LazyLib.jar and LazyLib-Kotlin.jar sits under org/lazywizard/lazylib).
    # kotlin/ and kotlinx/ too: LazyLib ships the Kotlin runtime (mod_info "jars": jars/internal/Kotlin-Runtime.jar,
    # which holds kotlin/jvm/internal/Intrinsics; LazyLib 3.0.0, read 2026-09-27). A Kotlin mod that does not
    # declare LazyLib crashes with NoClassDefFoundError: kotlin/jvm/internal/Intrinsics (Automatic Orders, GRP-4).
    "LazyLib": ("org/lazywizard/lazylib/", "kotlin/", "kotlinx/"),
    "Console Commands": ("org/lazywizard/console/",),
    "MagicLib": ("org/magiclib/", "data/scripts/util/Magic"),
    "LunaLib": ("lunalib/",),
    "Nexerelin": ("exerelin/",),
    "JSON": ("org/json/",),
    "LWJGL": ("org/lwjgl/",),
    # CMUtils (Combat Misc Utils, id cmutils): Neutrino (tomatopaste) calls cmu/CMUtils without declaring it, a
    # NoClassDefFoundError in live GRP4-20261005c (2026-10-05).
    "CMUtils": ("cmu/",),
}


LIBRARY_DEPENDENCY_IDS = {
    "GraphicsLib": "shaderLib",
    "LazyLib": "lw_lazylib",
    "Console Commands": "lw_console",  # Console Commands 4.0.9 mod_info.json
    "MagicLib": "MagicLib",
    "LunaLib": "lunalib",
    "Nexerelin": "nexerelin",
    "CMUtils": "cmutils",  # CMUtils 0.3.2 mod_info.json
}


SETTINGS_ACCEPT_LIMIT = 25  # owner, 2026-09-27 (ROADMAP item 19 held rule)


SETTINGS_BASELINE_FILE = "SETTINGS_BASELINE.json"


DESIGN_TYPE_CSV_TARGETS = (
    ("data", "hulls", "ship_data.csv"),
    ("data", "weapons", "weapon_data.csv"),
)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _java_for_major(major: int) -> str:
    if major in CLASS_MAJOR_TO_JAVA:
        return str(CLASS_MAJOR_TO_JAVA[major])
    return f"class-file major {major}"
