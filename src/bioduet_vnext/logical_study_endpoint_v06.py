"""Role-bound access to the ONE original None-compatible LogicalSession.
Opaque handles never expose original kernel tokens. This module does not grant
Root resources, execute participant analysis, fill a method, or select actions.
"""
import secrets,threading,time,json,hashlib,math
from copy import deepcopy
from .contracts_v01 import require,Scope
from .native_science_world_v03 import PROFILE,REGISTER_FIELDS
from .mcp_tool_contracts_v01 import tool_contracts
DECISIONS={"action":{"kind":"action","request":"role action request below"},
 "message":{"kind":"message","to":"the other role A or H","text":"1..4096 characters"},
 "wait":{"kind":"wait","until":"integer logical tick strictly after current tick"},
 "finish":{"kind":"finish"}}
ACTION_FIELDS={"A01":[],
 "A02":["evidence_ref"],"A03":["library_id","expected_version","condition","reason"],
 "A04":sorted(REGISTER_FIELDS),"A06":["collection_version","conditions","analysis_unit","paired","method_spec_json"],
 "A11":sorted(REGISTER_FIELDS),"A12":["artifact_id"],
 "A13":["run_id","expected_collection_version","expected_design_version","interpretation","supersedes_run_id"],
 "A14":["artifact_id","reason"]}
