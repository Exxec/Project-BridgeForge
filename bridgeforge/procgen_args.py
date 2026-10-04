"""Suspect literal arguments to StarSystemAPI.initStar / LocationAPI.addPlanet (owner request 2026-10-04).

Zorg18's 0.6-era generator called `initStar("star_zorg", 200f, 10000, -10000)` (the last two were the hyperspace
location in 0.6); the modpack port that BridgeForge revived kept `-10000` as RC8's corona size and dropped Zeta I's
planet radius, shifting `addPlanet(..., 0, 100, 5000, 100)` to `(..., 0, 0, 100, 5000)`: a radius-0 planet orbiting at
100. Both compiled, loaded and passed the probe. RC8's signatures (javap, starfarer.api.jar):

- initStar(String id, String type, float radius, float corona[, float wind, float flare, float crLoss])
- initStar(String id, String type, Color color, float radius, float corona)
- addPlanet(String id, SectorEntityToken focus, String name, String type, float angle, float radius,
  float orbitRadius, float orbitDays)

Only literal values are judged: radius <= 0, corona < 0, orbitRadius < 0 or orbitDays <= 0 is suspect. Loose and
bundled sources are parsed; jar classes are read with javap when a JDK is available.
"""
from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

_CALL = re.compile(r"\b(initStar|addPlanet)\s*\(")
_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[fFdD]?\s*$")


def _arguments(text: str, open_index: int) -> list[str] | None:
    depth, start, args = 0, open_index + 1, []
    for i in range(open_index, len(text)):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append(text[start:i])
                return args
        elif ch == "," and depth == 1:
            args.append(text[start:i])
            start = i + 1
    return None


def judge(method: str, floats: list[float | None], has_color: bool = False) -> list[str]:
    """Problems with a call's float arguments, in signature order (None = not a literal)."""
    problems = []
    if method == "initStar":
        radius, corona = (floats + [None, None])[:2]
        if radius is not None and radius <= 0:
            problems.append(f"star radius {radius:g}")
        if corona is not None and corona < 0:
            problems.append(f"corona {corona:g}")
    elif method == "addPlanet" and len(floats) == 4:
        _, radius, orbit_radius, orbit_days = floats
        if radius is not None and radius <= 0:
            problems.append(f"planet radius {radius:g}")
        if orbit_radius is not None and orbit_radius < 0:
            problems.append(f"orbit radius {orbit_radius:g}")
        if orbit_days is not None and orbit_days <= 0:
            problems.append(f"orbit days {orbit_days:g}")
    return problems


def source_suspects(text: str) -> list[tuple[int, str, list[str]]]:
    """(line, method, problems) for literal-argument calls in Java source (comments must be blanked)."""
    found = []
    for match in _CALL.finditer(text):
        args = _arguments(text, match.end() - 1)
        if not args:
            continue
        method = match.group(1)
        if method == "initStar":
            if len(args) < 4:
                continue  # a 0.6-style call RC8 does not have; javac reports it
            color = "Color" in args[2] or "new " in args[2]
            raw = args[3:5] if color else args[2:4]
        else:
            if len(args) != 8:
                continue
            raw = args[4:8]
        floats = [float(m.group(1)) if (m := _NUMBER.match(a)) else None for a in raw]
        problems = judge(method, floats)
        if problems:
            found.append((text.count("\n", 0, match.start()) + 1, method, problems))
    return found


_FLOAT_PUSH = re.compile(r"^\s*\d+:\s*(fconst_(\d)|ldc(?:_w)?\s+#\d+\s+// float (-?[\d.E-]+)f?|"
                         r"(bipush|sipush)\s+(-?\d+)|iconst_(m1|\d))")
_INVOKE = re.compile(r"^\s*\d+:\s*invoke\w+\s+#\d+(?:,\s*\d+)?\s+// (?:Interface)?Method ([\w/$]+)\.(initStar|addPlanet):\(([^)]*)\)")


def javap_suspects(listing: str) -> list[tuple[str, str, list[str]]]:
    """(method in class, call, problems) from `javap -c -constants` output. Tracks float pushes since the last invoke:
    fconst/ldc float, and int pushes followed by i2f; any other float-producing instruction makes the value unknown."""
    found, floats, current, pending_int = [], [], "?", None
    for line in listing.splitlines():
        header = re.match(r"^  (?:public|private|protected|static|final|\s)*[\w.$<>\[\]]+ (\w+)\(", line)
        if header:
            current, floats, pending_int = header.group(1), [], None
            continue
        if re.match(r"^\s*\d+:\s*i2f", line):
            floats.append(pending_int)
            pending_int = None
            continue
        push = _FLOAT_PUSH.match(line)
        if push:
            if push.group(2) is not None:
                floats.append(float(push.group(2)))
            elif push.group(3) is not None:
                floats.append(float(push.group(3)))
            else:
                pending_int = float(push.group(5) if push.group(5) is not None else (-1 if push.group(6) == "m1" else push.group(6)))
            continue
        invoke = _INVOKE.match(line)
        if invoke:
            method, descriptor = invoke.group(2), invoke.group(3)
            count = descriptor.count("F")
            values = floats[-count:] if count and len(floats) >= count else [None] * count
            if method == "initStar":
                values = values[:2]
            problems = judge(method, values)
            if problems:
                found.append((current, method, problems))
            floats, pending_int = [], None
            continue
        if re.match(r"^\s*\d+:\s*(fload|faload|getfield|getstatic|invoke|fadd|fsub|fmul|fdiv|fneg|d2f|l2f)", line):
            floats.append(None)
    return found


def jar_suspects(jar: Path, javap: Path) -> list[tuple[str, str, str, list[str]]]:
    """(class, method, call, problems) for one jar's classes that mention initStar or addPlanet."""
    try:
        with zipfile.ZipFile(jar) as archive:
            names = [n for n in archive.namelist() if n.endswith(".class") and (b"initStar" in (data := archive.read(n))
                                                                                or b"addPlanet" in data)]
    except (OSError, zipfile.BadZipFile):
        return []
    found = []
    for name in names:
        cls = name[:-6].replace("/", ".")
        out = subprocess.run([str(javap), "-c", "-p", "-constants", "-cp", str(jar), cls], capture_output=True,
                             text=True, encoding="utf-8", errors="replace").stdout
        found += [(name, method, call, problems) for method, call, problems in javap_suspects(out)]
    return found
