"""Qualification distinguishes fresh evidence from declarations and incomplete tools."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from bridgeforge import case_qualification as q
from bridgeforge.case_identity import CONTEXT_ROLES, tree_digest, tree_files
from bridgeforge.case_store import CaseStore
from bridgeforge.case_workspace import open_workspace_view
from tests.support import resolved_temp_dir
from tests.test_case_workspace import mod


def fixture(root, target_profile=None):
    workspace = root / 'workspace'; workspace.mkdir()
    for name in ('original', 'working'):
        path = mod(workspace / name)
        (path / 'mod_info.json').write_text(json.dumps({'id': 'synthetic-s1', 'name': 'Synthetic S1',
            'version': '1.0.0', 'gameVersion': '0.98a-RC8', 'author': 'Synthetic', 'description': 'Synthetic fixture'}))
    context = root / 'context'; context.mkdir()
    core = context / 'core'; core.mkdir()
    (core / 'data').mkdir()
    target = context / 'target.json'
    target.write_text(json.dumps({'schema_version': 1, 'target': q.TARGET['target'], 'core_sha256': tree_digest(tree_files(core))}))
    release = context / 'release.json'
    release.write_text(json.dumps({'mods': {'synthetic-s1': {'local_only': True, 'reason': 'Synthetic test only'}}}))
    inputs = {role: {} for role in CONTEXT_ROLES}
    inputs.update(core={'starsector': core}, tools={'python': Path(sys.executable).resolve()},
                  policy={'target': target, 'release': release})
    view = open_workspace_view(workspace)
    store = CaseStore(root / 'state')
    case = store.create_case(view, target_profile=target_profile or q.TARGET, declared_scope='local-new-game')['content']['case_id']
    return store, case, view, inputs


class QualificationTests(unittest.TestCase):
    def test_fresh_worker_does_not_invent_live_acceptance(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            report = q.qualify_case(store, case, candidate['record_id'])
            self.assertEqual(report['state'], 'INCOMPLETE', report)
            self.assertEqual(report['dimensions']['candidate']['status'], 'PASS')
            self.assertEqual(report['dimensions']['target']['status'], 'PASS')
            self.assertEqual(report['dimensions']['compile']['status'], 'NOT_APPLICABLE')
            self.assertEqual(report['dimensions']['live']['status'], 'INCOMPLETE')
            self.assertEqual(report['dimensions']['save']['status'], 'NOT_APPLICABLE')
            self.assertNotIn('worker failed', report['dimensions']['static']['reason'].lower())
            self.assertEqual(store.assess_candidate(case, candidate['record_id'])['state'], 'CURRENT')

    def test_changed_candidate_refused_before_scanning(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            (view.working / 'new.txt').write_text('changed')
            with patch.object(q, '_worker', side_effect=AssertionError('must not scan stale inputs')):
                report = q.qualify_case(store, case, candidate['record_id'])
            self.assertEqual(report['state'], 'REFUSED')

    def test_boolean_schema_does_not_qualify_target(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            path = inputs['policy']['target']; data = json.loads(path.read_text()); data['schema_version'] = True
            path.write_text(json.dumps(data))
            candidate = store.add_candidate(case, inputs=inputs)
            with patch.object(q, '_worker', return_value={'error': 'not executed'}):
                report = q.qualify_case(store, case, candidate['record_id'])
            self.assertEqual(report['dimensions']['target']['status'], 'INCOMPLETE')

    def test_missing_declared_jar_fails_without_fallback(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            path = view.working / 'mod_info.json'; data = json.loads(path.read_text()); data['jars'] = ['jars/missing.jar']
            path.write_text(json.dumps(data))
            candidate = store.add_candidate(case, inputs=inputs)
            report = q.qualify_case(store, case, candidate['record_id'])
            self.assertEqual(report['dimensions']['source_authority']['status'], 'FAIL', report)

    def test_javac_pass_with_unavailable_janino_is_incomplete(self):
        source = Path('Script.java').resolve()
        observed = {'compile': {'status': 'PASS', 'javac_returncode': 0, 'janino': {'status': 'UNAVAILABLE'}}}
        self.assertEqual(q._compile(observed, [source], True, Path('core'), {'status': 'PASS'})['status'], 'INCOMPLETE')

    def test_compile_requires_complete_source_coverage(self):
        source = Path('Script.java').resolve()
        observed = {'compile': {'status': 'PASS', 'javac_returncode': 0, 'janino': {'status': 'PASS'},
                                'mod': str(source.parent), 'files': []}}
        self.assertEqual(q._compile(observed, [source], True, Path('core'), {'status': 'PASS'})['status'], 'INCOMPLETE')
        observed['compile']['files'] = [source.name]
        self.assertEqual(q._compile(observed, [source], True, Path('core'), {'status': 'PASS'})['status'], 'PASS')

    def test_dependency_extras_and_cycles_are_not_qualified(self):
        with resolved_temp_dir() as root:
            provider = mod(root / 'provider')
            body = {'context': {'inputs': {'dependencies': {'synthetic-s1': {'kind': 'tree', 'path': str(provider)}}}}}
            status, _ = q._dependencies(body, {'id': 'other'})
            self.assertEqual(status['status'], 'INCOMPLETE')
            (provider / 'mod_info.json').write_text(json.dumps({'id': 'synthetic-s1', 'dependencies': ['synthetic-s1']}))
            status, _ = q._dependencies(body, {'id': 'other', 'dependencies': ['synthetic-s1']})
            self.assertEqual(status['status'], 'INCOMPLETE')

    def test_unbound_python_never_starts_worker(self):
        body = {'context': {'inputs': {'tools': {}}}}
        with patch.object(q.subprocess, 'run', side_effect=AssertionError('unbound tool')):
            self.assertIn('error', q._worker(Path('working'), Path('core'), [], body, False))


class BoundLiveQualificationTests(unittest.TestCase):
    def prepare(self, root, extra=False, echo=True, profile=None):
        from tests.bound_runs import make_rig, stage, MENU, LOAD, COMBAT, CONTENT_IDS
        from bridgeforge.run_manifest import prepare_run, release_run
        store, case, view, inputs = fixture(root, target_profile=profile)
        rig = make_rig(root, {'unbound': []} if extra else None)
        inputs['core'] = {'starsector': (root / 'core_real')}
        target = inputs['policy']['target']
        target.write_text(json.dumps({'schema_version': 1, 'target': q.TARGET['target'],
            'core_sha256': tree_digest(tree_files(root / 'core_real'))}))
        jdk = root / 'jdk'; (jdk / 'bin').mkdir(parents=True)
        import os
        java = jdk / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
        java.write_bytes(b'synthetic executable, never run')
        (jdk / 'release').write_text('JAVA_VERSION="25.0.4"')
        launcher = rig / 'game.bat'; launcher.write_text('"' + str(java) + '" -version')
        inputs['tools']['jdk'] = jdk
        inputs['launcher'] = {'game': launcher}
        candidate = store.add_candidate(case, inputs=inputs)
        stage(rig, {'synthetic-s1': view.root}, ['unbound'] if extra else [])
        manifest = prepare_run(rig, 'synthetic-qualification', 'live', targets=['synthetic-s1'],
            expected=list(q.profile_milestones(candidate['content'])), launcher=launcher)
        lines = [MENU, LOAD, CONTENT_IDS, COMBAT, 'BF-PROBE|0.3.2|probe|INFO|campaign|START',
                 'BF-PROBE|0.3.2|probe|INFO|campaign|END']
        if echo:
            lines.append('BF-PROBE|0.2.9|run|manifest_id=' + manifest['manifest_id'])
        Path(manifest['log']).write_text('\n'.join(lines) + '\n')
        release_run(rig, manifest['run_id'], launcher=launcher)
        return store, case, candidate, view, rig, manifest

    def test_exact_synthetic_bound_run_and_post_test_drift(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = self.prepare(root)
            report = q.qualify_case(store, case, candidate['record_id'], live=(rig, manifest['run_id']))
            self.assertEqual(report['state'], 'QUALIFIED_FOR_DECLARED_SCOPE', report)
            result = report['dimensions']['live']
            self.assertEqual(result['status'], 'PASS', result)
            (rig / 'mods' / view.root.name / 'changed.txt').write_text('post-test drift')
            result = q._live(candidate['content'], view.working, {'id': 'synthetic-s1'}, (rig, manifest['run_id']))
            self.assertEqual(result['status'], 'FAIL', result)

    def test_unbound_runtime_provider_fails_even_when_r1_is_acceptable(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = self.prepare(root, extra=True)
            result = q._live(candidate['content'], view.working, {'id': 'synthetic-s1'}, (rig, manifest['run_id']))
            self.assertEqual(result['status'], 'FAIL', result)
            self.assertIn('closure', result['reason'])

    def test_legacy_log_without_manifest_echo_cannot_qualify(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = self.prepare(root, echo=False)
            result = q._live(candidate['content'], view.working, {'id': 'synthetic-s1'}, (rig, manifest['run_id']))
            self.assertEqual(result['status'], 'FAIL', result)


class ReviewQualificationTests(unittest.TestCase):
    def test_changed_inputs_require_matching_owner_policy(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            (view.working / 'changed.txt').write_text('changed')
            candidate = store.add_candidate(case, inputs=inputs)
            status, decision = q._review(candidate['content'], candidate, view.working, view.original)
            self.assertEqual(status['status'], 'INCOMPLETE')
            review = root / 'review.json'
            review.write_text(json.dumps({'schema': 'bridgeforge.owner-review', 'schema_version': 1,
                'actor': 'owner', 'decision': 'APPROVE_FOR_DECLARED_NEW_GAME', 'scope': q.PROFILE_ID,
                'subject_id': q.review_subject(candidate), 'reason': 'Synthetic policy fixture'}))
            inputs['source_authority'] = {'review': review}
            selected = store.add_candidate(case, inputs=inputs)
            status, decision = q._review(selected['content'], selected, view.working, view.original)
            self.assertEqual(status['status'], 'PASS', status)
            (view.working / 'changed.txt').write_text('different inputs')
            selected = store.add_candidate(case, inputs=inputs)
            status, decision = q._review(selected['content'], selected, view.working, view.original)
            self.assertEqual(status['status'], 'INCOMPLETE')

    def test_input_mutation_during_worker_refuses_qualification(self):
        with resolved_temp_dir() as root:
            store, case, view, inputs = fixture(root)
            candidate = store.add_candidate(case, inputs=inputs)
            def mutate(*args):
                (view.working / 'changed.txt').write_text('concurrent change')
                return {'findings': [], 'compile': None}
            with patch.object(q, '_worker', side_effect=mutate):
                report = q.qualify_case(store, case, candidate['record_id'])
            self.assertEqual(report['state'], 'REFUSED', report)
            self.assertEqual(report['dimensions']['candidate']['status'], 'FAIL')


class VersionedCampaignObligationTests(unittest.TestCase):
    def test_v2_campaign_checks_do_not_require_or_imply_saved_load(self):
        from tests.bound_runs import LOAD
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = BoundLiveQualificationTests().prepare(root)
            log = Path(manifest['log'])
            log.write_text(log.read_text().replace(LOAD + '\n', ''))
            report = q.qualify_case(store, case, candidate['record_id'], live=(rig, manifest['run_id']))
            self.assertEqual(report['state'], 'QUALIFIED_FOR_DECLARED_SCOPE', report)
            self.assertEqual(report['profile'], 'rc8-local-new-game/v2')
            self.assertIn('existing-save-upgrade', report['unsupported_scopes'])

    def test_v1_still_requires_saved_load_even_with_completed_campaign_checks(self):
        from tests.bound_runs import LOAD
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = BoundLiveQualificationTests().prepare(root, profile=q.LEGACY_TARGET)
            log = Path(manifest['log'])
            original = log.read_text()
            legacy_only = '\n'.join(line for line in original.splitlines() if '|probe|INFO|campaign|' not in line and '|content-ids|' not in line) + '\n'
            log.write_text(legacy_only)
            self.assertEqual(q.qualify_case(store, case, candidate['record_id'], live=(rig, manifest['run_id']))['state'],
                             'QUALIFIED_FOR_DECLARED_SCOPE')
            log.write_text(original.replace(LOAD + '\n', ''))
            report = q.qualify_case(store, case, candidate['record_id'], live=(rig, manifest['run_id']))
            self.assertEqual(report['state'], 'REFUSED')
            self.assertEqual(report['profile'], 'rc8-local-new-game/v1')

    def test_v2_saved_load_does_not_replace_missing_campaign_completion(self):
        with resolved_temp_dir() as root:
            store, case, candidate, view, rig, manifest = BoundLiveQualificationTests().prepare(root)
            log = Path(manifest['log'])
            log.write_text(log.read_text().replace('BF-PROBE|0.3.2|probe|INFO|campaign|END', 'not a completion'))
            self.assertEqual(q.qualify_case(store, case, candidate['record_id'], live=(rig, manifest['run_id']))['state'], 'REFUSED')
