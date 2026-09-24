"""Shared test fixtures: normalize Windows RUNNER~1/8.3 temporary paths."""
from contextlib import contextmanager
from pathlib import Path
import tempfile


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
