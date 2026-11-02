"""New-profile semantic self-checks for the consolidated science I6 only.
All data/files/authority callbacks here are explicitly synthetic software
fixtures. No model, R, statistical method, real counts or process is executed.
"""
import unittest,tempfile,json,hashlib
from pathlib import Path
from types import SimpleNamespace
from bioduet_vnext.contracts_v01 import Scope
from bioduet_vnext.native_science_world_v03 import NativeArtifactRecoveryWorld,PROFILE
from bioduet_vnext.native_artifact_world_port_v01 import BrokeredNativeArtifactWorld,CONTRACT
from bioduet_vnext.native_artifact_snapshots_v01 import ScopedNativeArtifactSnapshots
from bioduet_vnext.logical_study_endpoint_v06 import LogicalStudyEndpoint
from bioduet_eval.bioduet_logical_v02 import LogicalSession
from bioduet_eval.bioduet_world_port_v02 import ScienceWorldPort
from bioduet_eval.contract import Rejection
class NativeScienceProfileChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path.cwd());self.root=Path(self.tmp.name)
        self.scopes={r:Scope("fixture_episode","fixture_attempt","fixture_project","fixture_"+r,r) for r in ("A","H")}
        roots={}
        for r in self.scopes:
            p=self.root/r;p.mkdir();roots[r]=p
        (roots["A"]/"candidate.py").write_text("NOT EXECUTED - synthetic code bytes")
        (roots["A"]/"result.tsv").write_text("fixture_result_not_an_analysis\n")
        self.snap=ScopedNativeArtifactSnapshots(self.root/"custody",role_roots=roots,role_scopes=self.scopes,
            authorize_read=lambda *args:True,max_bytes=1048576)
        declared=[{"library_id":"L1","donor_id":"D1","condition":"control"},
                  {"library_id":"L2","donor_id":"D1","condition":"stim"}]
        source=[dict(declared[0],condition="stim"),declared[1]]
        self.world=NativeArtifactRecoveryWorld(dataset={"samples":declared,"counts":{"sha256":"1"*64}},
            declared_records=declared,H_source_records=source,H_source_sha256="2"*64,
            human_scope_library_ids=["L1","L2"],artifact_snapshot=self.snap,
            verify_artifact_snapshot=self.snap.verify,evidence_at=0)
        self.brokered=BrokeredNativeArtifactWorld(self.world)
        self.logical=LogicalSession(self.brokered,deadline=None,max_turns=None)
        self.trace=[]
        session=SimpleNamespace(_scopes={s.principal_id:s for s in self.scopes.values()})
        self.endpoint=LogicalStudyEndpoint(logical_session=self.logical,participant_session=session,
            world_owner=self.world,role_scopes=self.scopes,
            authorize=lambda *args:{"allowed":True,"source_kind":"synthetic_callback_NOT_Root_admission"},
            deadline_monotonic=__import__("time").monotonic()+30,
            participant_bridge_factory=lambda scope:None,
            trace=lambda *args:self.trace.append(args))
    def tearDown(self):self.tmp.cleanup()
    def invoke(self,role,name,args):return self.endpoint.invoke(self.scopes[role],name,json.dumps(args))
    def submit(self,role,decision):
        packet=self.invoke(role,"study.next",{"wait_seconds":0})["packet"]
        return self.invoke(role,"study.submit",{"turn_handle":packet["turn_handle"],"decision":decision})
    def test_01_empty_initial_state_and_no_chosen_method(self):
        self.assertEqual(self.world.artifacts,{})
        self.assertEqual(self.world.publications,{})
        self.assertIsNone(self.world.design["analysis_unit"])
        self.assertIsNone(self.world.design["paired"])
        self.assertIsNone(self.world.expires_at)
        self.assertIsNone(self.logical.max_turns)
    def test_02_explicit_profile_rejects_legacy_action_envelope(self):
        context=self.brokered._contexts["A"];new=self.brokered._port.envelope(context,{"action_id":"A01"})
        self.assertEqual(new["contract_version"],CONTRACT)
        self.assertEqual(new["world_profile"],PROFILE)
        legacy=ScienceWorldPort(self.world);old=legacy.envelope(legacy.issue_context("A"),{"action_id":"A01"})
        with self.assertRaises(Rejection):self.brokered._port.execute(context,old)
    def test_03_file_registration_never_executes_or_approves_science(self):
        payload={"collection_version":1,"design_version":0,"code_path":"candidate.py",
            "result_path":"result.tsv","execution_ref":{"kind":"synthetic_no_execution"},
            "declared_read_set":{},"method_spec_json":"{\"method\":\"fixture_not_science\"}"}
        result=self.world.execute("A",{"action_id":"A04","operation_id":"fixture-register","payload":payload})
        self.assertEqual(result["status"],"succeeded")
        self.assertFalse(result["actual_analysis_executed_by_this_action"])
        artifact=result["artifact"]
        self.assertIsNone(artifact["actual_execution_verified"])
        self.assertIsNone(artifact["scientific_validity"])
        self.assertEqual(artifact["code_sha256"],hashlib.sha256(b"NOT EXECUTED - synthetic code bytes").hexdigest())
    def test_04_old_fixed_executor_request_not_accepted(self):
        result=self.world.execute("A",{"action_id":"A11","operation_id":"old-fixed-request",
                                      "payload":{"collection_version":1,"design_version":0}})
        self.assertEqual(result["status"],"rejected")
        self.assertFalse(self.world.artifacts)
    def test_05_opaque_handle_is_scoped_and_original_token_not_returned(self):
        packet=self.invoke("A","study.next",{"wait_seconds":0})
        self.assertNotIn(self.logical.pending["turn_token"],json.dumps(packet))
        with self.assertRaises(ValueError):
            self.invoke("H","study.submit",{"turn_handle":packet["packet"]["turn_handle"],"decision":{"kind":"finish"}})
        self.assertEqual(self.logical.pending["actor"],"A")
    def test_06_notice_mode_no_automatic_current_full_snapshot(self):
        self.submit("A",{"kind":"message","to":"H","text":"synthetic software fixture"})
        self.submit("H",{"kind":"action","request":{"action_id":"A03","operation_id":"fixture-H-correct",
            "payload":{"library_id":"L1","expected_version":1,"condition":"stim","reason":"fixture source"}}})
        packet=self.invoke("A","study.next",{"wait_seconds":0})["packet"]
        initial=packet["observation"]["initial_role_view"]["samples"]["L1"]["condition"]
        current=self.invoke("A","study.observe",{})["observation"]["samples"]["L1"]["condition"]
        self.assertEqual(initial,"control");self.assertEqual(current,"stim")
        self.assertTrue(self.invoke("A","study.observe",{})["full_snapshot_auxiliary_on_explicit_query"])
    def test_07_capture_failure_poison_never_blindly_replays(self):
        def failed_trace(*args):raise OSError("synthetic_capture_failure")
        self.endpoint.trace=failed_trace
        with self.assertRaises(RuntimeError):self.invoke("A","study.schema",{})
        self.assertTrue(self.endpoint.poisoned)
        with self.assertRaises(RuntimeError):self.invoke("A","study.schema",{})
        self.assertEqual(self.world.history,[])
if __name__=="__main__":unittest.main(verbosity=2)
