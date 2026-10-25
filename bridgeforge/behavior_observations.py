"""S3 exact-input scenario observations; passing assertions are not feature equivalence."""
from __future__ import annotations

from pathlib import Path
import re

from . import scenarios
from .behavior_obligations import FAMILIES, plan_behavior_obligations
from .case_identity import digest, file_digest
from .case_qualification import _live, engine_identity
from .case_store import CaseStore
from .case_workspace import _physical
from .run_manifest import read_manifest
from .scan.scanner import _load_lenient_json_file


def _definition(name: str, plan: dict, candidate: dict, directory: Path | None = None) -> tuple[Path, dict]:
    if not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', name) is None:
        raise ValueError('Invalid behavior scenario name')
    path = _physical((Path(directory) if directory is not None else scenarios.SCENARIOS_DIR) / f'{name}.json')
    bound = (candidate['content']['context']['inputs']['rules'] or {}).get('scenario.' + name)
    if not bound or bound['kind'] != 'file' or Path(bound['path']) != path:
        raise ValueError('Scenario definition must be bound in candidate rules')
    definition = scenarios.load_scenario(name) if directory is None else scenarios.load_scenario(name, directory=directory)
    if (type(definition.get('schema_version')) is not int or definition['schema_version'] != 1
            or definition.get('name') != name or definition.get('family') not in FAMILIES):
        raise ValueError('Unsupported behavior scenario definition/family')
    selected = definition.get('behavior_ids')
    known = {item['behavior_id'] for item in plan['obligations']}
    if (not isinstance(selected, list) or not selected or any(not isinstance(item, str) for item in selected)
            or len(set(selected)) != len(selected) or not set(selected).issubset(known)):
        raise ValueError('Scenario must select known unique plan behavior IDs')
    if (definition['family'] == 'upgrade-reload' or definition.get('compat_set')
            or definition.get('probe_setups') or definition.get('track_entities') or definition.get('snapshot_tag')):
        raise ValueError('Save, setup, tracking and compatibility-set scenarios need further evidence adapters')
    expect = definition.get('expect')
    if not isinstance(expect, dict) or set(expect) - {'probe', 'save'} or expect.get('save') not in (None, []):
        raise ValueError('Saved-state assertions require a lineage adapter')
    assertions = expect.get('probe')
    if not isinstance(assertions, list) or not assertions:
        raise ValueError('Behavior observations require nonempty probe assertions')
    positive = False
    for assertion in assertions:
        if not isinstance(assertion, dict) or set(assertion) - {'check', 'status', 'subject_pattern', 'min_count', 'max_count'}:
            raise ValueError('Unsupported probe assertion fields')
        for field in ('check', 'subject_pattern'):
            value = assertion.get(field)
            if not isinstance(value, str) or not value or value == '*':
                raise ValueError('Behavior assertions need explicit check and subject patterns')
            re.compile(value)
        if assertion.get('status') not in {'OK', 'INFO', 'FAIL', 'WARN'}:
            raise ValueError('Behavior assertions need an explicit status')
        low = assertion.get('min_count', 1 if 'max_count' not in assertion else 0)
        high = assertion.get('max_count')
        if type(low) is not int or low < 0 or (high is not None and (type(high) is not int or high < low)):
            raise ValueError('Behavior assertion counts must be nonnegative integer bounds')
        positive |= low > 0 and assertion['status'] in {'OK', 'INFO'}
    if not positive:
        raise ValueError('Absence-only assertions do not establish an observation')
    return path, definition


def observe_behavior_scenario(store: CaseStore, case_id: str, candidate_id: str, plan: dict,
                              *, scenario: str, rig: Path, run_id: str, definition_directory: Path | None = None) -> dict:
    """Recheck R1 identity and named assertions without launching or accepting anything.

    Rebuild the plan so a forged/rehashed plan or obsolete hypothesis cannot select
    invented behavior. Output covers only these candidate-log assertions. Reference
    equivalence, deviations, family controls and whole-case qualification stay open.
    """
    current = plan_behavior_obligations(store, case_id, candidate_id)
    if plan != current:
        raise ValueError('Behavior plan is stale, altered or belongs to another candidate')
    candidate = store.load_candidate(case_id, candidate_id)
    path, definition = _definition(scenario, plan, candidate, definition_directory)
    rig = Path(rig).resolve()
    manifest = read_manifest(rig, run_id)
    if manifest['scenario'] != scenario:
        raise ValueError('Run was not prepared for this named behavior scenario')
    view = store.workspace(case_id)
    info = _load_lenient_json_file(view.working / 'mod_info.json')
    if definition.get('subject_mod') != info.get('id'):
        raise ValueError('Scenario subject does not match candidate mod')
    enabled = {item['id'] for item in manifest['enabled']}
    mods, extra = definition.get('mods', []), definition.get('extra_mods', [])
    if not isinstance(mods, list) or not isinstance(extra, list):
        raise ValueError('Scenario mod declarations must be lists')
    declared = mods + extra
    probe = (candidate['content']['context']['inputs']['tools'] or {}).get('probe')
    probe_ids = set()
    if probe:
        probe_ids.add(_load_lenient_json_file(Path(probe['path']) / 'mod_info.json')['id'])
    if not declared or not all(isinstance(item, str) for item in declared) or set(declared) != enabled - probe_ids:
        raise ValueError('Scenario enabled mod declaration differs from runtime')
    paths = [path, rig / 'logs' / f'{run_id}.manifest.json', rig / 'logs' / f'{run_id}.completed.json', Path(manifest['log'])]
    before = {str(item): file_digest(item) for item in paths}
    live = _live(candidate['content'], view.working, info, (rig, run_id))
    checked = None
    if live['status'] == 'PASS':
        checked = (scenarios.scenario_check(scenario, Path(manifest['log'])) if definition_directory is None
                   else scenarios.scenario_check(scenario, Path(manifest['log']), directory=definition_directory))
    after = {str(item): file_digest(item) for item in paths}
    if (before != after or store.assess_candidate(case_id, candidate_id)['state'] != 'CURRENT'
            or engine_identity() != plan['engine_id']):
        raise ValueError('Behavior observation inputs or artifacts changed during evaluation')
    state = ('ASSERTIONS_OBSERVED' if checked and checked['status'] == 'PASS' else
             'REGRESSION_DETECTED' if checked else 'REFUSED' if live['status'] == 'FAIL' else 'INCOMPLETE')
    content = {'schema': 'bridgeforge.behavior-observation', 'schema_version': 1,
               'case_id': case_id, 'candidate_id': candidate_id, 'context_id': plan['context_id'],
               'plan_id': plan['plan_id'], 'engine_id': plan['engine_id'],
               'scenario': scenario, 'family': definition['family'], 'behavior_ids': definition['behavior_ids'],
               'manifest_id': manifest['manifest_id'], 'run_id': run_id, 'artifacts': before,
               'state': state, 'live': live, 'scenario_result': checked,
               'reference_observation': 'UNAVAILABLE', 'feature_preservation': 'UNKNOWN',
               'deviation_authority': 'NONE', 'family_control_qualification': 'NOT_EVALUATED',
               'qualification': 'NOT_EVALUATED', 'saved_upgrade': 'NOT_AUTHORIZED_OR_OBSERVED',
               'residual_human_tests': plan['residual_human_tests'],
               'scope_limit': 'Only these candidate scenario assertions; not reference equivalence or whole-family support'}
    return {**content, 'observation_id': digest(content)}
