"""Narrow offline entry checks; actual immutable bundles plus labelled mutations."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

from labweave_eval import dual_control_oracle_v03 as route
from labweave_eval import dual_control_oracle_v02 as legacy
from labweave_eval import bioduet_recovery_evaluation_v01 as recovery
from labweave_eval.bioduet_bundle_v01 import load_bundle


class OfflineRecoveryEntry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = Path(os.environ['BIODUET_OFFLINE_JOIN_QA'])
        cls.fixtures = json.loads((cls.qa / 'fixtures.json').read_bytes())
        cls.loaded = {}
        for name, fixture in cls.fixtures.items():
            e, t = fixture['expectation'], fixture['trace']
            cls.loaded[name] = load_bundle(t['directory'], e['summary_sha256'], e['condition'])

    def arguments(self, name):
        f = self.fixtures[name]
        return deepcopy(f['expectation']), deepcopy(f['trace'])

    def evaluated(self, name, change=None):
        e, t = self.arguments(name)
        loaded = deepcopy(self.loaded[name])
        if change:
            change(loaded)
        with patch.object(recovery, 'load_bundle', return_value=loaded):
            return route.evaluate(e, t)

    def test_actual_four_bundles_preserve_complete_partial_and_protocol(self):
        for name in self.fixtures:
            with self.subTest(name=name):
                r = self.evaluated(name)
                complete = name != 'opencode_H1'
                self.assertEqual(r['engineering_goal_met'], complete)
                self.assertEqual(r['participant_lifecycle_complete'], complete)
                self.assertEqual(r['evidence_status'], 'complete_recorded' if complete else 'partial_retained')
                self.assertFalse(r['independently_recomputed_here'])
                self.assertIsNone(r['formal_benchmark_score'])
                self.assertEqual(r['new_model_calls'] + r['new_R_runs'], 0)
        r = self.evaluated('reference_H1')
        self.assertEqual(r['simulator_protocol']['faults']['H'], 1)
        self.assertTrue(r['engineering_goal_met'])
        r = self.evaluated('opencode_H1')
        self.assertTrue(r['recorded_technical_recovery_passed'])
        self.assertEqual(r['original_failure'], 'ValueError')

    def test_missing_invalid_and_wrong_summary_pin_refused(self):
        e, t = self.arguments('biomni_H1')
        for key in recovery.PINS:
            bad = deepcopy(e)
            del bad[key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'EXPECTATION_SCHEMA'):
                route.evaluate(bad, t)
        bad = deepcopy(e); bad['summary_sha256'] = 'z' * 64
        with self.assertRaisesRegex(ValueError, 'PIN'):
            route.evaluate(bad, t)
        bad['summary_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
            route.evaluate(bad, t)

    def test_profile_engine_identity_and_truth_pins_refused(self):
        e, t = self.arguments('biomni_H1')
        for key in ('prehistory_sha256', 'counts_sha256', 'truth_sha256'):
            bad = deepcopy(e); bad[key] = '0' * 64
            with self.subTest(key=key), patch.object(recovery, 'load_bundle', return_value=self.loaded['biomni_H1']):
                with self.assertRaisesRegex(ValueError, 'PIN'):
                    route.evaluate(bad, t)
        for key, value, error in [('schema', 'other-profile', 'RECOVERY_PROFILE'),
            ('mode', 'native-fake', 'ENGINE_PROFILE'),
            ('behavior_source', 'synthetic_qualification', 'HISTORICAL_INTERACTIVE_PROFILE'),
            ('episode_id', 'different', 'EPISODE_IDENTITY')]:
            def mutate(loaded):
                loaded['private_bundle']['summary'][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, error):
                self.evaluated('biomni_H1', mutate)
        e['agent_engine'] = 'opencode'
        with patch.object(recovery, 'load_bundle', return_value=self.loaded['biomni_H1']):
            with self.assertRaisesRegex(ValueError, 'ENGINE_PROFILE'):
                route.evaluate(e, t)

    def test_invalid_or_missing_role_refused(self):
        for replacement in ('X', 'A'):
            def mutate(loaded):
                s = loaded['private_bundle']['summary']
                for row in s['model_calls']['records']:
                    if row['actor'] == 'H':
                        row['actor'] = replacement
            with self.subTest(role=replacement), self.assertRaisesRegex(ValueError, 'DUAL_ROLE_EVIDENCE'):
                self.evaluated('biomni_H1', mutate)

    def test_partial_oracle_cleanup_and_budget_never_complete(self):
        mutations = {
            'terminal': lambda x: x['private_bundle']['summary'].update(terminal='turn_limit'),
            'failure': lambda x: x['private_bundle']['summary'].update(failure='ValueError'),
            'pending': lambda x: x['private_bundle']['summary'].update(pending_turn={'issued': True}),
            'oracle': lambda x: x['private_bundle']['summary'].update(oracle_failure_type='ValueError'),
            'reader': lambda x: x['check'].update(evidence_status='partial_retained'),
            'models': lambda x: x['check']['model_evidence'].update(evidence_status='partial_retained'),
            'usage': lambda x: x['check']['model_evidence'].update(usage_complete=False),
            'cleanup': lambda x: x['private_bundle']['summary']['cleanup'][0].update(confirmed=False),
            'native': lambda x: x['private_bundle']['summary']['native']['receipt'].update(status='cancelled'),
        }
        for key, mutation in mutations.items():
            with self.subTest(case=key):
                r = self.evaluated('biomni_H1', mutation)
                self.assertFalse(r['engineering_goal_met'])
                self.assertFalse(r['participant_lifecycle_complete'])
                self.assertEqual(r['evidence_status'], 'partial_retained')

    def test_recorded_science_failure_does_not_pass(self):
        for field in ('independent_oracle', 'independent_counts_QC', 'consequence_diagnosis'):
            def mutate(loaded):
                loaded['private_bundle']['summary'][field] = {}
            with self.subTest(field=field):
                self.assertFalse(self.evaluated('biomni_H1', mutate)['engineering_goal_met'])

    def test_pair_reference_matches_and_native_engine_mismatch_does_not(self):
        e0, t0 = self.arguments('reference_H0')
        e1, t1 = self.arguments('reference_H1')
        r = route.pair(e0, t0, e1, t1)
        self.assertTrue(r['pair_comparable'])
        self.assertFalse(r['formal_pair_eligible'])
        en, tn = self.arguments('biomni_H1')
        r = route.pair(e0, t0, en, tn)
        self.assertFalse(r['pair_comparable'])

    def test_mixed_profiles_rejected_before_any_bundle_read(self):
        e, t = self.arguments('reference_H0')
        for schema in ('bioduet-bw01-expectation/1', 'c02-dual-control-engineering-expectation/1'):
            other = {'schema': schema}
            with patch.object(recovery, 'load_bundle') as reader:
                for args in ((e, t, other, {}), (other, {}, e, t)):
                    with self.assertRaisesRegex(ValueError, 'MIXED_EVALUATION_PROFILES'):
                        route.pair(*args)
                reader.assert_not_called()

    def test_legacy_evaluate_pair_and_bw01_delegate_unchanged(self):
        from test_dual_control_oracle_v01 import fixture
        e0, t0 = fixture('H0'); e1, t1 = fixture('H1')
        self.assertEqual(route.evaluate(e0, t0), legacy.evaluate(e0, t0))
        self.assertEqual(route.pair(e0, t0, e1, t1), legacy.pair(e0, t0, e1, t1))
        expected = {'schema': 'bioduet-bw01-expectation/1'}
        sentinel = {'old_profile_result': True}
        with patch.object(legacy.bw01, 'evaluate', return_value=sentinel) as old:
            self.assertIs(route.evaluate(expected, {}), sentinel)
            old.assert_called_once_with(expected, {})

    def cli(self, name, mode='evaluate', h1=None):
        f = self.fixtures[name]
        args = ['dual_control_oracle_v03', mode, '--expectation', f['expectation_file'],
                '--expectation-sha256', f['expectation_sha256']]
        trace = f['trace']
        if h1 is not None:
            other = self.fixtures[h1]
            args += ['--h1-expectation', other['expectation_file'],
                     '--h1-expectation-sha256', other['expectation_sha256']]
            trace = {'H0': trace, 'H1': other['trace']}
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(trace).encode()))
        stdout = io.StringIO()
        # Execute the complete __main__ argparse/pinned expectation/stdin/exit path
        # in this already OS-restricted Python process; no subprocess or execution grant.
        with patch.object(sys, 'argv', args), patch.object(sys, 'stdin', stdin):
            with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as exit:
                runpy.run_module('labweave_eval.dual_control_oracle_v03', run_name='__main__')
        record = {'argv': args, 'exit_code': exit.exception.code, 'stdout': stdout.getvalue()}
        with (self.qa / (name + '-' + mode + '-cli.json')).open('x') as f:
            json.dump(record, f, sort_keys=True)
        return exit.exception.code, json.loads(stdout.getvalue())

    def test_complete_cli_four_evaluate_and_reference_pair(self):
        for name in self.fixtures:
            with self.subTest(name=name):
                status, report = self.cli(name)
                self.assertEqual(status, 1 if name == 'opencode_H1' else 0)
                self.assertEqual(report['engineering_goal_met'], status == 0)
        status, report = self.cli('reference_H0', 'pair', 'reference_H1')
        self.assertEqual(status, 0)
        self.assertTrue(report['pair_comparable'])
