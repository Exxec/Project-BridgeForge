"""`env-check`: read a launcher bat and its vmparams / @argfiles and report what the launch really loads (ROADMAP item 63).

Why: the AoTD Toolbox Scheduler Fork needs the StarsectorPrepatcher javaagent, which must be the last `-javaagent`.
An earlier plan said the owner's launch had no agent because only `Miko_Rouge.bat` was read and not the `@Miko_Simple.txt`
argument file it passes to java (docs/AOTD_COMPAT_PLAN.md, correction 2026-10-10). This command follows `@argfiles`.

Read-only. Reports java version, javaagents in order, whether Prepatcher is last, heap, and which enabled mods need
Prepatcher while the launch lacks it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bridgeforge.bytecode.java_matrix import PREPATCHER_MARKER, _major

PREPATCHER_VALIDATED_MAJORS = (17, 27)  # StarsectorPrepatcher 0.18.4 docs/COMPATIBILITY.md; Java 28 is owner-reported only
PREPATCHER_NEEDERS = frozenset({"starsector_prepatcher", "aotd_theory_of_toolbox"})
_TOKEN = re.compile(r'"[^"]*"|\S+')
_DIR_VARS = ("%~dp0", "%RT%")
_HEAP = re.compile(r"-Xmx(\d+)([kKmMgG]?)")


def _tokens(line: str) -> list[str]:
    return [t.strip('"') for t in _TOKEN.findall(line)]


def _join_continuations(text: str) -> list[str]:
    out, pending = [], ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith("^"):
            pending += line[:-1] + " "
            continue
        out.append(pending + line)
        pending = ""
    if pending:
        out.append(pending)
    return out


def _resolve(name: str, bat_dir: Path) -> Path | None:
    for var in _DIR_VARS:
        name = name.replace(var, str(bat_dir) + "\\")
    candidate = Path(name.replace("\\", "/"))
    options = [candidate] if candidate.is_absolute() else [bat_dir / candidate, bat_dir / "starsector-core" / candidate, bat_dir.parent / candidate]
    return next((p for p in options if p.is_file()), None)


def _argfile_tokens(path: Path, bat_dir: Path, seen: set[Path], files: list[str]) -> list[str]:
    path = path.resolve()
    if path in seen:
        return []
    seen.add(path)
    files.append(str(path))
    out: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("#"):
            continue
        for token in _tokens(line):
            out.extend(_expand(token, bat_dir, seen, files))
    return out


def _expand(token: str, bat_dir: Path, seen: set[Path], files: list[str]) -> list[str]:
    if token.startswith("@") and len(token) > 1:
        target = _resolve(token[1:], bat_dir)
        return _argfile_tokens(target, bat_dir, seen, files) if target else [token]
    return [token]


def _java_home_info(java_token: str) -> tuple[int | None, str]:
    java = Path(java_token.replace("\\", "/"))
    home = java.parent.parent
    release = home / "release"
    if release.is_file():
        for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("JAVA_VERSION="):
                version = line.split("=", 1)[1].strip().strip('"')
                return _major(version), version
    major = _major(home.name)
    return major, home.name


def read_launch(bat: Path, vmparams: list[Path] | None = None) -> dict:
    """Tokens of the java command line in `bat` with every @argfile and extra vmparams file expanded in place."""
    bat = Path(bat).expanduser().resolve()  # a relative launcher path left %RT% argument files unresolved (found 2026-10-12)
    bat_dir = bat.parent
    seen: set[Path] = set()
    files: list[str] = []
    java_token = ""
    tokens: list[str] = []
    for line in _join_continuations(bat.read_text(encoding="utf-8", errors="replace")):
        words = _tokens(line)
        if not words or words[0].upper().startswith(("REM", "@ECHO", "::", "SET", "CD")):
            continue
        for index, word in enumerate(words):
            if word.lower().endswith("java.exe") or word.lower().endswith("\\java") or word.lower() == "java":
                java_token = java_token or word
                words = words[index + 1:]
                break
        else:
            if not java_token:
                continue
        for word in words:
            tokens.extend(_expand(word, bat_dir, seen, files))
    for extra in vmparams or []:
        tokens.extend(_argfile_tokens(Path(extra), bat_dir, seen, files))
    return {"java": java_token, "tokens": tokens, "files": files}


def enabled_mods_needing_prepatcher(mods_dir: Path) -> list[dict]:
    """Enabled mods (from <mods_dir>/enabled_mods.json) that declare a dependency on Prepatcher or the Toolbox fork,
    or are the Toolbox fork itself."""
    mods_dir = Path(mods_dir)
    enabled_path = mods_dir / "enabled_mods.json"
    if not enabled_path.is_file():
        return []
    try:
        enabled = set(json.loads(enabled_path.read_text(encoding="utf-8")).get("enabledMods", []))
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    found = []
    for folder in sorted(p for p in mods_dir.iterdir() if p.is_dir()):
        info_path = folder / "mod_info.json"
        if not info_path.is_file():
            continue
        try:
            info = json.loads(info_path.read_text(encoding="utf-8-sig", errors="replace"))
        except json.JSONDecodeError:
            continue
        if not isinstance(info, dict) or info.get("id") not in enabled:
            continue
        deps = {d.get("id") for d in info.get("dependencies") or [] if isinstance(d, dict)}
        needs = sorted(deps & PREPATCHER_NEEDERS)
        if info["id"] == "aotd_theory_of_toolbox":
            needs = ["(is the Toolbox fork)"]
        if needs:
            found.append({"mod": info["id"], "needs": needs})
    return found


def main_class_index(tokens: list[str]) -> int | None:
    """Index of the main class in an expanded java command line: the first token that is not an option, an option's value or an
    unresolved @argfile. Everything after it is an application argument, never a JVM option."""
    from bridgeforge.bytecode.java_matrix import VALUE_OPTIONS

    expect_value = False
    for index, token in enumerate(tokens):
        if expect_value:
            expect_value = False
        elif token.startswith("-"):
            expect_value = token in VALUE_OPTIONS
        elif not token.startswith("@"):
            return index
    return None


def _finding(fid: str, classification: str, confidence: str, message: str) -> dict:
    return {"id": fid, "classification": classification, "confidence": confidence, "message": message}


def env_check(bat: Path, vmparams: list[Path] | None = None, mods_dir: Path | None = None) -> dict:
    launch = read_launch(bat, vmparams)
    tokens = launch["tokens"]
    main_at = main_class_index(tokens)
    jvm_tokens = tokens[:main_at] if main_at is not None else tokens  # after the main class are application arguments, not JVM options
    agents = [t.split(":", 1)[1] for t in jvm_tokens if t.startswith("-javaagent:")]
    prepatcher_at = [i for i, a in enumerate(agents) if PREPATCHER_MARKER in a]
    prepatcher_last = bool(prepatcher_at) and prepatcher_at[-1] == len(agents) - 1
    major, version = _java_home_info(launch["java"]) if launch["java"] else (None, "")
    heaps = [m for t in tokens if (m := _HEAP.fullmatch(t))]
    heap = f"{heaps[-1].group(1)}{heaps[-1].group(2) or ''}" if heaps else None
    needers = enabled_mods_needing_prepatcher(mods_dir) if mods_dir else []
    findings = []
    late = [t for t in (tokens[main_at + 1:] if main_at is not None else []) if t.startswith("-javaagent:")]
    if late:
        # `-javaagent:` after the main class is an application argument: the JVM never loads it (java-matrix --prepatcher appended the
        # Prepatcher agent after com.fs.starfarer.StarfarerLauncher in fr.vmparams, 2026-10-12, so the Toolbox fork saw no agent).
        findings.append(_finding("agent-after-main-class", "REVIEW", "HIGH", f"{len(late)} -javaagent option(s) come after the main class and are never loaded: {', '.join(late)}."))
    if prepatcher_at and not prepatcher_last:
        findings.append(_finding("prepatcher-not-last-agent", "REVIEW", "HIGH", f"Prepatcher is javaagent {prepatcher_at[-1] + 1} of {len(agents)}; it must be the last one."))
    if needers and not prepatcher_at:
        names = ", ".join(f"{n['mod']} ({'/'.join(n['needs'])})" for n in needers)
        findings.append(_finding("prepatcher-needed-but-missing", "REVIEW", "HIGH", f"Enabled mods need the Prepatcher javaagent but the launch has none: {names}."))
    if prepatcher_at and major is not None and major not in PREPATCHER_VALIDATED_MAJORS:
        findings.append(_finding("prepatcher-java-unvalidated", "REVIEW", "MEDIUM", f"Java {major} is outside Prepatcher's documented validated set {PREPATCHER_VALIDATED_MAJORS}; support is not claimed without separate validation."))
    if not launch["java"]:
        findings.append(_finding("java-command-not-found", "UNKNOWN", "LOW", "No java command line was found in the launcher; the version, agents and heap are unknown."))
    return {"schema_version": 1, "launcher": str(bat), "files_read": launch["files"], "java": launch["java"] or None, "java_major": major, "java_version": version or None,
            "javaagents": agents, "prepatcher_present": bool(prepatcher_at), "prepatcher_last": prepatcher_last, "heap": heap,
            "mods_needing_prepatcher": needers, "findings": findings}


def verify_rig_launchers(rig: Path, bats: list[str] | None = None) -> list[dict]:
    """Self-test of generated rig launchers (ROADMAP 70 H1.3): use the text, not just trust it. Per launcher: no -javaagent after the main
    class, every @argfile exists, a `-prep` launcher has the Prepatcher agent last and a plain one has none; across launchers: a `-prep`
    and a plain one never share an argument file (one shared fr.filtered.vmparams made every Fast Rendering launcher load the agent).
    Returns {"bat", "id", "message"} per problem."""
    rig = Path(rig).expanduser().resolve()
    names = bats if bats is not None else sorted(p.name for p in rig.glob("run-*.bat"))
    problems: list[dict] = []
    users: dict[str, dict[str, set[str]]] = {}
    for name in names:
        bat = rig / name
        if not bat.is_file():
            problems.append({"bat": name, "id": "launcher-missing", "message": f"{name} was not written"})
            continue
        result = env_check(bat)
        for finding in result["findings"]:
            if finding["id"] in ("agent-after-main-class", "prepatcher-not-last-agent"):
                problems.append({"bat": name, "id": finding["id"], "message": finding["message"]})
        launch = read_launch(bat)
        for token in launch["tokens"]:
            if token.startswith("@") and len(token) > 1:
                problems.append({"bat": name, "id": "argfile-missing", "message": f"argument file {token[1:]} does not exist"})
        prep_expected = name.endswith("-prep.bat") or "prepatcher" in name
        if prep_expected and not result["prepatcher_last"]:
            problems.append({"bat": name, "id": "prep-launcher-without-agent", "message": "a -prep launcher must carry the Prepatcher agent, last"})
        if not prep_expected and result["prepatcher_present"] and "miko" not in name:
            problems.append({"bat": name, "id": "plain-launcher-with-agent", "message": "a launcher without -prep loads the Prepatcher agent"})
        for argfile in launch["files"]:
            users.setdefault(argfile, {"prep": set(), "plain": set()})["prep" if prep_expected else "plain"].add(name)
    for argfile, groups in sorted(users.items()):
        if groups["prep"] and groups["plain"]:
            problems.append({"bat": ", ".join(sorted(groups["prep"] | groups["plain"])), "id": "argfile-shared-between-variants",
                             "message": f"{Path(argfile).name} is used by both a -prep and a plain launcher"})
    return problems


def render(result: dict) -> str:
    lines = [f"Launcher: {result['launcher']}", f"Files read: {', '.join(result['files_read']) or 'none'}",
             f"Java: {result['java_version']} (major {result['java_major']})", f"Heap: {result['heap']}"]
    lines.append("Javaagents: " + (" -> ".join(Path(a.replace('\\', '/')).name for a in result["javaagents"]) or "none"))
    lines.append(f"Prepatcher: {'present, last' if result['prepatcher_last'] else 'present, NOT last' if result['prepatcher_present'] else 'absent'}")
    lines += [f"[{f['classification']}/{f['confidence']}] {f['id']}: {f['message']}" for f in result["findings"]] or ["No findings."]
    return "\n".join(lines)
