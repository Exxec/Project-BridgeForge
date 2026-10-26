"""S1 read-only workspace boundary; opening paths grants no qualification or mutation rights."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PureWindowsPath


@dataclass(frozen=True)
class WorkspaceView:
    schema_version: int
    layout: str
    root: Path
    original_container: Path
    original: Path
    working: Path
    reports: Path | None
    checkpoints: Path | None
    selection_source: str
    unavailable: tuple[str, ...]
    provenance: str = 'UNVERIFIED'


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _present(path: Path) -> bool:
    return path.exists() or _linked(path)


def _physical(path: Path) -> Path:
    if any(_linked(part) for part in (path, *path.parents)):
        raise ValueError(f'Workspace view refuses symlink/junction path: {path}')
    return path.resolve()


def _directory(path: Path, field: str) -> Path:
    result = _physical(path)
    if not result.is_dir():
        raise ValueError(f'{field}: required directory is missing: {path}')
    return result


def _components(value: object, field: str) -> list[str]:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{field}: expected a nonempty relative path')
    portable = value.replace('\\', '/')
    if PureWindowsPath(value).drive or portable.startswith('/') or any(part in {'', '.', '..'} for part in portable.split('/')) or ':' in portable:
        raise ValueError(f'{field}: absolute, drive, empty or traversal components are not permitted')
    return portable.split('/')


def _relative(root: Path, value: object, field: str) -> Path:
    selected = _physical(root.joinpath(*_components(value, field)))
    if not selected.is_relative_to(root):
        raise ValueError(f'{field}: path escapes workspace boundary')
    return selected


def _record(path: Path) -> dict:
    _physical(path)
    try:
        result = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'{path.name}: cannot read JSON record: {exc}') from exc
    if not isinstance(result, dict) or type(result.get('schema_version')) is not int or result['schema_version'] != 1:
        raise ValueError(f'{path.name}: expected schema_version 1 object')
    return result


def _mod(path: Path, field: str) -> Path:
    result = _directory(path, field)
    marker = result / 'mod_info.json'
    _physical(marker)
    if not marker.is_file():
        raise ValueError(f'{field}: selected mod root has no mod_info.json: {result}')
    return result


def _disjoint(paths: list[Path]) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ValueError(f'Workspace roles overlap: {left} and {right}')


def open_workspace_view(workspace: Path, *, original_relative: str | None = None) -> WorkspaceView:
    """Adapt supported physical layouts without writes, first-match selection or acceptance inference.

    Explicit original selection is relative to the preserved original container, not the working copy.
    Nested payload safety, source/jar authority, hashes and concurrent changes need later qualification.
    """
    root = _directory(Path(workspace).expanduser(), 'workspace')
    manifest_path = root / 'workspace-manifest.json'
    convention = any(_present(root / name) for name in ('original', 'working'))
    manifest_dirs = any(_present(root / name) for name in ('original-reference', 'working-copy'))
    if _present(manifest_path):
        if convention:
            raise ValueError('Ambiguous workspace: manifest and convention layout markers coexist')
        record = _record(manifest_path)
        container = _directory(_relative(root, record.get('original_reference'), 'original_reference'), 'original_reference')
        working = _mod(_relative(root, record.get('working_copy'), 'working_copy'), 'working_copy')
        layout, source = 'manifest-v1', 'WORKSPACE_REFERENCE'
    else:
        if manifest_dirs:
            raise ValueError('Incomplete/ambiguous workspace: manifest-layout directories without a manifest')
        container = _directory(root / 'original', 'original')
        working = _mod(root / 'working', 'working')
        layout, source = 'convention-v1', 'ROOT_REFERENCE'
    _disjoint([container, working])
    reports = _directory(root / 'reports', 'reports') if _present(root / 'reports') else None
    checkpoints = _directory(root / 'checkpoints', 'checkpoints') if layout == 'manifest-v1' and _present(root / 'checkpoints') else None
    _disjoint([container, working, *([reports] if reports else []), *([checkpoints] if checkpoints else [])])
    if original_relative is not None:
        selected = container if original_relative == '.' else _relative(container, original_relative, 'original_relative')
        source = 'EXPLICIT_SELECTION'
    elif layout == 'convention-v1' and reports and _present(reports / 'intake.json'):
        intake = _record(reports / 'intake.json')
        if intake.get('mode') != 'INTAKE':
            raise ValueError('intake.json: expected INTAKE mode')
        selected_root = intake.get('selected_root')
        if selected_root == '.':
            selected = _relative(container, 'extracted', 'selected_root')
        else:
            # Validate before prefixing so an absolute/drive path cannot be disguised as a child.
            _components(selected_root, 'selected_root')
            selected = _relative(container, 'extracted/' + selected_root, 'selected_root')
        source = 'INTAKE_SELECTION'
    else:
        selected = container
        if not (selected / 'mod_info.json').is_file():
            raise ValueError('Original mod root is not explicit; provide original_relative within the original container')
    original = _mod(selected, 'original')
    unavailable = tuple(name for name, value in (('reports', reports), ('checkpoints', checkpoints)) if value is None)
    return WorkspaceView(1, layout, root, container, original, working, reports, checkpoints, source, unavailable)
