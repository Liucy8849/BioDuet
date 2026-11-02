"""One real-data scientific host over existing kernels and stores.
Root supplies current protected resource authority and actual transport binding.
No analysis executor, fixed solver, fabricated job, model or subprocess is used.
"""
import os,json,hashlib,secrets,math,time,threading,re
from pathlib import Path
from copy import deepcopy
from .contracts_v01 import Scope,require
from .score_bridge_v01 import read_pinned
from .dataset_v01 import DatasetBank
from .participant_session_v01 import ParticipantSession
from .native_artifact_snapshots_v01 import ScopedNativeArtifactSnapshots
from .native_science_world_v03 import NativeArtifactRecoveryWorld,PROFILE
from .native_artifact_world_port_v01 import BrokeredNativeArtifactWorld,CONTRACT
from .logical_study_endpoint_v06 import LogicalStudyEndpoint
from bioduet_eval.bioduet_logical_v02 import LogicalSession
from bioduet_eval.bioduet_recovery_world_v02 import sha as original_World_request_sha
from .participant_observer_v04 import request_sha256
from scientific_episode_capture_v02 import EpisodeCapture
from scientific_world_observation_v03 import ObservedScienceWorld,ObservedLogicalSession

def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def write_new(path,raw):
    path=Path(path);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as out:out.write(raw);out.flush();os.fsync(out.fileno())
    require(path.read_bytes()==raw,"NEW_HOST_BYTES_READBACK")
    return {"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def json_new(path,value):return write_new(path,canonical(value)+b"\n")
def pinned(row,max_bytes=32*1024*1024):
    p=Path(row["path"]);require(p.is_absolute(),"ROOT_PINNED_INPUT_PATH")
    raw=read_pinned(p.parent,p.name,row["sha256"],max_bytes=max_bytes)
    require(len(raw)==row["bytes"],"ROOT_PINNED_INPUT_SIZE");return raw

def project_role_input(role,name,raw):
    # Real counts/genes and all biological record values remain unchanged.
    # The historical A file carries observation_profile=analysis_anomaly, which
    # describes its preparation, not this current change_notice protocol.
    if role!="A" or name!="records.json":return raw
    original=json.loads(raw)
    require(original.get("schema")=="bioduet-analysis-declaration-view/1",
            "EXACT_HISTORICAL_DECLARATION_SOURCE")
    projected={k:deepcopy(v) for k,v in original.items() if k!="observation_profile"}
    projected["schema"]="bioduet-role-science-records/1"
    for k in ("libraries","dictionary","counts_sha256","source","cell_type","code_origin"):
        require(projected[k]==original[k],"NO_BIOLOGICAL_DATA_OR_SOURCE_CHANGE")
    return canonical(projected)+b"\n"

class NativeScienceHostComposition:
    def __init__(self,*,root,bindings,actual_admission,authorize_resource,transport_binding_factory):
        require(callable(authorize_resource) and callable(transport_binding_factory),
                "ACTUAL_ROOT_RESOURCE_AND_TRANSPORT_BINDINGS_NO_FIXTURE_DEFAULT")
        self.bindings=deepcopy(bindings);self.admission=deepcopy(actual_admission)
        self.resource=authorize_resource;self.transport_binding=transport_binding_factory;self.root=Path(root)
        require(self.root.is_absolute() and not self.root.exists(),"FRESH_SCIENCE_HOST_ROOT")
        self.deadline=actual_admission["deadline_monotonic"]
        require(type(self.deadline) in (int,float) and math.isfinite(self.deadline)
                and self.deadline>time.monotonic(),"ACTUAL_FINITE_CURRENT_ADMISSION")
        require(bindings["task_id"]=="BW-01" and bindings["information_mode"]=="change_notice",
                "FIRST_NOTICE_SCIENCE_PROFILE")
        require(bindings["source_kind"]=="real_public_data_with_declared_simulated_researcher"
                and bindings["no_preexisting_artifacts_imported"] is True,"REAL_PROFILE_NOT_ENGINEERING_FIXTURE")
        self.identity={k:bindings[k] for k in ("episode_id","attempt_id","project_id")}
        self.scopes={role:Scope(**row) for role,row in bindings["role_scopes"].items()}
        require(set(self.scopes)=={"A","H"} and len({s.principal_id for s in self.scopes.values()})==2,
                "INDEPENDENT_ROLE_SCOPES")
        require(all(re.search(r"(?i)(?:^|[-_/])H[01](?:$|[-_/])",str(value)) is None
            for scope in self.scopes.values() for value in vars(scope).values()),"OPAQUE_ROLE_IDENTIFIERS_NO_EXPERIMENTAL_ARM")
        require(all(s.role==r and all(getattr(s,k)==v for k,v in self.identity.items())
                    for r,s in self.scopes.items()),"ACTUAL_SCOPE_IDENTITY")
        self.root.mkdir(mode=0o700);self.policy=[];self._policy_lock=threading.RLock()
        self.notice_proofs={};self.native_workspace_refs=[];self.session=None;self.capture=None
        self.bank=DatasetBank(max_total_bytes=bindings["dataset_max_bytes"])
        self.native_roots={};self.public_input_refs={};self.role_tasks={}
        (self.root/"capture").mkdir(mode=0o700)
        self.capture=EpisodeCapture(self.root/"capture",**self.identity,
            clock_domain=bindings["actual_clock_domain"],boot_id=bindings["actual_boot_id"],
            composition_sha256=bindings["composition_sha256"],
            transport_binding_factory=transport_binding_factory)
        self.authorize=self.capture.wrap_authorize_tool(self._authorize)
        self.session=ParticipantSession(self.root/"participant",**self.identity,
            information_mode="change_notice",scopes=list(self.scopes.values()),
            authorize_tool=self.authorize,verify_commit=self._verify_notice,
            authorize_notice_read=self._authorize_notice_read,datasets=self.bank)
        # The source class is unchanged; new profile storage limits must be frozen
        # explicitly by Root and covered by the current hard filesystem limits.
        file_limit=bindings["workspace_max_file_bytes"];total_limit=bindings["workspace_max_total_bytes"]
        require(type(file_limit) is int and type(total_limit) is int and
                1<=file_limit<=16*1024*1024 and file_limit<=total_limit<=64*1024*1024,
                "FROZEN_FINITE_STORAGE_CONFIGURATION")
        self.session.workspace.max_file=file_limit;self.session.workspace.max_total=total_limit
        self.capture.bind_existing_session(self.session)
        role_inputs=self.root/"role-inputs";role_inputs.mkdir(mode=0o700)
        native=self.root/"native";native.mkdir(mode=0o700)
        records={}
        for role,scope in self.scopes.items():
            rd=role_inputs/role;rd.mkdir(mode=0o700)
            nr=native/role;nr.mkdir(mode=0o700);self.native_roots[role]=nr
            materialized=[]
            for item in bindings["role_inputs"][role]:
                name=item["public_name"]
                require(type(name) is str and name not in ("",".","..") and
                        "/" not in name and "\\" not in name,"PUBLIC_BASENAME_ONLY")
                original_raw=pinned(item["source"])
                if name=="records.json":records[role]=json.loads(original_raw)
                raw=project_role_input(role,name,original_raw)
                # Counts/genes are byte-exact; A record protocol-only projection is explicit.
                ref=write_new(rd/name,raw);object_id=secrets.token_urlsafe(18)
                self.bank.register(scope,object_id,root=rd,relative=name,expected_sha256=ref["sha256"])
                materialized.append({**ref,"public_name":name,"object_id":object_id,
                                     "actor_path":"/inputs/data/"+name,"read_only_mount_required":True,
                    "original_source_ref":deepcopy(item["source"]),
                    "projection":"drop_legacy_observation_profile_new_records_schema_no_biological_changes"
                        if raw!=original_raw else "byte_exact"})
            self.public_input_refs[role]=materialized
        require(set(records)=={"A","H"},"ROLE_RECORDS_INPUTS")
        a=records["A"];h=records["H"]
        require(set(a)=={"cell_type","code_origin","counts_sha256","dictionary","libraries",
                        "observation_profile","schema","source"} and
                set(h)=={"boundary","records","schema","source"},"EXACT_EXISTING_ROLE_RECORD_SCHEMAS")
        declared=[{k:r[k] for k in ("library_id","donor_id","condition")} for r in a["libraries"]]
        hsource=[{k:r[k] for k in ("library_id","donor_id","condition")} for r in h["records"]]
        counts=[r for r in self.public_input_refs["A"] if r["public_name"]=="counts.tsv"]
        require(len(counts)==1 and a["counts_sha256"]==counts[0]["sha256"],"ACTUAL_COUNTS_BINDING")
        href=[r for r in self.public_input_refs["H"] if r["public_name"]=="records.json"][0]
        self.snapshots=ScopedNativeArtifactSnapshots(self.root/"native-artifact-custody",
            role_roots=self.native_roots,role_scopes=self.scopes,
            authorize_read=self._authorize_snapshot,max_bytes=file_limit)
        dataset={"samples":deepcopy(a["libraries"]),"counts":{"sha256":counts[0]["sha256"]},
                 "source":deepcopy(a["source"]),"cell_type":a["cell_type"]}
        self.world=NativeArtifactRecoveryWorld(dataset=dataset,declared_records=declared,
            H_source_records=hsource,H_source_sha256=href["sha256"],
            human_scope_library_ids=[r["library_id"] for r in hsource],
            artifact_snapshot=self._snapshot_to_existing_workspace,
            verify_artifact_snapshot=self.snapshots.verify,evidence_at=0)
        self.brokered=BrokeredNativeArtifactWorld(self.world)
        self.world_binding={"schema":"bioduet-single-native-science-world-binding/1",
            "profile":PROFILE,"port_contract":CONTRACT,"capture_identity":self.identity,
            "world_project_id":self.brokered._port.project_id,
            "world_episode_id":self.brokered._port.episode_id,
            "roles":{r:{"capture_principal_id":s.principal_id,
                "world_principal_id":self.brokered._contexts[r].principal_id}
                for r,s in self.scopes.items()},
            "source_kind":bindings["source_kind"],"initial_artifacts":[],"initial_publications":[],
            "canonical_World_instances":1,"dataset_Bank_instances":1}
        worldref=json_new(self.root/"world-binding.json",self.world_binding)
        self.observed_world=ObservedScienceWorld(self.brokered,capture=self.capture,
            role_scopes=self.scopes,instance_binding_ref=worldref)
        self.logical_raw=LogicalSession(self.observed_world,deadline=None,max_turns=None)
        self.logical=ObservedLogicalSession(self.logical_raw,capture=self.capture,
                                           observed_world=self.observed_world)
        self.logical_binding={**self.world_binding,"world_binding_ref":worldref,
            "logical_episode_id":self.logical_raw.episode_id,"logical_deadline":None,"max_turns":None,
            "native_filesystem_binding":"one native directory per actual Scope; exact existing-file snapshots into existing ParticipantSession Workspace; no duplicate execution"}
        self.binding_ref=json_new(self.root/"world-logical-binding.json",self.logical_binding)
        self.endpoint=LogicalStudyEndpoint(logical_session=self.logical,participant_session=self.session,
            world_owner=self.world,role_scopes=self.scopes,authorize=self._authorize,
            participant_bridge_factory=self.capture.bridge,deadline_monotonic=self.deadline,
            trace=self._trace,after_logical_submit=self._after_logical_submit)
        for role in self.scopes:
            task={"schema":"bioduet-science-loop-role-public-task/1","task_id":"BW-01",
                "information_mode":"change_notice","role":role,
                "prompt":pinned(bindings["role_public_prompt_refs"][role],max_bytes=65536).decode("utf-8"),
                "data_files":[{"path":r["actor_path"],"bytes":r["bytes"],"sha256":r["sha256"]}
                              for r in self.public_input_refs[role]],
                "artifacts":deepcopy(bindings["role_artifact_specs"][role]),
                "require_any_artifact_groups":deepcopy(bindings["role_artifact_require_any"][role]),
                "available_runtimes":deepcopy(bindings["role_public_runtime_paths"][role]),
                "reference_analysis_script_supplied":False,"experimental_arm_exposed":False}
            require(type(task["prompt"]) is str and task["prompt"],"PINNED_ROLE_PUBLIC_GOAL")
            self.role_tasks[role]=json_new(self.root/("public-task-"+role+".json"),task)
    def _authorize(self,scope,name,args):
        with self._policy_lock:
            issued=self.scopes.get(getattr(scope,"role",None)) is scope
            active=time.monotonic()<self.deadline
            external=self.resource(scope,name,deepcopy(args)) if issued and active else {"allowed":False}
            require(type(external) is dict and type(external.get("allowed")) is bool,"ACTUAL_RESOURCE_AUTHORITY_RECEIPT")
            # No process is launched by JobStore in this profile. Native Terminal is
            # the only analysis backend; query/result/cancel retain original semantics.
            allowed=issued and active and external["allowed"] and name not in ("job.submit","jobs.submit","job.dispatch","jobs.dispatch")
            safe_resource={"allowed":external["allowed"]}
            if external["allowed"]:
                require(all(type(external.get(k)) is str and len(external[k])==64
                    for k in ("source_sha256","current_grant_sha256")) and
                    type(external.get("scope_id")) is str and bool(external["scope_id"]),
                    "CURRENT_PROTECTED_ROOT_RESOURCE_SOURCE_NOT_FIXTURE_ALLOWED_TRUE")
                safe_resource.update({k:external[k] for k in ("scope_id","source_sha256","current_grant_sha256")})
            row={"seq":len(self.policy),"principal_id":getattr(scope,"principal_id",None),
                "role":getattr(scope,"role",None),"tool":name,"allowed":allowed,
                "resource_receipt":safe_resource,"source":"current_episode_business_policy"}
            self.policy.append(row)
            return {"allowed":allowed,"authority_seq":row["seq"],
                    "source_ref":{"sha256":digest(row),"kind":"actual_host_policy_evaluation"}}
    def _authorize_notice_read(self,scope,event):
        return self._authorize(scope,"notice.receive",{"event_id":event["event_id"]})["allowed"]
    def _authorize_snapshot(self,scope,name,operation_id,kind):
        return self._authorize(scope,"native.artifact.snapshot",
            {"name":name,"operation_id":operation_id,"kind":kind})["allowed"]
    def _snapshot_to_existing_workspace(self,role,name,operation_id,kind):
        ref=self.snapshots(role,name,operation_id,kind);require(self.snapshots.verify(ref),"ACTUAL_NATIVE_BYTES")
        raw=Path(ref["path"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==ref["sha256"],"SNAPSHOT_IMPORT_IDENTITY")
        logical="native/"+hashlib.sha256((operation_id+"\0"+kind).encode()).hexdigest()
        wr=self.session.workspace.write(self.scopes[role],logical,raw,code_origin="upstream")
        self.native_workspace_refs.append({"role":role,"operation_id":operation_id,"kind":kind,
            "native_snapshot":ref,"existing_workspace_ref":wr,
            "authorship_and_execution_verified":None,"duplicate_analysis_run":False})
        return ref
    def _verify_notice(self,recipient,event,receipt):
        if self.scopes.get("A") is not recipient:return False
        if type(receipt) is not dict or self.notice_proofs.get(event.get("event_id"))!=receipt:return False
        i=receipt["world_history_index"]
        if not 0<=i<len(self.world.history):return False
        entry=self.world.history[i];req=entry["request"];op=self.world.operations.get(("H",req["operation_id"]))
        return (entry["actor"]=="H" and entry["result"].get("status")=="succeeded"
            and op is not None and op[0]==original_World_request_sha(req) and op[1]==entry["result"]
            and digest(entry)==receipt["world_history_sha256"]
            and event["source_sha256"]==digest(entry)
            and receipt["world_binding_sha256"]==self.binding_ref["sha256"])
    def _after_logical_submit(self,scope,record,before):
        if scope.role!="H":return
        for index in range(before,len(self.world.history)):
            entry=self.world.history[index];request=entry["request"];action=request["action_id"]
            if entry["actor"]!="H" or entry["result"].get("status")!="succeeded" or action not in ("A02","A03","A14"):continue
            source_sha=digest(entry)
            if action=="A03":
                object_id=request["payload"]["library_id"];revision=entry["result"]["version"]
                kind="record_revision_committed"
            else:
                object_id="research-context:"+self.brokered._port.episode_id
                revision=index+1;kind="source_certificate_released" if action=="A02" else "artifact_usage_restricted"
            event={"event_id":source_sha,"object_id":object_id,"revision":revision,
                   "event_kind":kind,"source_sha256":source_sha}
            receipt={"world_history_index":index,"world_history_sha256":source_sha,
                     "world_binding_sha256":self.binding_ref["sha256"],
                     "revision_source":"sample_version" if action=="A03" else "actual_context_commit_log_ordinal"}
            self.notice_proofs[event["event_id"]]=receipt
            self.session.committed_change(self.scopes["A"],event,receipt)
    def _trace(self,scope,name,raw,result):
        binding=self.transport_binding(scope,name,raw,request_sha256(name,raw))
        self.capture.journal.append({"kind":"science_host_endpoint_return_or_rejection",
            "actual_ingress_binding":binding,"study_path":"original ActionBroker/ObservedWorld; participant tools use captured BoundMCP",
            "role":getattr(scope,"role",None),"tool":name,"arguments_json":raw,
            "result":deepcopy(result),"meaning":"transport boundary, not commit/exit/model understanding"})
    def export_private_state(self):
        # No original kernel token, capability, GO, credential or raw provider header.
        state={"schema":"bioduet-science-host-private-state/1","identity":self.identity,
            "binding":self.binding_ref,"world":self.world.snapshot(),"world_history":self.world.history,
            "world_operations":[{"actor":k[0],"operation_id":k[1],"request_sha256":v[0],"result":v[1]}
                                for k,v in self.world.operations.items()],
            "world_native_operation_failures":self.world.native_operation_failures,
            "broker_audit":self.brokered.broker_audit,"port_audit":self.brokered.port_audit,
            "logical_records":self.logical_raw.records,"logical_terminal":self.logical_raw.terminal,
            "logical_pending_actor":None if self.logical_raw.pending is None else self.logical_raw.pending["actor"],
            "policy":self.policy,"endpoint":self.endpoint.audit,"native_snapshots":self.snapshots.audit,
            "native_workspace_refs":self.native_workspace_refs,
            "dataset_audit":self.bank.audit,"workspace_audit":self.session.workspace.audit,
            "scientific_validity":None,"execution_backend":"native_terminal",
            "job_execution_lifecycle":"not_inferred_or_reexecuted"}
        return json_new(self.root/"host-state.json",state)
    def close(self):
        # Closing FDs is not a claim that model/tool descendants are dead.
        if self.session is not None:self.session.close()
        if self.capture is not None:self.capture.close()
