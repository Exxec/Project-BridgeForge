"""Shared test fixtures: normalize Windows RUNNER~1/8.3 temporary paths."""
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile

# Git hooks run with GIT_DIR, GIT_INDEX_FILE and similar set to the real repository. A test that runs `git init` in a temp
# folder under those variables re-initialises the real repository instead (2026-10-21: the pre-push hook's test run set
# core.bare=true on the owner's checkout). Every git-running test module imports this one, so drop them before tests run.
for _name in [name for name in os.environ if name.startswith("GIT_")]:
    del os.environ[_name]


@contextmanager
def resolved_temp_dir(**kwargs):
    with tempfile.TemporaryDirectory(**kwargs) as directory:
        yield Path(directory).resolve()


def link_dir(target: Path, link: Path) -> None:
    """Link `link` to directory `target` the way a rig links starsector-core.

    Windows gets a real NTFS junction (the production layout); elsewhere a directory symlink,
    which the rig guards accept too, so the rig-safety tests also run on POSIX CI.
    Raises OSError when neither can be created.
    """
    try:
        import _winapi
    except ImportError:
        link.symlink_to(target, target_is_directory=True)
    else:
        _winapi.CreateJunction(str(target), str(link))


def project_jdk_major() -> int | None:
    """The JDK feature version CI installs (`.java-version`, read by every setup-java step), or None outside a checkout."""
    try:
        return int((Path(__file__).resolve().parents[1] / ".java-version").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def javac_path() -> str | None:
    """A javac to compile test fixtures with: the JDK `find_jdk` picks (repo rig, JAVA_HOME, PATH), else None.

    A JDK of `.java-version`'s version wins when there is one, so a local run compiles with the JDK CI uses (96.5 C6).
    `shutil.which("javac")` alone skipped these tests on a machine whose only JDK is the rig's (2026-11-15)."""
    from bridgeforge.bytecode.java_toolchain import find_jdk

    jdk = find_jdk(prefer_major=project_jdk_major())
    return str(jdk.javac) if jdk is not None else None
