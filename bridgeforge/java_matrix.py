"""Boot one mod set across every Java version and launcher a tester might use (ROADMAP item 61).

A tester's log showed vanilla ids missing at load ("System with id [temporalshell] not found", "Ship hull
spec [afflictor] not found!") on Java 28-beta with Fast Rendering. Nothing in the rig could vary the JVM or
the launcher, so such a report could be neither reproduced nor ruled out. A *variant* is one JDK plus one
launcher; `setup_rig` writes a `run-j<major>-<launcher>.bat` per variant beside the rig's `run-java25.bat`
(which it never touches) and `run_java_matrix` boots the same mods through each, several times, and reports a
pass rate per variant, because a parallel-loading race need not show on every run.

Launchers: `direct` is the proven RC8 flag block (rig `run-java25.bat`, read 2026-10-09) on the chosen JDK;
`fr` is Fast Rendering's own `fr.bat` command (`java [-javaagent:PatchLibAgent.jar] @fr.vmparams`, read from the
install 2026-10-09) on the chosen JDK. The `fr` bat appends the rig's log path so a run never writes its log
into the real install through the `starsector-core` junction.

Needs the game install and a rig, so a live run is local-only (docs/LOCAL_HANDOFF.md).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import boot_test
from .progress import Checkpoint, report

LAUNCHERS = ("direct", "fr", "miko", "miko-noprep")
DEFAULT_LAUNCHERS = ("direct", "fr")  # miko variants mirror the owner's real launch and are opt-in
MIKO_ARGS = "Miko_Simple.txt"  # the argument file Miko_Rouge.bat passes to java (@..\Miko_Simple.txt)
PREPATCHER_MARKER = "StarsectorPrepatcherAgent"
DEFAULT_HEAP_GB = 4  # 32 GB machine, three instances: 3 x (heap + ~2 GB native) leaves room for the OS (owner 2026-10-10)

# Directories searched for a JDK, in addition to the install the rig links to and the rig itself.
COMMON_JDK_ROOTS = (
    Path(r"C:\Program Files\Eclipse Adoptium"),
    Path(r"C:\Program Files\Java"),
    Path(r"C:\Program Files\Microsoft"),
    Path(r"C:\Program Files\Zulu"),
    Path(r"C:\Program Files\Amazon Corretto"),
)

DIRECT_FLAGS = (
    "-noverify -XX:+UnlockDiagnosticVMOptions -XX:-BytecodeVerificationLocal -XX:-BytecodeVerificationRemote",
    "-Djava.library.path=native\\windows",
    "-Djava.util.Arrays.useLegacyMergeSort=true",
    "--enable-preview --enable-native-access=ALL-UNNAMED",
    "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED --add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/java.util=ALL-UNNAMED --add-opens=java.base/java.util.concurrent=ALL-UNNAMED --add-opens=java.base/java.util.concurrent.locks=ALL-UNNAMED --add-opens=java.base/jdk.internal.ref=ALL-UNNAMED --add-opens=java.base/java.lang.reflect=ALL-UNNAMED --add-opens=java.base/java.lang.ref=ALL-UNNAMED --add-opens=java.base/java.text=ALL-UNNAMED --add-opens=java.desktop/java.awt.font=ALL-UNNAMED --add-opens=java.desktop/java.awt=ALL-UNNAMED",
    "--add-exports=java.base/jdk.internal.ref=ALL-UNNAMED --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED --add-exports=java.base/sun.nio.ch=ALL-UNNAMED",
    "-Xms{heap}g -Xmx{heap}g -Xss4m",
)
PATH_FLAGS = (
    "-Dcom.fs.starfarer.settings.paths.saves=..\\saves",
    "-Dcom.fs.starfarer.settings.paths.screenshots=..\\screenshots",
    "-Dcom.fs.starfarer.settings.paths.mods=..\\mods",
    "-Dcom.fs.starfarer.settings.paths.logs=..\\logs",
)
CLASSPATH = (
    "janino.jar;commons-compiler.jar;commons-compiler-jdk.jar;starfarer.api.jar;starfarer_obf.jar;jogg-0.0.7.jar;"
    "jorbis-0.0.15.jar;json.jar;lwjgl.jar;jinput.jar;log4j-1.2.9.jar;lwjgl_util.jar;fs.sound_obf.jar;fs.common_obf.jar;"
    "xstream-1.4.10.jar;txw2-3.0.2.jar;jaxb-api-2.4.0-b180830.0359.jar;webp-imageio-0.1.6.jar"
)


def _major(text: str) -> int | None:
    """Major version from `25.0.4.1`, `1.8.0_503`, `28-beta` or a folder name like `jdk-28+13`."""
    match = re.search(r"(?<![\d.])(1\.(\d+)|(\d+))", text)
    if not match:
        return None
    return int(match.group(2) or match.group(3))


def _jdk_info(home: Path) -> dict | None:
    java = home / "bin" / "java.exe"
    if not java.is_file() and not (home / "bin" / "java").is_file():
        return None
    version = ""
    release = home / "release"
    if release.is_file():
        for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("JAVA_VERSION="):
                version = line.split("=", 1)[1].strip().strip('"')
    major = _major(version) or _major(home.name)
    if major is None:
        return None
    return {"major": major, "version": version or home.name, "home": str(home), "name": home.name}


def discover_jdks(rig: Path | None = None, extra_roots: list[Path] | None = None) -> list[dict]:
    """JDKs/JREs found beside the rig's linked install, inside the rig, and in the usual install folders.

    One entry per major version (the first found wins: install and rig copies come before system ones),
    sorted by major. A tester's exact JVM build is not knowable here; `describe_log_java` reads it from a log.
    """
    roots: list[Path] = []
    if rig is not None:
        rig = Path(rig).expanduser().resolve()
        roots.append(rig)
        core = rig / "starsector-core"
        try:
            install = core.resolve().parent
        except OSError:
            install = None
        if install is not None:
            roots += [install, install / "jre"]
    roots += list(extra_roots or []) + list(COMMON_JDK_ROOTS)
    found: dict[int, dict] = {}
    for root in roots:
        if not root.is_dir():
            continue
        candidates = [root] + sorted(p for p in root.iterdir() if p.is_dir())
        for home in candidates:
            if home.name != "jre" and home != root and not re.match(r"(jdk|jre|java|zulu|corretto|temurin|microsoft)", home.name, re.I) and not (home / "bin").is_dir():
                continue
            info = _jdk_info(home)
            if info and info["major"] not in found:
                found[info["major"]] = info
    return [found[m] for m in sorted(found)]


def describe_log_java(log: Path) -> dict:
    """What a tester's starsector.log says about its JVM: version line and the mods that patch rendering/loading."""
    result: dict = {"java_version": None, "fast_rendering": False, "launcher_hint": None}
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        if result["java_version"] is None and "StarfarerLauncher" in line and "Java version:" in line:
            result["java_version"] = line.split("Java version:", 1)[1].strip()
        if "com.genir.renderer" in line or "fast-rendering" in line.lower() or "FastRendering" in line:
            result["fast_rendering"] = True
    if result["fast_rendering"]:
        result["launcher_hint"] = "fr"
    return result


