"""Fail-closed pre-fit permission gate, not a scientific evaluator or executor.
Only protected Root current receipts can release fixed immutable R code. Missing
receipt is pending; malformed/changed control poisons the affected gate. Model
statements, method names, command basenames and post-hoc verdicts are not grants.
"""
import os,stat,json,hashlib,time,shlex,uuid,math
from pathlib import Path
PACKET="317b9b7c136deab41cce0902b01f85fe5781cedd32b2bb1a618cf6f812661aa5"
class PendingScientificExecution(Exception):pass
class ScientificGateIntegrityError(Exception):pass
def check(ok,reason):
    if not ok:raise ScientificGateIntegrityError(reason)
def encode(x):return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def digest(b):return hashlib.sha256(b).hexdigest()
def stable(p,limit,control=False):
    p=Path(p);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);check(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<=before.st_size<=limit,"BOUNDED_REGULAR_SINGLE_LINK")
        if control:
            check(stat.S_IMODE(before.st_mode)==0o444 and before.st_uid!=os.geteuid(),"FOREIGN_ROOT_CONTROL_0444")
            check(bool(os.statvfs(p).f_flag & os.ST_RDONLY),"ACTUAL_READONLY_CONTROL_MOUNT")
        raw=bytearray()
        while True:
            block=os.read(fd,65536)
            if not block:break
            raw.extend(block);check(len(raw)<=limit,"READ_LIMIT")
        after=os.fstat(fd);end=os.lstat(p)
        check(all(getattr(before,k)==getattr(after,k)==getattr(end,k) for k in ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")),"UNCHANGED_FD_AND_PATH")
        return bytes(raw)
    finally:os.close(fd)
class ScienceExecutionGate:
    def __init__(self,cfg,scope,workspace):
        check(cfg["schema"]=="bioduet-root-science-prefit-gate-config/1" and cfg["actor_scope"]==scope and scope["role"]=="A","ACTUAL_A_GATE_SCOPE")
        check(cfg["method_packet_sha256"]==PACKET and type(cfg["unit_deadline_monotonic"]) in (int,float) and math.isfinite(cfg["unit_deadline_monotonic"]) and time.monotonic()<cfg["unit_deadline_monotonic"],"FINITE_CURRENT_GATE_UNIT")
        self.cfg=cfg;self.scope=scope;self.workspace=Path(workspace).resolve();self.journal=Path(cfg["private_gate_journal_root"]);check(not self.journal.resolve().is_relative_to(self.workspace),"PRIVATE_GATE_JOURNAL_NOT_AGENT_WORKSPACE");check(type(cfg["max_private_capture_bytes"]) is int and 64*1024*1024<=cfg["max_private_capture_bytes"]<=512*1024*1024,"FINITE_PRIVATE_CAPTURE_STORAGE");self.journal.mkdir(mode=0o700,exist_ok=False);self.poisoned=False;self.active=None;self.awaiting_scope=False;self.audit=[]
    def view_path(self,path,write):
        p=Path(path)
        if not p.is_absolute():p=self.workspace/p
        p=p.resolve();inside=p.is_relative_to(self.workspace)
        allowed=inside or (not write and str(p) in {str(Path(r["path"]).resolve()) for r in self.cfg["public_readonly_view_refs"]})
        check(allowed,"ROLE_FILE_TOOL_PATH_BOUNDARY")
    def _record(self,event):
        row={"event_id":uuid.uuid4().hex,"monotonic_ns":time.monotonic_ns(),**event};raw=encode(row)+b"\n"
        p=self.journal/(row["event_id"]+".json")
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
        self.audit.append({"path":str(p),"bytes":len(raw),"sha256":digest(raw)});return row
    def _propose(self,command):
        # Evidence capture only: no commands/imports/fits are executed here.
        used=sum(p.stat().st_size for p in self.journal.rglob("*") if p.is_file());check(used<=self.cfg["max_private_capture_bytes"]-64*1024*1024,"PRIVATE_CAPTURE_STORAGE_BUDGET")
        self.awaiting_scope=True
        files=[];total=0
        snapshot_id=uuid.uuid4().hex;snapshot_root=self.journal/("bundle-"+snapshot_id);snapshot_root.mkdir(mode=0o700)
        for p in sorted(self.workspace.rglob("*")):
            check(not p.is_symlink(),"WORKSPACE_BUNDLE_NO_SYMLINK")
            if not p.is_file():continue
            raw=stable(p,16*1024*1024);total+=len(raw);check(len(files)<128 and total<=64*1024*1024,"BUNDLE_STORAGE_LIMIT")
            rel=p.relative_to(self.workspace);copy=snapshot_root/rel;copy.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(copy,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
            check(stable(p,16*1024*1024)==raw,"WORKSPACE_CHANGED_DURING_CODE_CAPTURE")
            files.append({"relative_path":str(rel),"bytes":len(raw),"sha256":digest(raw),"private_snapshot_path":str(copy)})
        return self._record({"kind":"scientific_execution_pending","actor_scope":self.scope,"requested_command":command,"workspace_files":files,"snapshot_id":snapshot_id,"workspace_tree_sha256":digest(encode([{k:v for k,v in f.items() if k!="private_snapshot_path"} for f in files])),"source_kind":"actual_untrusted_A_workspace_observation_not_scope_approval","actual_fit_started":False})
    def current_approved_execution(self):
        check(not self.poisoned and time.monotonic()<self.cfg["unit_deadline_monotonic"],"CURRENT_GATE_STATE")
        try:pointer_raw=stable(self.cfg["gate_pointer_path"],1024*1024,True)
        except FileNotFoundError:raise PendingScientificExecution("Current scientific execution receipt has not been published.")
        pointer=json.loads(pointer_raw);ref=pointer["receipt_ref"];raw=stable(ref["path"],1024*1024,True);check(len(raw)==ref["bytes"] and digest(raw)==ref["sha256"],"ACTUAL_ROOT_RECEIPT_SHA")
        r=json.loads(raw);check(r["schema"]=="bioduet-root-scientific-execution-admission/1" and r["actor_scope"]==self.scope,"CURRENT_EXACT_EXEC_SCOPE")
        check(time.monotonic()<r["deadline_monotonic"]<=self.cfg["unit_deadline_monotonic"],"CURRENT_FINITE_EXEC_DEADLINE")
        check(r["method_packet_sha256"]==PACKET and r["environment_manifest_sha256"]==self.cfg["qualified_environment_manifest_sha256"],"FIXED_METHOD_ENVIRONMENT_BINDING")
        for key in ["root_actual_exec_grant_sha256","data_binding_sha256","metadata_binding_sha256","code_bundle_manifest_sha256","code_bundle_sha256","dependency_manifest_sha256","settings_sha256","intake_sha256","invocation_sha256","environment_manifest_sha256"]:check(type(r.get(key)) is str and len(r[key])==64 and set(r[key])<=set("0123456789abcdef"),"ACTUAL_BINDING_DIGEST")
        scope_ref=r["S_author_scope_check_ref"];sraw=stable(scope_ref["path"],1024*1024,True);check(len(sraw)==scope_ref["bytes"] and digest(sraw)==scope_ref["sha256"],"ACTUAL_S_SCOPE_CHECK_SHA")
        sr=json.loads(sraw);check(sr["schema"]=="bioduet-method-scope-author-check/1" and sr["record_kind"]=="actual" and sr["performed"] is True and sr["verdict"]=="within_scope_for_calibration" and sr["approved_method_packet_sha256"]==PACKET,"ACTUAL_S_AUTHOR_SCOPE_NOT_EXPERT_OR_NUMERIC_GRADE")
        for key in ["code_bundle_sha256","dependency_manifest_sha256","settings_sha256","intake_sha256","invocation_sha256"]:check(type(sr.get(key)) is str and len(sr[key])==64 and set(sr[key])<=set("0123456789abcdef") and sr[key]==r[key],"EXACT_S_CHECK_INPUT_OPTION_DEPENDENCY_BINDINGS")
        check(sr["method_scope_card_sha256"]=="808049e0bc00be3d15ec68e60c1f5f3af0ead063ad0c670945bc67142f5689b3" and sr["input_policy_sha256"]=="31afdb8cd75413b984fdcd9a3819330e55b90db3e50b5d8dc14af10cae894a4b","ACTUAL_S_PUBLIC_SCOPE_AND_INPUT_POLICY")
        check(r["code_bundle_manifest_sha256"]==r["code_bundle_sha256"],"EXACT_FROZEN_CODE_BUNDLE_ALIAS")
        # All algorithm options/dependencies and input revisions belong to the
        # Root-frozen bundle and S scope-check, not a method-name assertion.
        for f in r["immutable_execution_files"]:
            b=stable(f["path"],64*1024*1024,True);check(len(b)==f["bytes"] and digest(b)==f["sha256"],"EXACT_IMMUTABLE_CODE_AND_INPUT_BYTES")
        script=r["script_ref"];check(script in r["immutable_execution_files"],"SCRIPT_IN_FROZEN_EXECUTION_BUNDLE")
        argv=r["argv"];check(argv[:3]==[self.cfg["fixed_Rscript_path"],"--vanilla",script["path"]],"ONLY_APPROVED_R_SCRIPT_NOT_INLINE_CODE_OR_SHELL")
        canonical=shlex.join(argv);check(r["command"]==canonical,"CANONICAL_LITERAL_ARGV_NO_SHELL_REWRITE")
        return r,ref,canonical
    def current_scope_feedback(self):
        # Feedback enables code revision only. It cannot authorize any execution.
        path=self.cfg.get("scope_feedback_pointer_path")
        if path is None:raise PendingScientificExecution("No scope feedback available.")
        check(not self.poisoned and time.monotonic()<self.cfg["unit_deadline_monotonic"],"CURRENT_FEEDBACK_SCOPE")
        try:raw=stable(path,1024*1024,True)
        except FileNotFoundError:raise PendingScientificExecution("No new scope feedback available.")
        pointer=json.loads(raw);ref=pointer["feedback_ref"];body=stable(ref["path"],1024*1024,True);check(len(body)==ref["bytes"] and digest(body)==ref["sha256"],"EXACT_PROTECTED_SCOPE_FEEDBACK")
        f=json.loads(body);check(f["schema"]=="bioduet-root-scientific-code-scope-feedback/1" and f["actor_scope"]==self.scope and f["scientific_execution_authorized"] is False,"FEEDBACK_IS_NOT_EXECUTION_GRANT")
        source=f["actual_S_scope_check_ref"];sraw=stable(source["path"],1024*1024,True);check(len(sraw)==source["bytes"] and digest(sraw)==source["sha256"],"ACTUAL_S_FEEDBACK_SOURCE_SHA")
        sr=json.loads(sraw);check(sr["schema"]=="bioduet-method-scope-author-check/1" and sr["record_kind"]=="actual" and sr["performed"] is True and sr["verdict"] in ("out_of_scope","insufficient") and sr["approved_method_packet_sha256"]==PACKET,"ACTUAL_SCOPE_REVISION_FEEDBACK_NOT_TEMPLATE")
        for key in ["code_bundle_sha256","intake_sha256"]:check(type(f.get(key)) is str and type(sr.get(key)) is str and len(f[key])==64 and set(f[key])<=set("0123456789abcdef") and f[key]==sr[key],"ACTUAL_FEEDBACK_BINDING_DIGEST")
        check(f["reported_verdict"]==sr["verdict"] and f["code_bundle_sha256"]==sr["code_bundle_sha256"] and f["intake_sha256"]==sr["intake_sha256"],"EXACT_FEEDBACK_CODE_INTAKE_BINDING")
        check(type(f["actor_message"]) is str and 0<len(f["actor_message"])<=8192,"BOUNDED_PUBLIC_SCOPE_FEEDBACK")
        return f,ref
    def authorize(self,action):
        check(not self.poisoned,"GATE_POISONED_STOP_AFFECTED_EXECUTION")
        check(time.monotonic()<self.cfg["unit_deadline_monotonic"],"GATE_UNIT_EXPIRED")
        command=action.command
        check(type(command) is str,"ORIGINAL_NATIVE_COMMAND_STRING")
        if action.is_input:
            check(self.active is not None and command=="C-c" and not action.reset,"NO_ARBITRARY_TERMINAL_STDIN")
            return {"kind":"cancel_existing_native_process","execution_id":self.active}
        if command=="":
            check(not action.reset or self.active is None,"NO_RESET_OF_ACTIVE_SCIENTIFIC_EXEC")
            return {"kind":"native_IO_or_clean_session_reset_not_new_fit"}
        check(not action.reset,"NO_COMMAND_AND_RESET_COMBINATION")
        try:r,ref,canonical=self.current_approved_execution()
        except PendingScientificExecution:
            self._propose(command);raise
        except Exception:
            self.poisoned=True;raise
        try:
            if command!=canonical:
                self._propose(command);raise PendingScientificExecution("Only the current immutable approved command may execute: "+canonical)
            execution_id=r["execution_id"];check(type(execution_id) is str and len(execution_id)==32 and set(execution_id)<=set("0123456789abcdef"),"OPAQUE_CURRENT_EXECUTION_ID")
            intent=self.journal/("consumed-"+execution_id+".json")
            try:fd=os.open(intent,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            except FileExistsError:raise PendingScientificExecution("This execution ID already has a dispatch intent. Poll/cancel the existing native process; unknown/failed execution requires a fresh authorized ID, never blind replay.")
            with os.fdopen(fd,"wb") as f:f.write(encode({"execution_id":execution_id,"receipt_sha256":ref["sha256"],"command_sha256":digest(command.encode()),"state":"dispatch_intent_before_original_executor_not_execution_proof"}));f.flush();os.fsync(f.fileno())
            self.active=execution_id;self.awaiting_scope=False;self._record({"kind":"approved_native_dispatch_intent","execution_id":execution_id,"receipt_sha256":ref["sha256"]});return {"kind":"new_native_scientific_exec","execution_id":execution_id}
        except PendingScientificExecution:raise
        except Exception:
            self.poisoned=True;raise
    def observed(self,permit,observation):
        # Native observations are retained separately from Root kernel/retirement
        # and scientific validity. Exit0 alone is never acceptance.
        code=getattr(observation,"exit_code",None)
        self._record({"kind":"original_native_terminal_observation","permit_kind":permit["kind"],"execution_id":self.active,"reported_exit_code":code,"actual_execution_independently_verified":None,"scientific_validity":None})
        if type(code) is int and code!=-1:self.active=None
