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
# BRIDGEFORGE_DATA_ROOT points commands at the owner's real In operation/, Done/ and bridgeforge-state/ (96.5 A2); a test
# must never resolve its defaults there.
os.environ.pop("BRIDGEFORGE_DATA_ROOT", None)

# Registry guard (ROADMAP-3 96.5 C4, owner 2026-11-18). rig/rig_prefs.py writes HKCU\Software\JavaSoft\Prefs\com\fs\starfarer,
# the key that also holds the Starsector licence key, and rig-doctor reads HKLM. Only each test's own patch kept them off
# the real registry. Here, opening, creating or deleting any key outside TEST_REGISTRY_ROOT (under HKEY_CURRENT_USER)
# raises, so a forgotten patch fails loudly instead of touching the machine. A test that patches `winreg.OpenKey` and the
# like replaces the guard on purpose. Discovery imports every test module before a test runs, and over half of them import
# this one, so a whole-suite run is guarded from its first test; a test module that reaches registry code imports this
# module itself (tests/test_registry_guard.py checks it).
TEST_REGISTRY_ROOT = "Software\\BridgeForgeTests"


class RegistryGuardError(RuntimeError):
    """A test reached the real Windows registry outside TEST_REGISTRY_ROOT without patching winreg. Not an OSError on
    purpose: product code catches OSError as "key unreadable" and would hide the access."""


def _registry_allowed(root, sub_key) -> bool:
    import winreg

    path = str(sub_key or "").replace("/", "\\").strip("\\").lower()
    prefix = TEST_REGISTRY_ROOT.lower()
    return root == winreg.HKEY_CURRENT_USER and (path == prefix or path.startswith(prefix + "\\"))


def _guarded(name: str, original):
    def call(key, sub_key="", *args, **kwargs):
        if not _registry_allowed(key, sub_key):
            raise RegistryGuardError(f"winreg.{name}({sub_key!r}) in a test: patch winreg, or use a key under "
                                     f"HKEY_CURRENT_USER\\{TEST_REGISTRY_ROOT} (96.5 C4)")
        return original(key, sub_key, *args, **kwargs)

    call.registry_guard = True
    return call


def install_registry_guard() -> None:
    try:
        import winreg
    except ImportError:  # not Windows: no registry to guard
        return
    for name in ("OpenKey", "OpenKeyEx", "CreateKey", "CreateKeyEx", "DeleteKey", "DeleteKeyEx"):
        current = getattr(winreg, name, None)
        if current is not None and not getattr(current, "registry_guard", False):
            setattr(winreg, name, _guarded(name, current))


install_registry_guard()


def write_text(path: Path, text: str) -> None:
    """Write `text` as UTF-8 with the LF line ends the repository keeps, creating the parent folders.

    61 test modules each had their own `_write`; 42 used `write_text`, which writes CRLF on Windows and LF on Linux, so the
    same fixture differed by platform (ROADMAP-3 96.5 C9). Import it as `from tests.support import write_text as _write`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


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
