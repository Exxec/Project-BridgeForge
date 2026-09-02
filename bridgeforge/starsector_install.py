from __future__ import annotations

import hashlib
from pathlib import Path


def inventory_starsector_install(install_root: Path) -> tuple[list[Path], dict[str, object]]:
    """Return a hash-recorded, local-only Starsector core compile classpath.

    The selected install is never modified.  Every non-source JAR directly in
    ``starsector-core`` is included because the public API JAR alone omits
    runtime-provided compile types such as Log4j and LWJGL utility classes.
    Third-party mod dependencies remain separate and must still be supplied by
    the library registry or explicit ``--dependency-jar`` arguments.
    """
    install_root = install_root.expanduser().resolve()
    core = install_root / "starsector-core"
    api = core / "starfarer.api.jar"
    if not core.is_dir() or not api.is_file():
        raise ValueError("Selected Starsector install must contain starsector-core/starfarer.api.jar.")
    jars = sorted(path for path in core.glob("*.jar") if path.is_file() and not path.name.endswith("-sources.jar"))
    if not jars:
        raise ValueError("Selected Starsector install has no usable core JARs.")
    inventory = {
        "mode": "EXPLICIT_LOCAL_STARSECTOR_INSTALL",
        "install_root": str(install_root),
        "core_directory": str(core),
        "jars": [
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in jars
        ],
    }
    return jars, inventory