def variant_id(major: int, launcher: str) -> str:
    return f"j{major}-{launcher}"


def bat_name(vid: str) -> str:
    return f"run-{vid}.bat"


_REJECTED = ("Unrecognized", "Unsupported", "Improperly specified", "Invalid")
_PROBES: dict[tuple[str, str], bool] = {}


def _java_rejects(java_exe: Path, flags: list[str]) -> bool:
    """True when `java <flags> -version` fails because a flag is unknown to this JVM (not for any other reason)."""
    try:
        done = subprocess.run([str(java_exe), "-XX:+UnlockDiagnosticVMOptions", "-XX:+UnlockExperimentalVMOptions", *flags, "-version"], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode != 0 and any(marker in (done.stderr or "") for marker in _REJECTED)


def probeable(flag: str) -> bool:
    """Flags a newer JVM may have removed. -D, --add-*, -javaagent, -classpath and the main class are never probed."""
    return flag.startswith("-XX:") or flag == "-noverify"


def unsupported_flags(java_exe: Path, flags: list[str]) -> list[str]:
    """Flags this JDK refuses. JDK 28+13 rejects `-noverify` and `-XX:+UseVectorStubs` (found 2026-10-10), which
    would stop the launcher before the game starts, so a variant drops what its JVM does not know and records it."""
    flags = [f for f in dict.fromkeys(flags) if probeable(f)]
    if not flags:
        return []
    key = (str(java_exe), " ".join(flags))
    if key not in _PROBES:
        _PROBES[key] = _java_rejects(java_exe, flags)
    if not _PROBES[key]:
        return []
    dropped = []
    for flag in flags:
        single = (str(java_exe), flag)
        if single not in _PROBES:
            _PROBES[single] = _java_rejects(java_exe, [flag])
        if _PROBES[single]:
            dropped.append(flag)
    return dropped


def write_launcher_files(target: Path, variant: dict, core: Path) -> list[str]:
    """Write the variant's bat (and, for Fast Rendering, a filtered copy of the install's fr.vmparams) into
    `target`; returns and records the flags this JDK does not know. The install's own files are only read."""
    java_exe = Path(variant["jdk_home"]) / "bin" / "java.exe"
    if variant["launcher"] == "direct":
        dropped = unsupported_flags(java_exe, [t for line in DIRECT_FLAGS for t in line.split() if "{" not in t])
    elif variant["launcher"] in ("miko", "miko-noprep"):
        dropped = _write_miko_args(Path(target), variant, Path(core), java_exe)
    else:
        source = Path(core) / "fr.vmparams"
        if not source.is_file():
            raise ValueError(f"{source} not found; the Fast Rendering launcher needs fr.vmparams in the install's starsector-core")
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
        dropped = unsupported_flags(java_exe, [line.strip() for line in lines])
        kept = [line for line in lines if line.strip() not in dropped]
        (Path(target) / "fr.filtered.vmparams").write_text("\n".join(kept) + "\n", encoding="utf-8", newline="")
    variant["dropped_flags"] = dropped
    (Path(target) / variant["bat"]).write_text(build_launcher(variant["jdk_home"], variant["launcher"], variant["major"], dropped, variant.get("heap_gb", DEFAULT_HEAP_GB), variant.get("id", "")), encoding="utf-8", newline="")
    return dropped


def _write_miko_args(target: Path, variant: dict, core: Path, java_exe: Path) -> list[str]:
    """Copy the owner's Miko_Simple.txt into the rig with four edits: heap, log path, flags the JDK refuses, and
    (miko-noprep) the Prepatcher agent line. Links the Mikohime library folder the file's `..\\mikohime` paths need
    and the Prepatcher mod folder its agent path needs. The install is only read."""
    install = Path(core).resolve().parent
    source = install / MIKO_ARGS
    if not source.is_file():
        raise ValueError(f"{source} not found; the miko launcher mirrors the owner's {MIKO_ARGS}")
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    dropped = unsupported_flags(java_exe, [line.strip() for line in lines])
    heap = variant.get("heap_gb", DEFAULT_HEAP_GB)
    out = []
    # Same path style as the owner's own saves line (their file doubles its backslashes): saves -> logs.
    saves_line = next((l.strip() for l in lines if l.strip().startswith("-Dcom.fs.starfarer.settings.paths.saves=")), "")
    logs_value = saves_line.split("=", 1)[1].replace("saves", "logs") if "=" in saves_line else "..\\logs"
    for line in lines:
        text = line.strip()
        if text in dropped:
            continue
        if text.startswith("-Xms"):
            line = f"-Xms{heap}g"
        elif text.startswith("-Xmx"):
            line = f"-Xmx{heap}g"
        elif text.startswith("-Dcom.fs.starfarer.settings.paths.logs="):
            line = "-Dcom.fs.starfarer.settings.paths.logs=" + logs_value
        elif variant["launcher"] == "miko-noprep" and PREPATCHER_MARKER in text and not text.startswith("#"):
            continue
        out.append(line)
    (target / f"miko-{variant['id']}.args").write_text("\n".join(out) + "\n", encoding="utf-8", newline="")
    for name, src in (("mikohime", install / "mikohime"),):
        if src.is_dir() and not (target / name).exists():
            _link(src, target / name)
    (target / "fr-resource-cache").mkdir(exist_ok=True)  # a fresh cache per rig: nothing stale from the install
    prepatcher = install / "mods" / "StarsectorPrepatcher"
    if variant["launcher"] == "miko" and prepatcher.is_dir() and (target / "mods").is_dir() and not (target / "mods" / prepatcher.name).exists():
        _link(prepatcher, target / "mods" / prepatcher.name)
    return dropped


def build_launcher(jdk_home: str, launcher: str, java_major: int, dropped: list[str] | None = None, heap_gb: int = DEFAULT_HEAP_GB, vid: str = "") -> str:
    """Text of a rig launcher .bat. CWD is the starsector-core junction, as in the proven run-java25.bat.

    `dropped` (from write_launcher_files) lists flags to leave out; for Fast Rendering it also switches to the
    filtered fr.filtered.vmparams beside the bat. None keeps the install's fr.vmparams untouched."""
    if launcher not in LAUNCHERS:
        raise ValueError(f"unknown launcher {launcher!r}; expected one of {', '.join(LAUNCHERS)}")
    head = [
        "@ECHO OFF",
        f"REM BridgeForge java-matrix launcher: JDK {java_major}, {launcher}. Generated; rerun `java-matrix setup` instead of editing.",
        "SET RT=%~dp0",
        'CD /D "%RT%starsector-core"',
        "",
    ]
    java = f'"{jdk_home}\\bin\\java.exe"'
    if launcher == "direct":
        flags = [" ".join(t for t in line.format(heap=heap_gb).split() if t not in (dropped or ())) for line in DIRECT_FLAGS]
        flags = [f for f in flags if f]
        if java_major < 17:
            flags = [f.replace(" --enable-native-access=ALL-UNNAMED", "") for f in flags]
        body = [java + " ^"]
        body += [f" {flag} ^" for flag in (*flags, *PATH_FLAGS)]
        body += [f" -classpath {CLASSPATH} ^", " com.fs.starfarer.StarfarerLauncher"]
    elif launcher in ("miko", "miko-noprep"):
        body = [f'{java} "@%RT%miko-{vid}.args"']
    else:
        # fr.bat's own command line; the later -D and -Xmx win, so the log lands in the rig and the heap is ours.
        logs = PATH_FLAGS[-1] + f" -Xms{heap_gb}g -Xmx{heap_gb}g"
        argfile = "@fr.vmparams" if dropped is None else '"@%RT%fr.filtered.vmparams"'
        body = [
            "IF EXIST PatchLibAgent.jar (",
            f"  {java} -javaagent:PatchLibAgent.jar {argfile} {logs}",
            ") ELSE (",
            f"  {java} {argfile} {logs}",
            ")",
        ]
    return "\r\n".join(head + body) + "\r\n"


def plan_variants(jdks: list[dict], launchers: list[str] | None = None, majors: list[int] | None = None) -> list[dict]:
    # RC8 targets Java 17+; the install's bundled Java 8 jre cannot take the flag block, so it is opt-in via majors.
    chosen = [j for j in jdks if (j["major"] in majors if majors else j["major"] >= 17)]
    out = []
    for jdk in chosen:
        for launcher in launchers or list(DEFAULT_LAUNCHERS):
            vid = variant_id(jdk["major"], launcher)
            out.append({"id": vid, "major": jdk["major"], "launcher": launcher, "jdk_home": jdk["home"], "java_version": jdk["version"], "bat": bat_name(vid), "heap_gb": DEFAULT_HEAP_GB})
    return out


def setup_rig(rig: Path, variants: list[dict]) -> list[str]:
    """Write one launcher .bat per variant into the rig. Refuses unless the rig's starsector-core is a link."""
    rig = Path(rig).expanduser().resolve()
    if not boot_test._is_link(rig / "starsector-core"):
        raise ValueError(f"{rig / 'starsector-core'} is not a junction/symlink; java-matrix setup refuses a non-isolated rig")
    written = []
    for variant in variants:
        write_launcher_files(rig, variant, rig / "starsector-core")
        written.append(variant["bat"])
    return written


MAX_PARALLEL = 3  # owner limit 2026-10-09: RAM (~4 GB per instance) and GPU, and timing changes under load
INSTANCE_FILE = "instance.json"
LEDGER_NAME = "java-matrix-ledger.json"


def _link(target: Path, link: Path) -> None:
    """Junction on Windows (the rig layout), symlink elsewhere."""
    try:
        import _winapi
    except ImportError:
        link.symlink_to(target, target_is_directory=True)
    else:
        _winapi.CreateJunction(str(target), str(link))


def make_instance_rig(rig: Path, variant: dict, mods: list[str], mod_sources: list[Path] | None = None) -> Path:
    """A throwaway rig for one parallel instance: its own mods/logs/saves, the same starsector-core.

    Every folder in the main rig's mods/ is linked in (not copied); enabled_mods.json, logs and saves are the
    instance's own, which is what lets run_boot_test's one-run-per-rig refusal stay in force. Rebuilt each run.
    `mod_sources` (mass testing) links exactly those mod folders instead, so a run sees only the mods it needs.
    """
    rig = Path(rig).resolve()
    inst = rig / "instances" / variant["id"]
    if inst.exists():
        _remove_tree(inst)
    (inst / "mods").mkdir(parents=True)
    for sub in ("logs", "saves", "screenshots"):
        (inst / sub).mkdir()
    _link((rig / "starsector-core").resolve(), inst / "starsector-core")
    src = rig / "mods"
    if mod_sources is not None:
        for folder in mod_sources:
            _link(Path(folder).resolve(), inst / "mods" / Path(folder).name)
    elif src.is_dir():
        for child in sorted(p for p in src.iterdir() if p.is_dir()):
            _link(child.resolve(), inst / "mods" / child.name)
    write_launcher_files(inst, variant, inst / "starsector-core")
    return inst


def _remove_tree(path: Path) -> None:
    """Delete an instance rig without following its junctions into the real mods or install."""
    import shutil

    for root, dirs, _files in os.walk(path, topdown=True):
        for name in list(dirs):
            p = Path(root) / name
            if boot_test._is_link(p):
                os.rmdir(p) if os.name == "nt" else p.unlink()
                dirs.remove(name)
    shutil.rmtree(path, ignore_errors=True)


def _keep_logs(result: dict, dest: Path) -> str | None:
    """Copy a boot's stdout/stderr logs out of a throwaway instance rig; returns the kept stdout path."""
    import shutil

    dest.mkdir(parents=True, exist_ok=True)
    kept = None
    for field in ("log", "errlog"):
        src = result.get(field)
        if src and Path(src).is_file():
            target = dest / Path(src).name
            shutil.copy2(src, target)
            if field == "log":
                kept = str(target)
    return kept


def _mods_key(variant: dict, mods: list[str]) -> str:
    return f"{variant['id']}|{variant['java_version']}|{','.join(sorted(mods))}"


def load_ledger(path: Path | None) -> dict:
    if path and Path(path).is_file():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _write_instance(inst: Path, **fields: object) -> None:
    path = inst / INSTANCE_FILE
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data.update(fields)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_instances(rig: Path) -> list[dict]:
    """State of every instance rig under <rig>/instances: variant, run, status, whether its java is alive."""
    rig = Path(rig).expanduser().resolve()
    out = []
    base = rig / "instances"
    for inst in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        path = inst / INSTANCE_FILE
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        alive = bool(boot_test._running_java_under(inst))
        if data.get("state") == "running" and not alive and data.get("finished") is None:
            data["state"] = "running (no java yet)" if time.time() - data.get("started", 0) < 60 else "stale"
        data["java_alive"] = alive
        out.append(data)
    return out


def run_java_matrix(rig: Path, mods: list[str], variants: list[dict], repeats: int = 3, timeout: int = 240, checkpoint: Path | None = None, quiet: bool = False, log_name: str | None = None, parallel: int = 1, ledger: Path | None = None, skip_known: bool = False, mod_sources: list[Path] | None = None, keep_logs: Path | None = None) -> dict:
    """Boot `mods` through every variant `repeats` times; one progress line per boot, resumable from `checkpoint`.

    parallel=1 runs in the rig itself, one boot at a time (the reference). parallel=2..3 gives each variant its
    own instance rig (make_instance_rig) and runs that many variants at once; one variant's repeats stay serial.
    skip_known reuses a PASS_ALL recorded in `ledger` for the same variant, Java build and mod set instead of
    booting again (new mod sets have no entry, so they run everywhere). A variant whose launcher .bat is missing
    is REFUSED (run `java-matrix setup` first), not skipped. `mod_sources` forces instance rigs that link only
    those mod folders (even serially); `keep_logs` copies each boot's logs there, because an instance rig is
    rebuilt for the next run and takes its logs with it.
    """
    if not 1 <= parallel <= MAX_PARALLEL:
        raise ValueError(f"--parallel must be 1..{MAX_PARALLEL}")
    rig = Path(rig).expanduser().resolve()
    base = log_name or "java-matrix"
    known = load_ledger(ledger) if skip_known else {}
    header = {"rig": str(rig), "mods": sorted(mods), "variants": [v["id"] for v in variants], "repeats": repeats}
    rows: dict[str, list[dict]] = {v["id"]: [] for v in variants}
    reused: dict[str, dict] = {}
    todo = []
    for variant in variants:
        entry = known.get(_mods_key(variant, mods))
        if entry and entry.get("pass_rate") == 1.0:
            reused[variant["id"]] = entry
        else:
            todo.append(variant)
    total = len(todo) * repeats
    lock = threading.Lock()
    counter = [0]

    def boot_variant(variant: dict, ckpt: Checkpoint) -> None:
        target_rig, inst = rig, None
        if parallel > 1 or mod_sources is not None:
            inst = make_instance_rig(rig, variant, mods, mod_sources)
            target_rig = inst
        for run in range(1, repeats + 1):
            key = f"{variant['id']}#{run}"
            saved = ckpt.get(key)
            if saved is not None:
                row, seconds = saved, None
            else:
                if inst is not None:
                    _write_instance(inst, variant=variant["id"], launcher=variant["launcher"], java=variant["java_version"], mods=sorted(mods), run=run, of=repeats, state="running", started=time.time(), finished=None, status=None)
                started = time.monotonic()
                result = boot_test.run_boot_test(target_rig, mods, timeout=timeout, log_name=f"{base}-{variant['id']}-{run}", bat_name=variant["bat"])
                seconds = time.monotonic() - started
                triage = result.get("triage") if isinstance(result.get("triage"), dict) else {}
                row = {"run": run, "status": result["status"], "reason": result.get("reason"), "elapsed_seconds": result.get("elapsed_seconds"), "log": result.get("log"), "triage": triage.get("counts"), "vanilla_shadowing_symptoms": len(triage.get("vanilla_shadowing_symptoms") or [])}
                if inst is not None:
                    _write_instance(inst, state="done", finished=time.time(), status=row["status"], log=row["log"])
                    if keep_logs is not None:
                        row["log"] = _keep_logs(result, Path(keep_logs))
            with lock:
                if seconds is not None:
                    ckpt.add(key, row)
                rows[variant["id"]].append(row)
                counter[0] += 1
                if not quiet:
                    report(counter[0], total, key, row["status"], seconds)

    with Checkpoint(checkpoint, header) as ckpt:
        if parallel == 1:
            for variant in todo:
                boot_variant(variant, ckpt)
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                for future in [pool.submit(boot_variant, v, ckpt) for v in todo]:
                    future.result()
    matrix = []
    for variant in variants:
        meta = {**{k: variant[k] for k in ("id", "major", "launcher", "java_version")}, "dropped_flags": variant.get("dropped_flags", [])}
        if variant["id"] in reused:
            matrix.append({**meta, "runs": 0, "passed": 0, "pass_rate": 1.0, "statuses": ["KNOWN_PASS"], "results": [], "reused_from": reused[variant["id"]].get("date")})
            continue
        runs = rows[variant["id"]]
        passed = sum(1 for r in runs if r["status"] == "PASS")
        matrix.append({**meta, "runs": len(runs), "passed": passed, "pass_rate": round(passed / len(runs), 2) if runs else None, "statuses": [r["status"] for r in runs], "results": runs})
    result = {"schema_version": 1, "mode": "JAVA_MATRIX", "mods": sorted(mods), "repeats": repeats, "parallel": parallel, "matrix": matrix, "verdict": _verdict(matrix)}
    if ledger is not None:
        data = load_ledger(ledger)
        stamp = time.strftime("%Y-%m-%d")
        for variant, m in zip(variants, matrix):
            if m["runs"]:
                data[_mods_key(variant, mods)] = {"pass_rate": m["pass_rate"], "runs": m["runs"], "date": stamp, "parallel": parallel}
        Path(ledger).parent.mkdir(parents=True, exist_ok=True)
        Path(ledger).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    if checkpoint is not None and Path(checkpoint).is_file():
        Path(checkpoint).unlink()
    return result


def _verdict(matrix: list[dict]) -> str:
    if not matrix:
        return "NO_VARIANTS"
    if any(m["statuses"] and all(s == "REFUSED" for s in m["statuses"]) for m in matrix):
        return "REFUSED"
    rates = {m["pass_rate"] for m in matrix}
    if rates == {1.0}:
        return "PASS_ALL"
    if rates == {0.0}:
        return "FAIL_ALL"
    if any(m["pass_rate"] not in (0.0, 1.0) for m in matrix):
        return "FLAKY"
    return "VARIES_BY_VARIANT"


def render(result: dict) -> str:
    lines = [f"Verdict: {result['verdict']} ({result['repeats']} run(s) per variant, {result.get('parallel', 1)} at a time)"]
    for m in result["matrix"]:
        known = f"  (reused from {m['reused_from']})" if "reused_from" in m else ""
        lines.append(f"  {m['id']:<14} Java {m['java_version']:<12} {m['passed']}/{m['runs']} PASS  {' '.join(m['statuses'])}{known}")
    return "\n".join(lines)

