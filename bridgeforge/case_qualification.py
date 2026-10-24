"""S1 shared read-only qualification: re-evaluate evidence, never trust generic PASS receipts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .bytecode.java_toolchain import find_jdk
from .case_identity import digest, file_digest, tree_digest, tree_files
from .case_store import CaseStore
from .case_workspace import _physical
from .compile_check import discover_loose_scripts
from .log_triage import triage_log
from .release import _load_policy, policy_entry
from .run_manifest import CONFIG_RELATIVE, evaluate_run, read_manifest
from .live.live_trust import shipped_hash
from .safeio import atomic_write_json
from .scan.scan_classfile import _loaded_mod_jars
from .scan.scan_registry import _excluded
from .scan.scanner import _load_lenient_json_file
from .source_paths import python_sources

PROFILE_ID = 'rc8-local-new-game/v1'
TARGET = {'target': '0.98a-RC8', 'java': 17, 'scope': 'new-game', 'qualification_profile': PROFILE_ID}
REQUIRED = ('candidate', 'context', 'target', 'review', 'source_authority', 'dependencies', 'static', 'api', 'compile', 'rights', 'live')
LIVE_MILESTONES = ('main_menu', 'campaign_load', 'combat')


def result(status: str, reason: str, **details) -> dict:
    return {'status': status, 'reason': reason, **details}


def engine_identity() -> str:
    root = Path(__file__).resolve().parent
    paths = set(python_sources(root))
    for suffix in ('*.json', '*.java', '*.jar', '*.txt'):
        paths.update(root.rglob(suffix))
    return digest({path.relative_to(root).as_posix(): file_digest(path) for path in sorted(paths) if '__pycache__' not in path.parts})


def review_subject(candidate: dict) -> str:
    body = candidate['content']
    # Exclude the review declaration itself, preventing a circular approval hash.
    context = {role: value for role, value in body['context']['inputs'].items() if role != 'source_authority'}
    return digest({'case_id': body['case_id'], 'target_profile': body['target_profile'], 'original': body['original'],
                   'payload': body['payload'], 'context': context})


def _binding(body: dict, role: str, name: str, kind: str) -> Path | None:
    item = (body['context']['inputs'].get(role) or {}).get(name)
    return Path(item['path']) if item and item['kind'] == kind else None


def _json(path: Path) -> dict:
    _physical(path)
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Evidence/policy record must be an object')
    return value


def _review(body: dict, candidate: dict, working: Path, original: Path) -> tuple[dict, dict | None]:
    original_files = {name: hashed for name, hashed in tree_files(original).items() if not _excluded(name)}
    unchanged = tree_digest(original_files) == body['payload']['analysis']['sha256']
    path = _binding(body, 'source_authority', 'review', 'file')
    if path is None:
        if unchanged:
            return result('NOT_APPLICABLE', 'Original and working analysis inputs are identical; no changes to approve'), None
        return result('INCOMPLETE', 'Changed inputs require a bound owner decision, not a generic PASS receipt'), None
    decision = _json(path)
    valid = (decision.get('schema') == 'bridgeforge.owner-review' and type(decision.get('schema_version')) is int
             and decision['schema_version'] == 1 and decision.get('actor') == 'owner'
             and decision.get('decision') == 'APPROVE_FOR_DECLARED_NEW_GAME' and decision.get('scope') == PROFILE_ID
             and decision.get('subject_id') == review_subject(candidate)
             and isinstance(decision.get('reason'), str) and bool(decision['reason'].strip()))
    if not valid:
        return result('INCOMPLETE', 'Owner policy decision is unsupported, out of scope or bound to different inputs'), None
    return result('PASS', 'Explicit owner policy decision matches these inputs; not empirical behavior proof', decision_sha256=file_digest(path)), decision


def _deps(info: dict) -> list[str]:
    entries = info.get('dependencies', [])
    if not isinstance(entries, list):
        raise ValueError('Unsupported dependency declaration')
    found = []
    for entry in entries:
        name = entry.get('id') if isinstance(entry, dict) else entry
        if not isinstance(name, str) or not name.strip() or name in found:
            raise ValueError('Missing/duplicate dependency ID')
        if isinstance(entry, dict) and entry.get('version'):
            raise ValueError('Version-constrained dependency needs an evidenced resolution policy')
        found.append(name)
    return found


def _dependencies(body: dict, info: dict) -> tuple[dict, list[Path]]:
    group = body['context']['inputs']['dependencies']
    if group is None:
        return result('INCOMPLETE', 'Dependency selection is unknown'), []
    selected, rows = {}, {}
    for key, item in group.items():
        if item['kind'] != 'tree':
            return result('INCOMPLETE', 'Providers must be bound mod directories'), []
        path = Path(item['path'])
        metadata = _load_lenient_json_file(path / 'mod_info.json')
        if not isinstance(metadata, dict) or metadata.get('id') != key or key == info.get('id'):
            return result('FAIL', 'Selected provider identity is missing, conflicting or self-referential'), []
        selected[key], rows[key] = path, metadata
    visited, active = set(), set()
    def visit(name):
        if name in active:
            raise ValueError('Dependency cycle needs explicit resolution')
        if name in visited:
            return
        if name not in selected:
            raise ValueError('Missing selected dependency: ' + name)
        active.add(name)
        for child in _deps(rows[name]):
            visit(child)
        active.remove(name); visited.add(name)
    try:
        for name in _deps(info):
            visit(name)
    except ValueError as exc:
        return result('INCOMPLETE', str(exc)), []
    if set(selected) != visited:
        return result('INCOMPLETE', 'Extra providers are not justified by the declared closure'), []
    return result('PASS', 'Explicit provider closure resolved by metadata identities', selected=sorted(visited)), [selected[name] for name in sorted(visited)]


def _worker(working: Path, core: Path, providers: list[Path], body: dict, compile_requested: bool) -> dict:
    python = _binding(body, 'tools', 'python', 'file')
    if python != Path(sys.executable).resolve() or python.is_relative_to(working):
        return {'error': 'Qualification Python is not the bound running interpreter'}
    needs_java = bool(list(working.rglob('*.java')) or list(working.rglob('*.jar')))
    jdk = _binding(body, 'tools', 'jdk', 'tree')
    if needs_java:
        selected = find_jdk()
        if selected is None or jdk != selected.home or jdk.is_relative_to(working):
            return {'error': 'Java analysis requires the bound configured JDK, without discovery fallback'}
    with tempfile.TemporaryDirectory(prefix='bf-case-evidence-') as temporary:
        folder = Path(temporary).resolve()
        request, response = folder / 'request.json', folder / 'response.json'
        atomic_write_json(request, {'working': str(working), 'core': str(core), 'providers': [str(path) for path in providers],
                                    'compile': compile_requested, 'jdk': str(jdk) if jdk else None})
        env = dict(os.environ)
        env.update(TMP=str(folder), TEMP=str(folder), TMPDIR=str(folder), PYTHONPATH=str(Path(__file__).resolve().parent.parent))
        env['PATH'] = str(python.parent)
        env.pop('JAVA_HOME', None)
        if needs_java:
            env['JAVA_HOME'] = str(jdk)
            env['PATH'] = str(jdk / 'bin') + os.pathsep + env['PATH']
        try:
            done = subprocess.run([str(python), '-m', 'bridgeforge.case_evidence', str(request), str(response)],
                                  cwd=folder, env=env, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            return {'error': 'Evidence worker timed out; no qualification'}
        if done.returncode != 0 or not response.is_file():
            return {'error': 'Evidence worker failed: ' + (done.stderr or done.stdout)[-2000:]}
        value = _json(response)
        if value.get('schema_version') != 1:
            return {'error': 'Unsupported evidence worker response'}
        return value


def _compile(observed: dict, sources: list[Path], requested: bool, core: Path | None, dependencies: dict) -> dict:
    if not sources:
        return result('NOT_APPLICABLE', 'Fresh inventory found no active loose data Java sources')
    if core is None or dependencies['status'] != 'PASS' or not requested:
        return result('INCOMPLETE', 'Bound core/provider closure and explicit compile execution are required')
    value = observed.get('compile')
    if not isinstance(value, dict) or value.get('status') == 'UNAVAILABLE':
        return result('INCOMPLETE', 'Compile evidence is unavailable')
    if value.get('status') == 'FAIL' or value.get('javac_returncode') not in (0, None) or (value.get('janino') or {}).get('status') == 'FAIL':
        return result('FAIL', 'Current javac/Janino compilation failed', compile=value)
    if value.get('status') != 'PASS' or value.get('janino', {}).get('status') != 'PASS' or value.get('vanilla_companion_errors'):
        return result('INCOMPLETE', 'Both javac and RC8 Janino must be available and pass', compile=value)
    expected = {str(path.resolve()) for path in sources}
    # The worker reports every requested loose source, not an arbitrary one-file probe.
    mod = Path(value['mod'])
    covered = {str((mod / path).resolve()) for path in value.get('files', [])}
    if expected != covered:
        return result('INCOMPLETE', 'Compilation did not cover the current loose-source set')
    return result('PASS', 'Current full loose-source javac and RC8 Janino checks passed', compile=value)


def _run_context(body: dict, working: Path, info: dict, manifest: dict, rig: Path) -> dict | None:
    core = _binding(body, 'core', 'starsector', 'tree')
    launcher = _binding(body, 'launcher', 'game', 'file')
    jdk = _binding(body, 'tools', 'jdk', 'tree')
    if core is None or launcher is None or jdk is None:
        return result('INCOMPLETE', 'Live evidence needs bound core, launcher and runtime JDK')
    runtime = manifest['runtime']
    expected_java = jdk / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
    launcher_hash = runtime.get('launcher_files', {}).get(launcher.name)
    if (Path(manifest['rig_core']).resolve() != core or runtime.get('java_executable') is None
            or Path(runtime['java_executable']).resolve() != expected_java or launcher_hash != file_digest(launcher)):
        return result('FAIL', 'Run core/runtime/launcher do not match candidate context')
    # R1 binds staged bytes; also require those bytes to match this case's selected closure.
    selected = {info['id']: body['payload']['sha256']}
    for item in (body['context']['inputs']['dependencies'] or {}).values():
        path = Path(item['path'])
        metadata = _load_lenient_json_file(path / 'mod_info.json')
        selected[metadata['id']] = shipped_hash(path)
    probe = _binding(body, 'tools', 'probe', 'tree')
    if probe is not None:
        metadata = _load_lenient_json_file(probe / 'mod_info.json')
        if metadata['id'] in selected:
            return result('FAIL', 'Probe identity conflicts with candidate/provider closure')
        selected[metadata['id']] = shipped_hash(probe)
    staged = {entry['id']: entry['staged_sha256'] for entry in manifest['enabled']}
    if staged != selected:
        return result('FAIL', 'Enabled runtime closure differs from bound candidate/providers/probe')
    launcher_inputs = body['context']['inputs']['launcher'] or {}
    for name, hashed in runtime.get('launcher_files', {}).items():
        matches = [Path(item['path']) for item in launcher_inputs.values()
                   if item['kind'] == 'file' and Path(item['path']).name == name]
        if len(matches) != 1 or file_digest(matches[0]) != hashed:
            return result('FAIL', 'Unbound or mismatched launcher/VM parameter input: ' + name)
    if runtime.get('probe_config_sha256'):
        config = _binding(body, 'launcher', 'probe_config', 'file')
        if config != (rig / CONFIG_RELATIVE).resolve() or file_digest(config) != runtime['probe_config_sha256']:
            return result('FAIL', 'Probe configuration does not match selected context')
    if not runtime.get('java_version'):
        return result('INCOMPLETE', 'Selected Java version was not observed')
    if not set(LIVE_MILESTONES).issubset(manifest['expected_milestones']):
        return result('INCOMPLETE', 'Run was not prepared for every required scenario milestone')
    target = manifest['targets'].get(info.get('id'))
    if not target or Path(target['working']).resolve() != working or target['candidate_sha256'] != body['payload']['sha256']:
        return result('FAIL', 'This candidate is not the exact bound target of this run')
    return None


def _live(body: dict, working: Path, info: dict, reference: tuple[Path, str] | None) -> dict:
    if reference is None:
        return result('INCOMPLETE', 'No bound live scenario supplied')
    rig, run_id = reference
    rig = Path(rig).resolve()
    manifest = read_manifest(rig, run_id)
    log = Path(manifest['log'])
    artifacts = [rig / 'logs' / (run_id + '.manifest.json'), rig / 'logs' / (run_id + '.completed.json'), log]
    before = {str(path): file_digest(path) for path in artifacts}
    mismatch = _run_context(body, working, info, manifest, rig)
    if mismatch is not None:
        return mismatch
    launcher = _binding(body, 'launcher', 'game', 'file')
    evidence = evaluate_run(rig, manifest, log, mods_dir=rig / 'mods', launcher=launcher)
    member = evidence['members'].get(info.get('id')) or {}
    triage = triage_log(log, mods_dir=rig / 'mods')
    after = {str(path): file_digest(path) for path in artifacts}
    if before != after:
        return result('INCOMPLETE', 'Live artifacts changed during evaluation')
    if (evidence['status'] != 'ACCEPTABLE' or evidence.get('manifest_echo') != 'MATCH' or not member.get('ok') or triage['counts']['FATAL'] or triage['counts']['MOD-ERROR']
            or triage['probe']['counts_by_status'].get('FAIL', 0) or triage['caught_exceptions']['distinct']):
        return result('FAIL', 'Bound live evidence has target, provenance, fatal or probe failures', evidence=evidence)
    if not all(evidence['milestones'].get(name) for name in LIVE_MILESTONES):
        return result('INCOMPLETE', 'Required live observations are missing')
    return result('PASS', 'Required bound new-game/campaign/combat log observations passed; no save-upgrade claim',
                  manifest_id=manifest['manifest_id'], run_id=run_id, artifacts=after)


def qualify_case(store: CaseStore, case_id: str, candidate_id: str, *, run_compile: bool = False,
                 live: tuple[Path, str] | None = None) -> dict:
    """Evaluate the declared new-game evidence profile without applying/finalizing anything."""
    candidate = store.load_candidate(case_id, candidate_id)
    case = store.load_case(case_id)['content']
    body, view = candidate['content'], store.workspace(case_id)
    engine = engine_identity()
    dimensions = {name: result('INCOMPLETE', 'Not evaluated') for name in REQUIRED}
    dimensions['save'] = result('NOT_APPLICABLE', 'Existing-save/upgrade support is outside this declared profile, not proven')
    def finish():
        statuses = [dimensions[name]['status'] for name in REQUIRED]
        state = 'REFUSED' if 'FAIL' in statuses else ('INCOMPLETE' if 'INCOMPLETE' in statuses else 'QUALIFIED_FOR_DECLARED_SCOPE')
        return {'schema': 'bridgeforge.qualification', 'schema_version': 1, 'case_id': case_id, 'candidate_id': candidate_id,
                'profile': PROFILE_ID, 'scope': 'new-game', 'unsupported_scopes': ['existing-save-upgrade'], 'state': state,
                'dimensions': dimensions, 'engine_id': engine, 'authority': 'EVIDENCE_EVALUATED_NOT_RELEASE_APPROVAL'}
    if body['target_profile'] != TARGET or case['declared_scope'] != 'local-new-game':
        dimensions['target'] = result('INCOMPLETE', 'Unsupported declared target/scope profile')
        return finish()
    try:
        current = store.assess_candidate(case_id, candidate_id)
        if current['state'] != 'CURRENT':
            dimensions['candidate'] = result('FAIL', 'Candidate/context changed since capture')
            return finish()
        dimensions['candidate'] = result('PASS', 'Current candidate, original and context identities match')
        missing = body['context']['missing_roles']
        dimensions['context'] = result('INCOMPLETE' if missing else 'PASS', 'Missing context roles' if missing else 'Explicit context groups bound', missing=missing)
        info = _load_lenient_json_file(view.working / 'mod_info.json')
        if not isinstance(info, dict) or not isinstance(info.get('id'), str) or not info['id']:
            dimensions['static'] = result('FAIL', 'Mod metadata has no valid identity')
            return finish()
        core = _binding(body, 'core', 'starsector', 'tree')
        target_policy = _binding(body, 'policy', 'target', 'file')
        target_record = _json(target_policy) if target_policy else {}
        core_item = (body['context']['inputs']['core'] or {}).get('starsector') or {}
        target_ok = (type(target_record.get('schema_version')) is int and target_record['schema_version'] == 1 and target_record.get('target') == TARGET['target']
                     and core is not None and target_record.get('core_sha256') == core_item.get('sha256'))
        dimensions['target'] = result('PASS' if target_ok else 'INCOMPLETE', 'Selected target reference matches bound core' if target_ok else 'Bound target/core reference missing or mismatched')
        dimensions['review'], decision = _review(body, candidate, view.working, view.original)
        declared_jars = info.get('jars', [])
        if not isinstance(declared_jars, list):
            dimensions['source_authority'] = result('FAIL', 'Jar declaration must be a list')
            return finish()
        for name in declared_jars:
            if not isinstance(name, str):
                raise ValueError('Invalid declared jar path')
            path = _physical(view.working / name)
            if not path.is_relative_to(view.working) or not path.is_file() or path.suffix.lower() != '.jar':
                dimensions['source_authority'] = result('FAIL', 'Declared jar is absent, unsafe or not a jar')
                return finish()
        jars, loose = _loaded_mod_jars(view.working), discover_loose_scripts(view.working)
        if jars and list(view.working.rglob('*.java')) and (decision or {}).get('runtime_authority') != 'packaged-bytes':
            dimensions['source_authority'] = result('INCOMPLETE', 'Mixed jar/source authority needs an explicit packaged-byte decision')
        else:
            dimensions['source_authority'] = result('PASS', 'Runtime authority is packaged bytes' if jars else 'Runtime authority is current data/loose sources', jars=[str(path) for path in jars])
        dimensions['dependencies'], providers = _dependencies(body, info)
        observed = _worker(view.working, core, providers, body, bool(run_compile and loose and dimensions['dependencies']['status'] == 'PASS')) if core and dimensions['dependencies']['status'] == 'PASS' else {'error': 'Bound core/provider closure unavailable'}
        if 'error' in observed:
            dimensions['static'] = result('INCOMPLETE', observed['error'])
            dimensions['api'] = result('INCOMPLETE', observed['error'])
        else:
            findings = observed['findings']
            blockers = [row for row in findings if row['severity'] in {'critical', 'high'}]
            uncertain = [row for row in findings if row['classification'] in {'UNKNOWN', 'MANUAL', 'REVIEW'}]
            dimensions['static'] = result('FAIL' if blockers else ('INCOMPLETE' if uncertain else 'PASS'), 'Fresh scanner findings retained', findings=findings)
            api_gaps = [row for row in findings if any(word in row['id'] for word in ('api', 'linkage', 'unresolved', 'class-missing', 'ast-unavailable'))]
            dimensions['api'] = result('FAIL' if any(row['severity'] in {'critical', 'high'} for row in api_gaps) else ('INCOMPLETE' if api_gaps else 'PASS'), 'Fresh API/linkage scanner evidence', findings=api_gaps)
        dimensions['compile'] = _compile(observed, loose, run_compile, core, dimensions['dependencies'])
        policy_path = _binding(body, 'policy', 'release', 'file')
        policy = _load_policy(policy_path) if policy_path else None
        entry = policy_entry(policy, info.get('id'), info.get('name')) if policy else None
        rights_ok = isinstance(entry, dict) and isinstance(entry.get('local_only'), bool) and isinstance(entry.get('reason'), str) and bool(entry['reason'].strip())
        dimensions['rights'] = result('PASS' if rights_ok else 'INCOMPLETE', 'Explicit local/restricted policy retained; no publication approval' if rights_ok else 'Explicit mod rights/local-only policy required', local_only=entry.get('local_only') if entry else None)
        dimensions['live'] = _live(body, view.working, info, live)
        if store.assess_candidate(case_id, candidate_id)['state'] != 'CURRENT' or engine_identity() != engine:
            dimensions['candidate'] = result('FAIL', 'Inputs or evaluator changed during qualification')
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        dimensions['candidate'] = result('INCOMPLETE', 'Required evidence unavailable/unsupported: ' + str(exc))
    return finish()
