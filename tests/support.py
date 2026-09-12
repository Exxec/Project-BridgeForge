"""Shared test fixtures: normalize Windows RUNNER~1/8.3 temporary paths."""
from contextlib import contextmanager
from pathlib import Path
import tempfile


@contextmanager
def resolved_temp_dir(**kwargs):
    with tempfile.TemporaryDirectory(**kwargs) as directory:
        yield Path(directory).resolve()
