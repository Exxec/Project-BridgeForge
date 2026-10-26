"""Production portfolio boundaries, exact-input resume and owned subprocess recovery."""
import json
import io
from contextlib import redirect_stdout, redirect_stderr
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import psutil

from bridgeforge.case_qualification import TARGET
from bridgeforge.cli import main
from bridgeforge import portfolio
from bridgeforge.portfolio import output_lease, scan_portfolio
from bridgeforge.portfolio_process import AnalysisProcess
from bridgeforge.safeio import atomic_write_json
from tests.support import resolved_temp_dir
from tests.test_case_qualification import fixture


def setup(root):
    store, case, view, inputs = fixture(root)
    candidate = store.add_candidate(case, inputs=inputs)
    selected = [{'case_id': case, 'candidate_id': candidate['record_id']}]
    return store, selected, view, inputs, root / 'portfolio'


class PortfolioTests(unittest.TestCase):
    def test_real_worker_resume_and_corrupt_recompute(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            result = scan_portfolio(store, selected, output, memory_mib=512, quiet=True, reuse_parses=True)
            self.assertEqual(result['state'], 'COMPLETE', result)
            self.assertEqual(result['cases'][0]['state'], 'ANALYZED')
            self.assertEqual(result['qualification'], 'NOT_EVALUATED')
            self.assertEqual(result['max_active_workers'], 1)
            with patch('bridgeforge.portfolio.AnalysisProcess', side_effect=AssertionError('must reuse')):
                resumed = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(resumed['cases'][0]['state'], 'REUSED')
            raw = Path(resumed['cases'][0]['raw'])
            atomic_write_json(raw, {'altered': True})
            fresh = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(fresh['cases'][0]['state'], 'ANALYZED')
            self.assertNotEqual(fresh['cases'][0]['raw'], str(raw))
            self.assertEqual(json.loads(raw.read_text()), {'altered': True})

    def test_stale_inputs_and_duplicate_aliases_refused_before_launch(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            with self.assertRaisesRegex(ValueError, 'aliases'):
                scan_portfolio(store, selected * 2, output, memory_mib=512)
            (view.working / 'new.txt').write_text('changed')
            with patch('bridgeforge.portfolio.AnalysisProcess', side_effect=AssertionError('must refuse')):
                with self.assertRaisesRegex(ValueError, 'Stale'):
                    scan_portfolio(store, selected, output, memory_mib=512)

    def test_output_overlap_and_unknown_providers_refused(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            for path in (view.root / 'outputs', store.root / 'outputs', inputs['core']['starsector'] / 'output'):
                with self.assertRaisesRegex(ValueError, 'separate'):
                    scan_portfolio(store, selected, path, memory_mib=512)
            inputs['dependencies'] = None
            selected[0]['candidate_id'] = store.add_candidate(selected[0]['case_id'], inputs=inputs)['record_id']
            with self.assertRaisesRegex(ValueError, 'Provider selection'):
                scan_portfolio(store, selected, output, memory_mib=512)

    def test_kernel_lease_refuses_active_owner_and_releases(self):
        with resolved_temp_dir() as root:
            with output_lease(root):
                with self.assertRaisesRegex(ValueError, 'active coordinator'):
                    with output_lease(root):
                        self.fail('second owner acquired the lease')
            with output_lease(root):
                pass

    def test_cancellation_timeout_and_budget_leave_no_success_receipt(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            cancelled = scan_portfolio(store, selected, output, memory_mib=512, cancelled=lambda: True, quiet=True)
            self.assertEqual(cancelled['stop_reason'], 'CANCELLED')
            timed = scan_portfolio(store, selected, output, memory_mib=512, timeout=.001, quiet=True)
            self.assertEqual(timed['cases'][0]['state'], 'TIMEOUT')
            budget = scan_portfolio(store, selected, output, memory_mib=1, quiet=True)
            self.assertEqual(budget['stop_reason'], 'MEMORY_STOP')
            self.assertFalse(list(output.glob('attempts/*/*/receipt.json')))
            resumed = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(resumed['state'], 'COMPLETE')

    def test_same_version_context_change_requires_new_candidate(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            rule = root / 'rule.json'; rule.write_text('{"v":1}')
            inputs['rules']['test'] = rule
            selected[0]['candidate_id'] = store.add_candidate(selected[0]['case_id'], inputs=inputs)['record_id']
            first = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            rule.write_text('{"v":2}')
            with self.assertRaisesRegex(ValueError, 'Stale'):
                scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            selected[0]['candidate_id'] = store.add_candidate(selected[0]['case_id'], inputs=inputs)['record_id']
            fresh = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(fresh['cases'][0]['state'], 'ANALYZED')
            self.assertNotEqual(first['cases'][0]['raw'], fresh['cases'][0]['raw'])

    def test_invalid_limits(self):
        with resolved_temp_dir() as root:
            store, selected, _, _, output = setup(root)
            for kwargs in ({'jobs': 3}, {'jobs': True}, {'memory_mib': 0}, {'timeout': float('nan')}, {'timeout': 0}):
                with self.assertRaises(ValueError):
                    scan_portfolio(store, selected, output, **({'memory_mib': 512} | kwargs))

    @unittest.skipUnless(os.name == 'nt', 'Windows native current-directory limit')
    def test_windows_deep_attempt_path_and_actionable_limit(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, _ = setup(root)
            output = root / ('x' * (180 - len(str(root))))
            result = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(result['state'], 'COMPLETE', result)
            self.assertLess(len(str(Path(result['cases'][0]['raw']).parent)), 240)
            with self.assertRaisesRegex(ValueError, 'shorter output'):
                scan_portfolio(store, selected, output / ('x' * 80), memory_mib=512, quiet=True)

    def test_cli_explicit_plan_and_schema_refusal(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            selection = root / 'selection.json'
            atomic_write_json(selection, {'schema_version': 1, 'cases': selected})
            args = ['portfolio-scan', str(selection), '--store', str(store.root), '--output', str(output),
                    '--memory-mib', '512', '--quiet', '--json']
            stream = io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(stream.getvalue())['state'], 'COMPLETE')
            atomic_write_json(selection, {'schema_version': True, 'cases': selected})
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)

    def test_changed_engine_and_reused_artifact_drift_refuse_success(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            engine = portfolio.engine_identity()
            with patch.object(portfolio, 'engine_identity', side_effect=[engine, '0' * 64]):
                result = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(result['cases'][0]['state'], 'STALE')
            current = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(current['cases'][0]['state'], 'ANALYZED')
            raw = Path(current['cases'][0]['raw'])
            check = portfolio._fresh
            calls = []
            def drift(rows):
                errors = check(rows)
                calls.append(1)
                if len(calls) == 2:
                    atomic_write_json(raw, {'altered': 'during postflight'})
                return errors
            with patch.object(portfolio, '_fresh', side_effect=drift):
                result = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(result['cases'][0]['state'], 'STALE')

    def test_cancel_after_completed_worker_preserves_receipt_and_reaps_other(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            other = root / 'other'; other.mkdir()
            _, _, view2, inputs2 = fixture(other)
            case2 = store.create_case(view2, target_profile=TARGET, declared_scope='local-new-game')['content']['case_id']
            selected.append({'case_id': case2, 'candidate_id': store.add_candidate(case2, inputs=inputs2)['record_id']})
            def launch(command, *, folder, env):
                request = json.loads((folder / 'request.json').read_text())
                if request['scan']['working'] == str(view2.working):
                    command = [sys.executable, '-c', 'import time;time.sleep(60)']
                return AnalysisProcess(command, folder=folder, env=env)
            with patch.object(portfolio, 'AnalysisProcess', side_effect=launch):
                result = scan_portfolio(store, selected, output, jobs=2, memory_mib=512, quiet=True,
                                        cancelled=lambda: bool(list(output.glob('attempts/*/*/completion.json'))))
            self.assertEqual({r['state'] for r in result['cases']}, {'ANALYZED', 'CANCELLED'})
            self.assertEqual(result['max_active_workers'], 2)
            resumed = scan_portfolio(store, selected, output, jobs=2, memory_mib=512, quiet=True)
            self.assertEqual({r['state'] for r in resumed['cases']}, {'REUSED', 'ANALYZED'})

    def test_changed_inputs_during_scan_never_publish_success(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            calls = []
            def steer():
                calls.append(1)
                if len(calls) == 2:
                    (view.working / 'during.txt').write_text('changed during execution')
                return False
            result = scan_portfolio(store, selected, output, memory_mib=512, quiet=True, cancelled=steer)
            self.assertEqual(result['cases'][0]['state'], 'STALE')
            self.assertFalse(list(output.glob('attempts/*/*/receipt.json')))

    def test_worker_failure_preserves_other_case_and_selective_resume(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            other = root / 'other'; other.mkdir()
            _, _, view2, inputs2 = fixture(other)
            case2 = store.create_case(view2, target_profile=TARGET, declared_scope='local-new-game')['content']['case_id']
            candidate2 = store.add_candidate(case2, inputs=inputs2)['record_id']
            selected.append({'case_id': case2, 'candidate_id': candidate2})
            def launch(command, *, folder, env):
                request = json.loads((folder / 'request.json').read_text())
                if request['scan']['working'] == str(view2.working):
                    command = [sys.executable, '-c', 'import time;time.sleep(.3);raise SystemExit(17)']
                return AnalysisProcess(command, folder=folder, env=env)
            with patch('bridgeforge.portfolio.AnalysisProcess', side_effect=launch):
                failed = scan_portfolio(store, selected, output, jobs=2, memory_mib=512, quiet=True)
            self.assertEqual(failed['state'], 'INCOMPLETE')
            self.assertEqual({r['state'] for r in failed['cases']}, {'ANALYZED', 'FAILED'})
            resumed = scan_portfolio(store, selected, output, jobs=2, memory_mib=512, quiet=True)
            self.assertEqual(resumed['state'], 'COMPLETE')
            self.assertEqual({r['state'] for r in resumed['cases']}, {'REUSED', 'ANALYZED'})

    def test_compact_storage_prefix_collision_does_not_mix_subjects(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            other = root / 'other'; other.mkdir()
            _, _, view2, inputs2 = fixture(other)
            path = view2.working / 'mod_info.json'
            info = json.loads(path.read_text()); info['name'] = 'Distinct second candidate'
            path.write_text(json.dumps(info))
            case2 = store.create_case(view2, target_profile=TARGET, declared_scope='local-new-game')['content']['case_id']
            selected.append({'case_id': case2, 'candidate_id': store.add_candidate(case2, inputs=inputs2)['record_id']})
            real_digest = portfolio.digest
            def collide(value):
                hashed = real_digest(value)
                return 'a' * 16 + hashed[16:] if set(value) == {'case_id', 'candidate_id', 'engine'} else hashed
            with patch.object(portfolio, 'digest', side_effect=collide):
                first = scan_portfolio(store, selected, output, jobs=2, memory_mib=512, quiet=True)
                again = scan_portfolio(store, selected, output, jobs=2, memory_mib=512, quiet=True)
            self.assertEqual(first['state'], 'COMPLETE')
            self.assertEqual({r['state'] for r in again['cases']}, {'REUSED'})
            names = {r['case_id']: json.loads(Path(r['raw']).read_text())['metadata']['name'] for r in again['cases']}
            self.assertEqual(names[case2], 'Distinct second candidate')
            self.assertNotEqual(names[selected[0]['case_id']], names[case2])

    def test_completion_survives_coordinator_exit_before_receipt_publication(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            with patch.object(store, 'add_receipt', side_effect=RuntimeError('coordinator stopped before publication')):
                with self.assertRaisesRegex(RuntimeError, 'coordinator stopped'):
                    scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertTrue(list(output.glob('attempts/*/*/completion.json')))
            with patch('bridgeforge.portfolio.AnalysisProcess', side_effect=AssertionError('must recover completed scan')):
                resumed = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(resumed['cases'][0]['state'], 'RECOVERED')

    def test_retry_after_store_publication_is_idempotent(self):
        with resolved_temp_dir() as root:
            store, selected, view, inputs, output = setup(root)
            publish = store.add_receipt
            ids = []
            def interrupted(case_id, receipt):
                publish(case_id, receipt)
                ids.append(receipt['record_id'])
                raise RuntimeError('stopped after store publication')
            with patch.object(store, 'add_receipt', side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError, 'stopped after'):
                    scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            resumed = scan_portfolio(store, selected, output, memory_mib=512, quiet=True)
            self.assertEqual(resumed['cases'][0]['receipt_id'], ids[0])
            self.assertEqual(len(list((store.root / selected[0]['case_id'] / 'receipts').glob('*.json'))), 1)


class OwnedProcessTests(unittest.TestCase):
    def test_abrupt_coordinator_death_releases_lease_and_reaps_worker(self):
        with resolved_temp_dir() as root:
            child_script = "import time;from pathlib import Path;from bridgeforge.safeio import atomic_write_json;import os;atomic_write_json(Path('running.json'),{'pid':os.getpid()});time.sleep(60)"
            script = ('import os,sys,time;from pathlib import Path;'
                      'from bridgeforge.portfolio import output_lease;from bridgeforge.portfolio_process import AnalysisProcess;'
                      'root=Path.cwd();lease=output_lease(root);lease.__enter__();'
                      f'p=AnalysisProcess([sys.executable,\'-c\',{child_script!r}],folder=root,env=dict(os.environ));'
                      'exec("while not (root/\'running.json\').exists(): time.sleep(.01)");os._exit(23)')
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent))
            owner = subprocess.Popen([sys.executable, '-c', script], cwd=root, env=env)
            try:
                self.assertEqual(owner.wait(timeout=15), 23)
                pid = json.loads((root / 'running.json').read_text())['pid']
                until = time.monotonic() + 5
                while psutil.pid_exists(pid) and time.monotonic() < until:
                    try:
                        if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE: break
                    except psutil.NoSuchProcess: break
                    time.sleep(.02)
                if psutil.pid_exists(pid):
                    self.assertEqual(psutil.Process(pid).status(), psutil.STATUS_ZOMBIE)
                with output_lease(root):
                    pass
            finally:
                if owner.poll() is None:
                    owner.kill(); owner.wait(timeout=10)

    def test_owned_child_tree_is_terminated(self):
        with resolved_temp_dir() as root:
            env = dict(os.environ)
            script = "import subprocess,sys,time;from pathlib import Path;child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);Path('child.pid').write_text(str(child.pid));time.sleep(60)"
            process = AnalysisProcess([sys.executable, '-c', script], folder=root, env=env)
            try:
                until = time.monotonic() + 10
                while not (root / 'child.pid').exists() and time.monotonic() < until:
                    time.sleep(.02)
                child = psutil.Process(int((root / 'child.pid').read_text()))
                process.close()
                self.assertIsNotNone(process.poll())
                self.assertFalse(child.is_running() and child.status() != psutil.STATUS_ZOMBIE)
            finally:
                process.close()
