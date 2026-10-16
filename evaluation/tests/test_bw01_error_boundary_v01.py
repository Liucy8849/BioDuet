"""Targeted Root-requested exception-boundary regression, no model or DB."""
import json
import unittest
from labweave_eval.bw01_logical_v01 import Bw01EngineeringWorld, LogicalSession

SECRET = 'PRIVATE-SENTINEL-NOT-A-REAL-SECRET'
ACTION = {'kind': 'action', 'request': {'action_id': 'A01'}}


class BoundaryTests(unittest.TestCase):
    def assert_safe_terminal(self, session):
        self.assertEqual(session.terminal, 'environment_error')
        self.assertIsNone(session.next_turn())
        report = session.report()
        self.assertEqual(report['records'][-1]['result']['status'], 'environment_error')
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertFalse(report['interactive_closed_loop'])
        self.assertIsNone(report['formal_benchmark_score'])
        return report['records'][-1]

    def test_world_value_error_is_environment_error(self):
        class Broken(Bw01EngineeringWorld):
            def execute(self, actor, request):
                raise ValueError(SECRET)
        s = LogicalSession(Broken())
        p = s.next_turn()
        r = s.submit(p['turn_token'], ACTION)
        self.assertEqual(r['result']['stage'], 'world_execute')
        self.assertEqual(r['result']['error_type'], 'ValueError')
        self.assertNotIn('reason', r['result'])
        self.assert_safe_terminal(s)

    def test_invalid_world_results_are_environment_errors(self):
        for bad in [object(), {'status': 'succeeded', 'private': SECRET + 'x'*65537}]:
            with self.subTest(result_type=type(bad).__name__):
                class Broken(Bw01EngineeringWorld):
                    def execute(self, actor, request):
                        return bad
                s = LogicalSession(Broken())
                p = s.next_turn()
                r = s.submit(p['turn_token'], ACTION)
                self.assertEqual(r['result']['stage'], 'world_result_validation')
                self.assertEqual(r['result']['error_type'], 'ValueError')
                self.assert_safe_terminal(s)

    def test_observation_stage_exceptions_terminate_safely(self):
        for method in ('advance', 'observe', 'available_actions'):
            for error in (ValueError, RuntimeError):
                with self.subTest(method=method, error=error.__name__):
                    class Broken(Bw01EngineeringWorld):
                        # Do not let the stock observe call available_actions:
                        # isolate each next_turn boundary in this test.
                        def observe(self, actor):
                            return {'sample': {'version': 1}}
                    def fail(self, value):
                        raise error(SECRET)
                    setattr(Broken, method, fail)
                    s = LogicalSession(Broken())
                    self.assertIsNone(s.next_turn())
                    record = self.assert_safe_terminal(s)
                    self.assertEqual(record['stage'], method)
                    self.assertEqual(record['result']['error_type'], error.__name__)
                    self.assertIsNone(s.pending)
                    self.assertNotIn('decision', record)
                    self.assertEqual(len(s.records), 1)

    def test_invalid_observation_packet_terminates_safely(self):
        for bad in [object(), {'private': SECRET + 'x'*65537}]:
            with self.subTest(observation_type=type(bad).__name__):
                class Broken(Bw01EngineeringWorld):
                    def observe(self, actor):
                        return bad
                s = LogicalSession(Broken())
                self.assertIsNone(s.next_turn())
                record = self.assert_safe_terminal(s)
                self.assertEqual(record['stage'], 'packet_validation')
                self.assertEqual(record['result']['error_type'], 'ValueError')

    def test_input_validation_stays_separate_and_valid_action_still_runs(self):
        s = LogicalSession(Bw01EngineeringWorld())
        p = s.next_turn()
        r = s.submit(p['turn_token'], {'kind': 'wait', 'until': 0})
        self.assertEqual(r['result'], {'status': 'rejected', 'reason': 'INVALID_INTEGER'})
        self.assertIsNone(s.terminal)
        p = s.next_turn()
        r = s.submit(p['turn_token'], ACTION)
        self.assertEqual(r['result']['status'], 'succeeded')
        self.assertIsNone(s.terminal)
        self.assertEqual(s.world.tick, p['tick'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