class LogicalStudyEndpoint:
    def __init__(self,*,logical_session,participant_session,world_owner,role_scopes,authorize,
                 deadline_monotonic,trace,participant_bridge_factory,after_logical_submit=None):
        require(type(deadline_monotonic) in (int,float) and math.isfinite(deadline_monotonic)
                and deadline_monotonic>time.monotonic(),"FINITE_ACTUAL_EPISODE_DEADLINE")
        require(logical_session.max_turns is None and logical_session.deadline is None,
                "EXISTING_NONE_COMPATIBLE_KERNEL")
        require(getattr(world_owner,"profile",None)==PROFILE,"EXPLICIT_NATIVE_ARTIFACT_PROFILE")
        # Prove wrapper identity without rewriting any World/Port/Logical UUID.
        cursor=logical_session.world;seen=set();found=False
        for unused in range(8):
            if cursor is world_owner:found=True;break
            require(id(cursor) not in seen,"NO_WORLD_WRAPPER_CYCLE");seen.add(id(cursor))
            own=vars(cursor)
            if "_world" in own:cursor=own["_world"]
            elif "_port" in own:cursor=own["_port"].world
            else:break
        require(found,"ONE_CANONICAL_WORLD_OBJECT")
        require(set(role_scopes)=={"A","H"} and callable(authorize) and callable(trace),
                "ACTUAL_ROLE_AND_CAPTURE_BINDINGS")
        for role,scope in role_scopes.items():
            require(type(scope) is Scope and scope.role==role and
                    participant_session._scopes.get(scope.principal_id) is scope,"EXACT_ISSUED_SCOPE")
        self.logical=logical_session;self.participants=participant_session;self.world=world_owner
        self.scopes=dict(role_scopes);self.authorize=authorize;self.deadline=deadline_monotonic
        require(callable(participant_bridge_factory),"ACTUAL_CAPTURED_PARTICIPANT_BRIDGE")
        self._bridge=participant_bridge_factory
        self.trace=trace;self.after_submit=after_logical_submit
        self._lock=threading.RLock();self._condition=threading.Condition(self._lock);self._turn_handles={};self.audit=[];self.poisoned=False
        # These are explicitly labelled initial-role views, not a second mutable World.
        self.initial_views={r:deepcopy(world_owner.observe(r)) for r in self.scopes}
    def _issued(self,scope):
        require(time.monotonic()<self.deadline,"EPISODE_ACTUAL_LEASE_EXPIRED")
        require(self.scopes.get(scope.role) is scope,"EXACT_ROLE_SCOPE")
        require(not self.poisoned,"CAPTURE_OR_COMMIT_OUTCOME_REQUIRES_HOST_INSPECTION")
    def invoke(self,scope,tool_name,arguments_json):
        row={"role":getattr(scope,"role",None),"tool":tool_name if type(tool_name) is str else None,
             "state":"requested","arguments_sha256":None,"commit_or_execution_inferred":False}
        self.audit.append(row)
        try:
            self._issued(scope)
            require(type(tool_name) is str and type(arguments_json) is str and
                    len(arguments_json.encode())<=1048576,"BOUNDED_NATIVE_TOOL_ARGUMENTS")
            row["arguments_sha256"]=hashlib.sha256(arguments_json.encode()).hexdigest()
            args=json.loads(arguments_json);require(type(args) is dict,"TOOL_ARGUMENT_OBJECT")
            if tool_name.startswith("study."):
                receipt=self.authorize(scope,tool_name,deepcopy(args))
                require(type(receipt) is dict and receipt.get("allowed") is True,"CURRENT_EPISODE_AUTHORITY")
            if not tool_name.startswith("study."):
                result=self._bridge(scope).invoke(tool_name,arguments_json)
            else:
                with self._lock:result=self._study(scope,tool_name,args)
            row["state"]="returned_not_transport_commit_or_model_receipt"
        except Exception as exc:
            row.update(state="rejected_or_error_no_blind_retry",error_type=type(exc).__name__)
            self._capture(scope,tool_name,arguments_json,{"error_type":type(exc).__name__})
            raise
        self._capture(scope,tool_name,arguments_json,result)
        return deepcopy(result)
    def _capture(self,scope,name,raw,result):
        try:self.trace(scope,name,raw,result)
        except Exception:
            # A mutation might already have committed before capture failed.
            self.poisoned=True;raise RuntimeError("CAPTURE_FAILED_OUTCOME_MAY_ALREADY_HAVE_COMMITTED") from None
    def _study(self,scope,name,args):
        if name=="study.schema":
            require(not args,"NO_SCHEMA_ARGUMENTS")
            return {"profile":PROFILE,"decisions":deepcopy(DECISIONS),
                "original_participant_tools":tool_contracts(),
                "execution_profile":"analysis uses native Terminal; job.submit unavailable in this profile",
                "action_request":{"action_id":"offered ID","operation_id":"your unique idempotency ID",
                                  "payload":"exact keys from action_fields"},
                "A01_request":{"action_id":"A01"},"action_fields":deepcopy(ACTION_FIELDS),
                "method_spec_json":"JSON-encoded string, participant-selected; no platform method is filled",
                "study_next":{"wait_seconds":"optional 0..30 finite IO wait; not a call/turn budget"},"study_submit":{"turn_handle":"issued opaque handle","decision":"one exact decision"},
                "metadata_registration_runs_analysis":False,"actual_execution_is_native_terminal":True}
        if name=="study.observe":
            require(not args,"STUDY_OBSERVE_ARGUMENTS")
            return {"profile":PROFILE,"observation":self.logical.world.observe(scope.role),
                    "full_snapshot_auxiliary_on_explicit_query":True,"turn_granted":False}
        if name=="study.next":
            require(set(args)<= {"wait_seconds"},"STUDY_NEXT_ARGUMENTS")
            seconds=args.get("wait_seconds",30)
            require(type(seconds) in (int,float) and math.isfinite(seconds) and 0<=seconds<=30,
                    "FINITE_IO_WAIT_NOT_MODEL_TURN_LIMIT")
            until=min(time.monotonic()+seconds,self.deadline)
            while True:
                self._issued(scope)
                packet=self.logical.pending
                if packet is None:packet=self.logical.next_turn()
                if packet is None:return {"state":"finished","reason":self.logical.terminal}
                if packet["actor"]==scope.role:break
                left=until-time.monotonic()
                if left<=0:return {"state":"not_ready","turn_granted":False,"waited_IO_boundary":True}
                self._condition.wait(timeout=min(left,1))
            token=packet["turn_token"];current=self._turn_handles.get(scope.role)
            if current is None or current[0]!=token:
                current=(token,secrets.token_urlsafe(24));self._turn_handles[scope.role]=current
            public=deepcopy(packet);public.pop("turn_token")
            # Formal change_notice: a new turn does not push a fresh full World snapshot.
            public["observation"]={"initial_role_view":deepcopy(self.initial_views[scope.role]),
                "observation_kind":"initial_view_not_automatically_refreshed",
                "current_objects":"explicit study.observe query","change_notifications":"notice.receive"}
            public["turn_handle"]=current[1]
            return {"state":"turn_available","packet":public,"packet_not_model_receipt_or_understanding":True}
        if name=="study.operation":
            require(set(args)=={"operation_id"} and type(args["operation_id"]) is str,"OWN_OPERATION_LOOKUP")
            operation=self.world.operations.get((scope.role,args["operation_id"]))
            return {"found":operation is not None,"operation_id":args["operation_id"],
                "result":deepcopy(operation[1]) if operation is not None else None,
                "source":"actual_World_operation_table_not_transport_inference"}
        if name=="study.submit":
            require(set(args)=={"turn_handle","decision"} and type(args["turn_handle"]) is str,"STUDY_SUBMISSION_FIELDS")
            current=self._turn_handles.get(scope.role);pending=self.logical.pending
            require(current is not None and secrets.compare_digest(current[1],args["turn_handle"])
                    and pending is not None and pending["actor"]==scope.role
                    and pending["turn_token"]==current[0],"EXACT_CURRENT_ROLE_TURN")
            before=len(self.world.history)
            result=self.logical.submit(current[0],args["decision"])
            self._turn_handles.pop(scope.role,None)
            self._condition.notify_all()
            if self.after_submit is not None:
                try:self.after_submit(scope,result,before)
                except Exception:
                    self.poisoned=True;raise RuntimeError("POST_COMMIT_NOTICE_CAPTURE_OUTCOME_UNKNOWN") from None
            return result
        raise ValueError("UNKNOWN_STUDY_TOOL")
