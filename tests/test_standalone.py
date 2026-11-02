import json
import tempfile
import unittest
from pathlib import Path
from bioduet.runner import run, fixture
from bioduet_eval.bioduet_integrity_v01 import strict, sha

class StandaloneTests(unittest.TestCase):
    def test_both_conditions_and_failure_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            for condition in ("H0", "H1"):
                report = run(Path(tmp)/condition, condition=condition)
                self.assertEqual(report["terminal"], "participants_finished")
                self.assertIsNone(report["formal_benchmark_score"])
                self.assertIsNone(report["max_turns"])
                self.assertTrue((Path(tmp)/condition/"events.jsonl").is_file())
            def failing(packet):
                raise RuntimeError("synthetic injected failure")
            report = run(Path(tmp)/"failed", participant=failing)
            self.assertEqual(report["failure"]["type"], "RuntimeError")
            self.assertIn('"type": "failure"', (Path(tmp)/"failed"/"events.jsonl").read_text())
    def test_third_party_callable_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = []
            def adapter(packet):
                seen.append(packet["actor"])
                return fixture(packet)
            result = run(Path(tmp)/"plugin", participant=adapter)
            self.assertEqual(set(seen), {"A", "H"})
            self.assertIsNone(result["actual_model_calls"])
            self.assertEqual(result["behavior_source"], "caller_supplied_unverified")
        with self.assertRaises(ValueError):
            strict('{"a":1,"a":2}')
        self.assertEqual(sha({"é":1}), sha(strict('{"é":1}')))
