import copy, hashlib, json, tempfile, unittest
from pathlib import Path
from bioduet_eval.bw01_protocol_diagnostic_v01 import assess, diagnose

def report(h_reason=None, a_reason=None, h_action="A02"):
    rows=[]
    for seq, actor, reason, action in [(0,"A",a_reason,"A06"),(1,"H",h_reason,h_action)]:
        decision={"kind":"action","request":{"action_id":action,"payload":{}}}
        result={"status":"rejected","reason":reason} if reason else {"status":"succeeded"}
        record={"seq":seq,"tick":seq,"actor":actor,"decision":decision,"result":result}
        rows.append({"actor":actor,"parse_error":None,"submission":record})
    return {"condition":"H1","transcript":rows,"session_records":[r["submission"] for r in rows]}

class ProtocolDiagnosticTests(unittest.TestCase):
    def test_h_missing_operation_is_simulator_fault(self):
        r=assess(report("ACTION_SCHEMA"))
        self.assertEqual(r["prospective_protocol_gate"],"blocked")
        self.assertEqual(r["simulator_protocol_faults"][0]["detail"],"missing_operation_id")
        self.assertIsNone(r["agent_scientific_failure_attributable_from_joint_failure"])
    def test_agent_fault_does_not_become_simulator_fault(self):
        r=assess(report(a_reason="ACTION_SCHEMA"))
        self.assertEqual(r["simulator_protocol_status"],"passed")
        self.assertEqual(len(r["agent_protocol_faults"]),1)
    def test_scientific_and_permission_errors_remain_separate(self):
        for reason in (None,"VERSION_CONFLICT","EVIDENCE_UNAVAILABLE","CAPABILITY_UNAVAILABLE"):
            r=assess(report(reason,h_action="A03"))
            self.assertEqual(r["simulator_protocol_status"],"passed")
            self.assertIsNone(r["formal_benchmark_score"])
    def test_invalid_json_and_later_recovery_still_flagged(self):
        d=report("DECISION_SCHEMA")
        d["transcript"][1]["parse_error"]="INVALID_MODEL_JSON"
        d["session_records"][1].pop("decision")
        row=copy.deepcopy(report()["transcript"][1])
        row["submission"]["seq"]=2;row["submission"]["tick"]=2
        d["transcript"].append(row);d["session_records"].append(row["submission"])
        self.assertEqual(assess(d)["simulator_protocol_status"],"failed")
    def test_missing_or_inconsistent_trace_refused(self):
        for d in ({}, {"transcript":[],"session_records":[]},
                  {"transcript":report()["transcript"],"session_records":[]}):
            with self.assertRaises(ValueError):assess(d)
        d=report();d["transcript"][1]["actor"]="A"
        with self.assertRaises(ValueError):assess(d)
    def test_sidecar_preserves_original_and_is_not_rescoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);raw=json.dumps(report("ACTION_SCHEMA")).encode()
            (p/"episode-private.json").write_bytes(raw)
            summary={"condition":"H1","episode":{"sha256":hashlib.sha256(raw).hexdigest()},
                     "engineering_scientific_path_passed":False,"scientific_validity":"not_assessed"}
            old=json.dumps(summary).encode();(p/"summary.json").write_bytes(old)
            r=diagnose(p,p/"diagnostic.json")
            self.assertEqual((p/"summary.json").read_bytes(),old)
            self.assertEqual((p/"episode-private.json").read_bytes(),raw)
            self.assertTrue(r["policy_applied_after_run"])
            self.assertIsNone(r["historical_primary_metric_eligibility"])
            self.assertFalse(r["original_outcomes"]["engineering_scientific_path_passed"])
            with self.assertRaises(FileExistsError):diagnose(p,p/"diagnostic.json")
    def test_tamper_rejected_before_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/"episode-private.json").write_text(json.dumps(report()))
            (p/"summary.json").write_text(json.dumps({"condition":"H1","episode":{"sha256":"0"*64}}))
            with self.assertRaises(ValueError):diagnose(p,p/"diagnostic.json")
            self.assertFalse((p/"diagnostic.json").exists())

if __name__=="__main__":unittest.main()
