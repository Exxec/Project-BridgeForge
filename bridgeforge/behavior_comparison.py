"""S3 exact scenario-assertion comparisons; never whole-feature equivalence."""
from __future__ import annotations

import json
from pathlib import Path

from .behavior_obligations import plan_behavior_obligations
from .behavior_observations import observe_behavior_scenario
from .case_identity import digest, file_digest
from .case_qualification import engine_identity
from .case_store import CaseStore, _unique
from .case_workspace import _physical
from .scan.scan_json import _load_lenient_json_file

SCOPE = 'probe-assertion-vector/v1'


def _endpoint(selection: dict) -> tuple[CaseStore, dict, dict]:
    required = {'store', 'case_id', 'candidate_id', 'scenario', 'rig', 'run_id'}
    if not isinstance(selection, dict) or set(selection) - (required | {'definition_directory'}) or required - set(selection):
        raise ValueError('Scenario selector requires exact store/case/candidate/scenario/rig/run identities')
    for key in ('store', 'rig', 'definition_directory'):
        value = selection.get(key)
        if value is not None and (not isinstance(value, (str, Path)) or not Path(value).is_absolute()):
            raise ValueError('Scenario selector paths must be explicit absolute paths')
    store = CaseStore(Path(selection['store']))
    case_id, candidate_id = selection['case_id'], selection['candidate_id']
    plan = plan_behavior_obligations(store, case_id, candidate_id)
    directory = selection.get('definition_directory')
    observation = observe_behavior_scenario(store, case_id, candidate_id, plan, scenario=selection['scenario'],
        rig=Path(selection['rig']), run_id=selection['run_id'],
        definition_directory=Path(directory) if directory is not None else None)
    return store, plan, observation


def _vector(observation: dict) -> list[dict]:
    checked = observation.get('scenario_result')
    rows = checked.get('probe_assertions') if isinstance(checked, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError('Observed named probe assertions are unavailable')
    result = []
    for row in rows:
        assertion = row['assertion']
        result.append({'check': assertion['check'], 'status': assertion['status'],
                       'subject_pattern': assertion['subject_pattern'],
                       'min_count': assertion.get('min_count', 0 if 'max_count' in assertion else 1),
                       'max_count': assertion.get('max_count'), 'matched_count': row['matched_count']})
    return result


def _approval(path: Path, subject_id: str) -> tuple[dict, str]:
    path = _physical(Path(path))
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Deviation decision exceeds 1 MiB')
    before = file_digest(path)
    decision = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique)
    if (not isinstance(decision, dict) or set(decision) != {'schema_version', 'scope', 'subject_id', 'actor', 'decision', 'reason', 'owner_words'}
            or type(decision['schema_version']) is not int or decision['schema_version'] != 1
            or decision['scope'] != SCOPE or decision['subject_id'] != subject_id or decision['actor'] != 'OWNER'
            or decision['decision'] not in {'APPROVE_EXACT_SCENARIO_DEVIATION', 'REVOKE'}
            or any(not isinstance(decision[k], str) or not decision[k].strip() for k in ('reason', 'owner_words'))):
        raise ValueError('Deviation requires exact subject, scoped owner decision and review reason/words')
    if file_digest(path) != before:
        raise ValueError('Deviation authority changed during evaluation')
    return decision, before


def _mod_id(endpoint):
    store, plan, _ = endpoint
    info = _load_lenient_json_file(store.workspace(plan['case_id']).working / 'mod_info.json')
    if not isinstance(info, dict) or not isinstance(info.get('id'), str) or not info['id']:
        raise ValueError('Comparison subject mod identity is unavailable')
    return info['id']


def compare_behavior_scenarios(candidate: dict, reference: dict | None = None, *, deviation: Path | None = None) -> dict:
    """Freshly observe both named runs; a saved PASS or similarity label is not input.

    Comparability is limited to the same mod/family and ordered assertion signatures.
    Missing reference never becomes equivalence. Approval cannot waive a failing
    candidate assertion or identity gate; update the reviewed contract and rerun instead.
    """
    engine = engine_identity()
    current = _endpoint(candidate)
    prior = _endpoint(reference) if reference is not None else None
    observed = current[2]
    content = {'schema': 'bridgeforge.behavior-comparison', 'schema_version': 1,
               'scope': SCOPE, 'engine_id': engine, 'candidate_observation': observed,
               'reference_observation': prior[2] if prior else None,
               'qualification': 'NOT_EVALUATED', 'feature_preservation': 'UNKNOWN',
               'family_support': 'NOT_ESTABLISHED', 'save_upgrade': 'NOT_EVALUATED',
               'deviation_authority': None,
               'comparison_performed': False,
               'scope_limit': 'Only these ordered named probe assertion vectors; not original-runtime or whole-feature equivalence'}
    if observed['state'] == 'REGRESSION_DETECTED':
        content['state'] = 'REGRESSION_DETECTED'
    elif observed['state'] != 'ASSERTIONS_OBSERVED':
        content['state'] = 'CANDIDATE_INCOMPLETE'
    elif prior is None:
        content['state'] = 'REFERENCE_UNAVAILABLE'
    elif prior[2]['state'] != 'ASSERTIONS_OBSERVED':
        content['state'] = 'REFERENCE_INCOMPLETE'
    else:
        a, b = _vector(prior[2]), _vector(observed)
        signature = lambda rows: [{key: row[key] for key in ('check', 'status', 'subject_pattern')} for row in rows]
        # A different mod/family or predicate is a new comparison design, not a waiver.
        if (_mod_id(prior) != _mod_id(current) or prior[2]['family'] != observed['family'] or signature(a) != signature(b)
                or prior[2]['behavior_ids'] != observed['behavior_ids']):
            raise ValueError('Incomparable behavior family, feature IDs or assertion predicates')
        subject = {'scope': SCOPE, 'engine_id': engine, 'reference_observation_id': prior[2]['observation_id'],
                   'candidate_observation_id': observed['observation_id'], 'reference_vector': a, 'candidate_vector': b}
        content.update(subject_id=digest(subject), reference_vector=a, candidate_vector=b, comparison_performed=True,
                       state='ASSERTION_VECTOR_MATCH' if a == b else 'OBSERVED_DIFFERENCE')
        if deviation is not None:
            if a == b:
                raise ValueError('No observed difference to approve')
            decision, hashed = _approval(deviation, content['subject_id'])
            content['deviation_authority'] = {'path': str(_physical(deviation)), 'sha256': hashed, 'decision': decision}
            if decision['decision'] == 'APPROVE_EXACT_SCENARIO_DEVIATION':
                content['state'] = 'EXPECTED_SCOPED_DEVIATION'
    if deviation is not None and content['deviation_authority'] is None:
        raise ValueError('Deviation cannot replace missing observations or waive failed assertions')
    # Recheck both subjects and all observed artifacts after evaluating the other run/decision.
    for store, plan, observation in [current] + ([prior] if prior else []):
        if store.assess_candidate(plan['case_id'], plan['candidate_id'])['state'] != 'CURRENT':
            raise ValueError('Scenario comparison inputs became stale')
        if any(file_digest(Path(path)) != hashed for path, hashed in observation['artifacts'].items()):
            raise ValueError('Scenario comparison evidence changed during evaluation')
    if engine_identity() != engine:
        raise ValueError('Scenario comparison engine changed during evaluation')
    if content['deviation_authority'] is not None and file_digest(deviation) != content['deviation_authority']['sha256']:
        raise ValueError('Deviation authority changed before publication')
    return {**content, 'comparison_id': digest(content)}
