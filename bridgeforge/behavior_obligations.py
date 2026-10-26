"""S3 read-only, case-bound behavior obligations; discovery is never runtime proof."""
from __future__ import annotations

from pathlib import Path
import tempfile
import sys

from .behavior_discovery import build_archaeology, build_behavior_model
from .bytecode.java_toolchain import find_jdk
from .case_identity import digest
from .case_qualification import engine_identity
from .case_store import CaseStore
from .safeio import atomic_write_json

SCHEMA = 'bridgeforge.behavior-obligations'
SCHEMA_VERSION = 1
FAMILIES = ('generation', 'campaign-economy', 'combat-callbacks', 'dependency-integration',
            'long-running-campaign', 'upgrade-reload')


def _current(store: CaseStore, case_id: str, candidate_id: str) -> None:
    if store.assess_candidate(case_id, candidate_id)['state'] != 'CURRENT':
        raise ValueError('Behavior planning requires current candidate and context inputs')


def _models(root: Path, core: Path | None, providers: list[Path]) -> tuple[dict, dict]:
    # Reuse D-series discovery; only the adapter file is temporary, never an input file.
    architecture = build_archaeology(root, vanilla_core=core, provider_roots=providers or [root])
    with tempfile.TemporaryDirectory(prefix='bf-behavior-obligations-') as temporary:
        path = Path(temporary) / 'architecture.json'
        atomic_write_json(path, architecture)
        model = build_behavior_model(path)
    # D-series's adapter location is not part of a reproducible case identity.
    model.pop('input_architecture', None)
    return architecture, model


def plan_behavior_obligations(store: CaseStore, case_id: str, candidate_id: str) -> dict:
    """Discover original/candidate hypotheses freshly and emit unresolved obligations.

    This is a library planning surface, not a qualification adapter. It accepts no PASS
    receipts, expected-change approvals or historical runtime labels. Even identical
    static inventories cannot establish preserved behavior or a reference runtime.
    """
    candidate = store.load_candidate(case_id, candidate_id)
    _current(store, case_id, candidate_id)
    engine = engine_identity()
    view = store.workspace(case_id)
    body = candidate['content']; groups = body['context']['inputs']
    python = (groups['tools'] or {}).get('python')
    if python is None or python['kind'] != 'file' or Path(python['path']) != Path(sys.executable).resolve():
        raise ValueError('Behavior planning requires the bound running Python')
    cores = groups['core'] or {}
    core = cores.get('starsector')
    if core is not None and core['kind'] != 'tree':
        raise ValueError('Behavior core must be a bound physical tree')
    core_path = Path(core['path']) if core else None
    providers = []
    for item in (groups['dependencies'] or {}).values():
        if item['kind'] != 'tree':
            raise ValueError('Behavior providers must be bound physical trees')
        providers.append(Path(item['path']))
    providers.sort()
    needs_java = any(list(root.rglob('*.java')) or list(root.rglob('*.jar'))
                     for root in (view.original, view.working))
    if needs_java:
        selected = find_jdk(); jdk = (groups['tools'] or {}).get('jdk')
        if selected is None or jdk is None or jdk['kind'] != 'tree' or Path(jdk['path']) != selected.home:
            raise ValueError('Behavior Java analysis requires the bound configured JDK')
    original_architecture, original = _models(view.original, core_path, providers)
    architecture, working = _models(view.working, core_path, providers)
    originals = {item['id']: item for item in original['behaviors']}
    current = {item['id']: item for item in working['behaviors']}
    obligations = []
    for key in sorted(set(originals) | set(current)):
        before, after = originals.get(key), current.get(key)
        seed = after or before
        obligations.append({'behavior_id': key, 'entry_point': seed['entry_point'],
                            'discovery': 'BOTH' if before and after else 'CANDIDATE_ONLY' if after else 'ORIGINAL_ONLY',
                            'original_static': before, 'candidate_static': after,
                            'status': 'UNKNOWN', 'criticality': 'NOT_OWNER_SELECTED',
                            'reference_observation': 'UNAVAILABLE', 'candidate_observation': 'NOT_OBSERVED',
                            'deviation_authority': 'NONE', 'impact': 'UNRESOLVED',
                            'required_families': list(FAMILIES)})
    residual = [{'behavior_id': item['behavior_id'], 'action': 'Select criticality and observe or explicitly bound this feature',
                 'families': list(FAMILIES)} for item in obligations]
    residual.append({'behavior_id': None, 'action': 'Review discovery completeness; undiscovered behavior is unknown',
                     'families': list(FAMILIES)})
    content = {'schema': SCHEMA, 'schema_version': SCHEMA_VERSION, 'case_id': case_id,
               'candidate_id': candidate_id, 'context_id': digest(body['context']),
               'engine_id': engine, 'target_profile': body['target_profile'],
               'state': 'INCOMPLETE', 'mode': 'READ_ONLY_STATIC_PLAN',
               'source_authority': 'NOT_ESTABLISHED', 'resolution': 'BOUND_INPUTS_NOT_QUALIFIED',
               'reference': {'kind': 'ORIGINAL_STATIC_INVENTORY', 'runtime': 'UNAVAILABLE',
                             'original_id': body['original']['sha256']},
               'discovery_ids': {'original': digest(original_architecture), 'candidate': digest(architecture)},
               'obligations': obligations, 'selected_families': list(FAMILIES),
               'family_controls': {name: {'healthy': 'NOT_OBSERVED', 'known_bug': 'NOT_OBSERVED'} for name in FAMILIES},
               'residual_human_tests': residual,
               'qualification': 'NOT_EVALUATED', 'saved_upgrade': 'NOT_AUTHORIZED_OR_OBSERVED',
               'scope_limit': 'Static hypotheses only; no preserved-feature percentage or runtime equivalence'}
    # Reject races in candidate, core/providers, rules/policy, original or implementation.
    _current(store, case_id, candidate_id)
    if engine_identity() != engine:
        raise ValueError('Behavior implementation changed during discovery')
    return {**content, 'plan_id': digest(content)}
