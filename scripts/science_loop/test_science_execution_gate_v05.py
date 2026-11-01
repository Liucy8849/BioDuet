"""Thirteen synthetic gate methods: eleven compatibility and two new binding checks; never a Root grant, R run or science case.
Positive authorization-data paths replace only the readonly-file reader with
explicit fixture bytes. Actual model-owned-control refusal uses real stat checks.
No executor, SDK, network, process, dataset or R is invoked.
"""
import sys,tempfile,unittest,json,hashlib,time,shlex
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bioduet_vnext import science_execution_gate_v06 as g
class GateChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.work=self.root/"workspace";self.work.mkdir();self.script=self.work/"analysis.R";self.script.write_text("synthetic source only\n")
        self.scope={"role":"A","episode_id":"synthetic-e","attempt_id":"synthetic-a","project_id":"synthetic-p","principal_id":"synthetic-person"}
        self.cfg={"schema":"bioduet-root-science-prefit-gate-config/1","actor_scope":self.scope,"method_packet_sha256":g.PACKET,"unit_deadline_monotonic":time.monotonic()+30,"private_gate_journal_root":str(self.root/"private-journal"),"max_private_capture_bytes":128*1024*1024,"public_readonly_view_refs":[],"gate_pointer_path":str(self.root/"root-pointer"),"qualified_environment_manifest_sha256":"1"*64,"fixed_Rscript_path":"/synthetic/never-executed/Rscript"}
        self.gate=g.ScienceExecutionGate(self.cfg,self.scope,self.work)
    def action(self,command="Rscript analysis.R",**kw):return SimpleNamespace(command=command,is_input=kw.get("is_input",False),reset=kw.get("reset",False))
    def fixture(self):
        raw=b"synthetic immutable R source, never executed\n";script={"path":"/synthetic/frozen/analysis.R","bytes":len(raw),"sha256":g.digest(raw)}
        sr={"schema":"bioduet-method-scope-author-check/1","record_kind":"actual","performed":True,"verdict":"within_scope_for_calibration","approved_method_packet_sha256":g.PACKET,"method_scope_card_sha256":"808049e0bc00be3d15ec68e60c1f5f3af0ead063ad0c670945bc67142f5689b3","input_policy_sha256":"31afdb8cd75413b984fdcd9a3819330e55b90db3e50b5d8dc14af10cae894a4b"}
        for k in ["code_bundle_sha256","dependency_manifest_sha256","settings_sha256","intake_sha256","invocation_sha256"]:sr[k]="2"*64
        r={"schema":"bioduet-root-scientific-execution-admission/1","actor_scope":self.scope,"deadline_monotonic":self.cfg["unit_deadline_monotonic"]-1,"method_packet_sha256":g.PACKET,"environment_manifest_sha256":"1"*64,"root_actual_exec_grant_sha256":"3"*64,"data_binding_sha256":"4"*64,"metadata_binding_sha256":"5"*64,"code_bundle_manifest_sha256":"2"*64,"immutable_execution_files":[script],"script_ref":script,"execution_id":"a"*32,**{k:sr[k] for k in ["code_bundle_sha256","dependency_manifest_sha256","settings_sha256","intake_sha256","invocation_sha256"]}}
        r["argv"]=[self.cfg["fixed_Rscript_path"],"--vanilla",script["path"]];r["command"]=shlex.join(r["argv"])
        return r,sr,{script["path"]:raw}
    @contextmanager
    def synthetic_reader(self,r,sr,other):
        # Fixture reader supplies no authority; this exercises business joins only.
        def ref(path,b):return {"path":path,"bytes":len(b),"sha256":g.digest(b)}
        sraw=g.encode(sr);r["S_author_scope_check_ref"]=ref("/synthetic/scope-check",sraw);rraw=g.encode(r);pointer=g.encode({"receipt_ref":ref("/synthetic/receipt",rraw)})
        data={self.cfg["gate_pointer_path"]:pointer,"/synthetic/receipt":rraw,"/synthetic/scope-check":sraw,**other};old=g.stable
        def read(p,limit,control=False):
            value=data[str(p)];self.assertLessEqual(len(value),limit);return value
        g.stable=read
        try:yield
        finally:g.stable=old
    def test_pending_preserves_actual_code_before_later_edit(self):
        old=self.script.read_bytes()
        with self.assertRaises(g.PendingScientificExecution):self.gate.authorize(self.action())
        copies=list(self.gate.journal.glob("bundle-*/analysis.R"));self.assertEqual(len(copies),1);self.script.write_text("changed source\n");self.assertEqual(copies[0].read_bytes(),old);self.assertIsNone(self.gate.active)
    def test_model_owned_json_true_is_not_root_receipt(self):
        p=Path(self.cfg["gate_pointer_path"]);p.write_text('{"independent_source_verified":true}');p.chmod(0o444)
        with self.assertRaises(g.ScientificGateIntegrityError):self.gate.authorize(self.action())
        self.assertIsNone(self.gate.active)
    def test_file_tool_cannot_read_control_or_write_public_input(self):
        with self.assertRaises(g.ScientificGateIntegrityError):self.gate.view_path(self.cfg["gate_pointer_path"],False)
        public=self.root/"public.csv";public.write_text("synthetic\n");self.cfg["public_readonly_view_refs"].append({"path":str(public)});self.gate.view_path(public,False)
        with self.assertRaises(g.ScientificGateIntegrityError):self.gate.view_path(public,True)
    def test_arbitrary_stdin_is_not_execution_bypass(self):
        self.gate.active="a"*32
        with self.assertRaises(g.ScientificGateIntegrityError):self.gate.authorize(self.action("Rscript other.R",is_input=True))
        self.assertEqual(self.gate.authorize(self.action("C-c",is_input=True))["kind"],"cancel_existing_native_process")
    def test_H_cannot_receive_A_fit_gate(self):
        cfg=dict(self.cfg);scope={**self.scope,"role":"H"};cfg["actor_scope"]=scope
        with self.assertRaises(g.ScientificGateIntegrityError):g.ScienceExecutionGate(cfg,scope,self.work)
    def test_other_scope_receipt_rejected(self):
        r,sr,data=self.fixture();r["actor_scope"]={**self.scope,"project_id":"other"}
        with self.synthetic_reader(r,sr,data),self.assertRaises(g.ScientificGateIntegrityError):self.gate.authorize(self.action(r["command"]))
        self.assertTrue(self.gate.poisoned)
    def test_S_template_does_not_authorize_fit(self):
        r,sr,data=self.fixture();sr["record_kind"]="template";sr["performed"]=False
        with self.synthetic_reader(r,sr,data),self.assertRaises(g.ScientificGateIntegrityError):self.gate.authorize(self.action(r["command"]))
    def test_changed_immutable_script_rejected(self):
        r,sr,data=self.fixture();data[r["script_ref"]["path"]]=b"changed unreviewed script"
        with self.synthetic_reader(r,sr,data),self.assertRaises(g.ScientificGateIntegrityError):self.gate.authorize(self.action(r["command"]))
    def test_execution_id_consumed_before_delegate_no_blind_replay(self):
        r,sr,data=self.fixture()
        with self.synthetic_reader(r,sr,data):
            permit=self.gate.authorize(self.action(r["command"]));self.assertEqual(permit["kind"],"new_native_scientific_exec");self.assertTrue((self.gate.journal/("consumed-"+r["execution_id"]+".json")).is_file())
            with self.assertRaises(g.PendingScientificExecution):self.gate.authorize(self.action(r["command"]))
        # Authorize returns a permit, not execution or scientific success.
        self.assertEqual(len(list(self.gate.journal.glob("consumed-*.json"))),1)
    def feedback_data(self,other_scope=False,template=False):
        self.cfg["scope_feedback_pointer_path"]=str(self.root/"feedback-pointer")
        sr={"schema":"bioduet-method-scope-author-check/1","record_kind":"template" if template else "actual","performed":not template,"verdict":"out_of_scope","approved_method_packet_sha256":g.PACKET,"code_bundle_sha256":"2"*64,"intake_sha256":"3"*64}
        source=g.encode(sr);sref={"path":"/synthetic/sr","bytes":len(source),"sha256":g.digest(source)}
        f={"schema":"bioduet-root-scientific-code-scope-feedback/1","actor_scope":{**self.scope,"attempt_id":"other"} if other_scope else self.scope,"scientific_execution_authorized":False,"actual_S_scope_check_ref":sref,"reported_verdict":sr["verdict"],"code_bundle_sha256":sr["code_bundle_sha256"],"intake_sha256":sr["intake_sha256"],"actor_message":"synthetic scope reason only"}
        raw=g.encode(f);ref={"path":"/synthetic/feedback","bytes":len(raw),"sha256":g.digest(raw)}
        return {self.cfg["scope_feedback_pointer_path"]:g.encode({"feedback_ref":ref}),ref["path"]:raw,sref["path"]:source}
    def test_other_attempt_feedback_does_not_resume_this_scope(self):
        data=self.feedback_data(other_scope=True);old=g.stable
        def read(p,limit,control=False):return data[str(p)]
        g.stable=read
        try:
            with self.assertRaises(g.ScientificGateIntegrityError):self.gate.current_scope_feedback()
        finally:g.stable=old
    def test_actual_feedback_is_not_permission_template_refused(self):
        data=self.feedback_data();old=g.stable
        def read(p,limit,control=False):return data[str(p)]
        g.stable=read
        try:
            body,ref=self.gate.current_scope_feedback();self.assertIs(body["scientific_execution_authorized"],False);self.assertIsNone(self.gate.active)
        finally:g.stable=old
        data=self.feedback_data(template=True);g.stable=read
        try:
            with self.assertRaises(g.ScientificGateIntegrityError):self.gate.current_scope_feedback()
        finally:g.stable=old

    def test_equal_invalid_or_absent_bindings_never_dispatch(self):
        keys=["code_bundle_sha256","dependency_manifest_sha256","settings_sha256","intake_sha256","invocation_sha256"]
        cases=[None,"","g"*64,"0"*63,64,True,"__absent__"]
        for ki,key in enumerate(keys):
            for vi,value in enumerate(cases):
                with self.subTest(binding=key,value_kind=type(value).__name__,index=vi):
                    r,sr,data=self.fixture()
                    if value=="__absent__":r.pop(key);sr.pop(key)
                    else:r[key]=value;sr[key]=value
                    cfg={**self.cfg,"private_gate_journal_root":str(self.root/("invalid-binding-"+str(ki)+"-"+str(vi)))}
                    self.gate=g.ScienceExecutionGate(cfg,self.scope,self.work)
                    with self.synthetic_reader(r,sr,data),self.assertRaises(g.ScientificGateIntegrityError):
                        self.gate.authorize(self.action(r["command"]))
                    self.assertTrue(self.gate.poisoned)
                    self.assertIsNone(self.gate.active)
                    self.assertEqual(list(self.gate.journal.glob("consumed-*.json")),[])
    def test_equal_invalid_feedback_bindings_are_not_publication(self):
        for key in ["code_bundle_sha256","intake_sha256"]:
            for value in [None,"","g"*64,"0"*63,64,True]:
                with self.subTest(binding=key,value_kind=type(value).__name__):
                    data=self.feedback_data()
                    p=json.loads(data[self.cfg["scope_feedback_pointer_path"]]);f=json.loads(data[p["feedback_ref"]["path"]]);sr=json.loads(data[f["actual_S_scope_check_ref"]["path"]])
                    f[key]=value;sr[key]=value
                    sraw=g.encode(sr);data[f["actual_S_scope_check_ref"]["path"]]=sraw
                    f["actual_S_scope_check_ref"].update(bytes=len(sraw),sha256=g.digest(sraw))
                    raw=g.encode(f);data[p["feedback_ref"]["path"]]=raw
                    p["feedback_ref"].update(bytes=len(raw),sha256=g.digest(raw));data[self.cfg["scope_feedback_pointer_path"]]=g.encode(p)
                    old=g.stable
                    def read(path,limit,control=False):return data[str(path)]
                    g.stable=read
                    try:
                        with self.assertRaises(g.ScientificGateIntegrityError):self.gate.current_scope_feedback()
                        self.assertIsNone(self.gate.active)
                    finally:g.stable=old

if __name__=="__main__":unittest.main(verbosity=2)
