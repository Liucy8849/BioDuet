"""Owned native actor for the real BW01 science-loop work package; preparation only.
Runs ONLY after independent gateway transport qualification and a separate Root
model/SDK/tool admission. Native Agent/Conversation plan and call tools themselves;
this adapter neither writes analysis code nor executes an analysis on their behalf.
No scientific acceptance, actual authority or runtime is inferred from this source.
"""
import argparse,hashlib,json,os,sys,time,traceback,stat,math,re
from urllib.parse import urlsplit
from http.client import HTTPConnection
from pathlib import Path
# Fixed readonly source layout supplied by the independent Root scope.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bioduet_vnext.contracts_v01 import Scope,require,sha
from bioduet_vnext.model_gateway_client_v03 import issue_actor_capability,actor_client_config
from bioduet_vnext.native_science_participant_mcp_v02 import native_science_participant_config

def read_pin(row):
    p=Path(row["path"]);require(p.is_absolute() and not p.is_symlink(),"ACTOR_PINNED_INPUT")
    r=p.read_bytes();require(len(r)==row["bytes"] and hashlib.sha256(r).hexdigest()==row["sha256"],"ACTOR_INPUT_SHA")
    return r
def write_new(path,raw):
    p=Path(path);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
def json_new(path,row):write_new(path,(json.dumps(row,sort_keys=True,allow_nan=False)+"\n").encode())
def wait_control(path,nonce,deadline):
    p=Path(path)
    while time.monotonic()<deadline:
        try:
            require(not p.is_symlink(),"ROOT_CONTROL_SYMLINK")
            data=json.loads(p.read_bytes());require(data.get("nonce")==nonce,"ROOT_CONTROL_NONCE")
            return data
        except (FileNotFoundError,json.JSONDecodeError):time.sleep(.05)
    raise TimeoutError("ACTOR_OUTER_DEADLINE")

def read_artifact_snapshot(path,max_bytes=2097152):
    # Snapshot a regular descriptor once; never block on a FIFO or parse bytes
    # from a later second path read. This is IO integrity, not authorship proof.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=max_bytes,
                "ACTOR_REGULAR_BOUNDED_ARTIFACT")
        chunks=[];total=0
        while True:
            chunk=os.read(fd,min(65536,max_bytes+1-total))
            if not chunk:break
            chunks.append(chunk);total+=len(chunk)
            require(total<=max_bytes,"ACTOR_ARTIFACT_GREW_OVER_BOUND")
        raw=b"".join(chunks);after=os.fstat(fd)
        fields=("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")
        require(all(getattr(before,k)==getattr(after,k) for k in fields)
                and len(raw)==after.st_size,"ACTOR_ARTIFACT_CHANGED_DURING_READ")
        current=os.stat(path,follow_symlinks=False)
        require(stat.S_ISREG(current.st_mode) and
                all(getattr(after,k)==getattr(current,k) for k in fields),
                "ACTOR_ARTIFACT_PATH_REPLACED")
        return raw
    finally:os.close(fd)

def run(proof):
    require(proof.get("schema")=="bioduet-root-openhands-science-loop-actor/1"
            and proof.get("tool_profile") in ("common_environment_native_science_A","common_environment_simulated_researcher_H")
            and proof.get("model_call_limit") is None and proof.get("model_turn_limit") is None,
            "ROOT_ACTOR_PROFILE")
    require(proof.get("gateway_runtime_review_sha256")=="a3c6ebacd0f04c81d28a11919cfa102b536b916f386dfc6fae2db7776a235980"
            and sha(proof.get("provider_scope_ref_sha256")),"ACCEPTED_LIVE_PROVIDER_AND_FROZEN_SCOPE_NOT_EARLY_MODEL_LEASE")
    require(os.getuid()==1008 and os.getgroups()==[] and
            type(proof.get("deadline_monotonic")) in (int,float)
            and math.isfinite(proof["deadline_monotonic"]) and
            proof["deadline_monotonic"]>time.monotonic(),"EMPTY_GROUP_FINITE_ACTOR_SCOPE")
    require(os.environ.get("LITELLM_MODE")=="PRODUCTION"
            and os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP","").lower()=="true",
            "OFFLINE_LITELLM_METADATA_NO_DOTENV")
    for row in proof["readonly_input_manifest"]:read_pin(row)
    require(proof["SDK_model"]=="openai/"+proof["provider_model"],"FIXED_OPENAI_COMPATIBLE_ROUTE")
    workspace=Path(proof["workspace"]);output=Path(proof["output"])
    require(workspace.is_absolute() and output.is_absolute() and workspace.is_dir() and output.is_dir(),
            "ROOT_WORKSPACE")
    task_raw=read_pin(proof["public_task"])
    require(len(task_raw)<=131072,"BOUNDED_PUBLIC_TASK")
    task=json.loads(task_raw)
    require(task.get("schema")=="bioduet-science-loop-role-public-task/1"
            and task.get("task_id")=="BW-01" and task.get("information_mode")=="change_notice"
            and task.get("role")==proof["actor_scope"]["role"]
            and task["role"] in ("A","H") and type(task.get("prompt")) is str
            and bool(task["prompt"]) and task.get("reference_analysis_script_supplied") is False,
            "REAL_SCIENCE_PUBLIC_ROLE_TASK_NOT_SOLVER")
    method_scope_addendum_raw=read_pin(task["public_method_scope_addendum"])
    require(hashlib.sha256(method_scope_addendum_raw).hexdigest()=="3657c2a3bcff00c73479c66552b5fa41be81812ae5f0c23147704df4409554bb",
            "FIXED_PUBLIC_S_METHOD_SCOPE_CLARIFICATION_V2")
    require(proof["tool_profile"]=={"A":"common_environment_native_science_A","H":"common_environment_simulated_researcher_H"}[task["role"]],"ROLE_SPECIFIC_TOOL_PROFILE")
    require(task.get("experimental_arm_exposed") is False and
            not any(k in task for k in ("experimental_arm","operator_seed","oracle","reference_answer")),
            "NO_OPERATOR_ARM_OR_ANSWER_IN_PUBLIC_TASK")
    require(type(task.get("data_files")) is list and bool(task["data_files"]),"REAL_ROLE_DATA_REQUIRED")
    for row in task["data_files"]:
        require(Path(row["path"]).is_absolute() and
                re.search(r"(?:^|[-_/])H[01](?:$|[-_/])",row["path"],re.I) is None,
                "OPAQUE_ROLE_DATA_PATH_NOT_HOST_ARM")
        read_pin(row)
    require(type(task.get("artifacts")) is list and len(task["artifacts"])<=16,"BOUNDED_ARTIFACT_DECLARATIONS")
    names=set()
    for row in task["artifacts"]:
        name=row["name"]
        require(type(name) is str and name not in ("",".","..") and
                "/" not in name and "\\" not in name and name not in names,
                "ARTIFACT_NAME_ONLY_NO_PARENT_SYMLINK_TRAVERSAL")
        require(type(row.get("required")) is bool and type(row.get("max_bytes")) is int
                and 0<row["max_bytes"]<=16777216,"FINITE_ARTIFACT_IO_BOUND")
        names.add(name)
        require(not (workspace/name).exists() and not (workspace/name).is_symlink(),
                "NO_PREWRITTEN_SOLUTION_OR_EXISTING_OUTPUT_ASSUMED")
    scope=Scope(**proof["actor_scope"]);cap=issue_actor_capability(scope)
    json_new(proof["actor_ready_output"],{"nonce":proof["nonce"],"scope":proof["actor_scope"],
        "capability_sha256":cap.sha256,"PID":os.getpid(),"provider_credentials_read":False,
        "model_call_limit":None,"model_turn_limit":None,"Agent_constructed":False})
    ready=wait_control(proof["gateway_ready_input"],proof["nonce"],proof["deadline_monotonic"])
    require(ready.get("capability_sha256")==cap.sha256 and ready.get("scope")==proof["actor_scope"],
            "PRIVATE_GATEWAY_SCOPE")
    config=actor_client_config(gateway_base_url=ready["address"],capability=cap,model=proof["SDK_model"])
    endpoint=urlsplit(config["connection"]["base_url"])
    remaining=proof["deadline_monotonic"]-time.monotonic()
    require(remaining>0,"ACTOR_START_DEADLINE")
    probe=json.dumps({"model":proof["provider_model"],"messages":[{"role":"user","content":
        "Pre-admission gate check; must be rejected before provider dispatch."}],
        "max_tokens":1,"stream":False}).encode()
    connection=HTTPConnection("127.0.0.1",endpoint.port,timeout=min(10.,remaining))
    try:
        connection.request("POST","/v1/chat/completions",body=probe,headers={
            "Content-Type":"application/json","Authorization":"Bearer "+cap.value})
        response=connection.getresponse();body=response.read(65537)
        require(len(body)<=65536 and response.status==403,"NATIVE_MODEL_PASSIVE_REQUEST_NOT_REJECTED")
        json_new(proof["actor_pre_admission_output"],{"nonce":proof["nonce"],
            "capability_sha256":cap.sha256,"pre_admission_http_status":403,
            "request_sha256":hashlib.sha256(probe).hexdigest(),
            "response_sha256":hashlib.sha256(body).hexdigest(),
            "SDK_imported":False,"Agent_constructed":False,
            "actor403_not_alone_proof_of_private_secret_lookup_timing":True})
    finally:connection.close()
    control=wait_control(proof["actor_go_input"],proof["nonce"],proof["deadline_monotonic"])
    require(control.get("phase")=="controller_admitted_model_engineering_actor"
            and control.get("scope_ref_sha256")==proof["provider_scope_ref_sha256"]
            and sha(control.get("admission_ref_sha256"))
            and control.get("model")==proof["provider_model"]
            and type(control.get("deadline_monotonic")) in (int,float)
            and math.isfinite(control["deadline_monotonic"])
            and time.monotonic()<control["deadline_monotonic"]<=proof["deadline_monotonic"],
            "ACTUAL_POST_READY_CURRENT_MODEL_ADMISSION")
    json_new(output/"model-admission-observation.json",{
        "scope_ref_sha256":control["scope_ref_sha256"],
        "admission_ref_sha256":control["admission_ref_sha256"],
        "model":control["model"],"observed_after_valid_cap403_ACK":True,
        "trusted_Root_OS_control_and_actual_dispatch_still_require_independent_review":True})
    # The candidate overlay needs its own accepted zero-model wire review.
    # No old nullable SDK success or live JSON/SSE review extends to this source.
    require(proof.get("SDK_serialization_accepted") is True and
            proof.get("SDK_model")=="openai/deepseek-flash",
            "FRESH_COMPATIBILITY_ACCEPTANCE_REQUIRED")
    read_pin(proof["SDK_serialization_acceptance_review"])
    require(proof.get("SDK_serialization_acceptance_scope")==
            "combined_unchanged_prior_and_fresh_affected_subset",
            "EXPLICIT_COMBINED_WINDOW_QUALIFICATION_NOT_FRESH9")
    require(proof["SDK_source_pins"]["bytes"]==56382 and
            proof["SDK_source_pins"]["sha256"]==
            "0fb813380a02861b7c7216a6b3f9d8dbc2c1409e434f501af9de8ee6205fa46b",
            "EXACT_DEEPSEEK_COMPATIBILITY_SOURCE_MANIFEST")
    # Root independently binds accepted review bytes and all 323 candidate files.
    # Never silently import the installed stock or prior nullable overlay.
    source_root=Path(proof["SDK_source_root"])
    require(source_root.is_absolute() and not source_root.is_symlink(),"QUALIFIED_SDK_SOURCE_ROOT")
    source_root=source_root.resolve(strict=True)
    pins=json.loads(read_pin(proof["SDK_source_pins"]))
    require(type(pins.get("files")) is list and len(pins["files"])==323,"ALL323_QUALIFIED_SDK_SOURCES")
    for item in pins["files"]:
        relative=Path(item["path"])
        require(not relative.is_absolute() and all(p not in (".","..","") for p in relative.parts),
                "SDK_SOURCE_RELATIVE_PATH")
        target=source_root/relative
        require(target.resolve(strict=True).is_relative_to(source_root),"SDK_SOURCE_WITHIN_VIEW")
        read_pin({"path":str(target),"bytes":item["bytes"],"sha256":item["sha256"]})
    sys.path.insert(0,str(source_root))
    # Imports/construction are deliberately deferred until actual fresh admission.
    from pydantic import SecretStr
    import openhands.sdk
    from openhands.sdk import Agent,Conversation,LLM,Tool
    require(Path(openhands.sdk.__file__).resolve().is_relative_to(source_root),"NO_INSTALLED_SDK_OVERLAY_FALLBACK")
    from openhands.sdk.tool.registry import register_tool
    from openhands.tools.terminal.definition import TerminalTool
    from openhands.tools.file_editor.definition import FileEditorTool
    # The exact official tool actions/executors remain native. Only permission
    # checks precede their invocation; no platform analysis or planner is added.
    if task["role"]=="A":
        from bioduet_vnext.science_execution_gate_v06 import ScienceExecutionGate,PendingScientificExecution
        from bioduet_vnext.scoped_native_science_tools_v07 import register_scoped_native_tools
        prefit_gate=ScienceExecutionGate(proof["science_prefit_gate"],proof["actor_scope"],str(workspace))
        register_scoped_native_tools(prefit_gate)
    else:prefit_gate=None
    # This normal public constraint card is identical for A/H and both arms.
    # It supplies scope/allowed parameter versions, never formula/solver/truth.
    method_scope_raw=read_pin(proof["public_method_scope_card"])
    require(hashlib.sha256(method_scope_raw).hexdigest()=="808049e0bc00be3d15ec68e60c1f5f3af0ead063ad0c670945bc67142f5689b3","FIXED_PUBLIC_S_METHOD_SCOPE_CARD")
    connection=config["connection"]
    llm=LLM(model=connection["model"],api_key=SecretStr(connection["api_key"]),base_url=connection["base_url"])
    mcp_config=native_science_participant_config(proof,read_pin)
    actor_tools=[]
    if task["role"]=="A":
        actor_tools=[Tool(name="TerminalTool",params={
            "terminal_type":"subprocess","shell_path":proof["fixed_bash"]["path"],
            "no_change_timeout_seconds":10,"env":{"HOME":os.environ["HOME"],"PATH":proof["fixed_child_PATH"]}}),
            Tool(name="FileEditorTool")]
    agent=Agent(llm=llm,mcp_config=mcp_config,tools=actor_tools)
    event_index=[]
    def observe(event):
        serialized=event.model_dump_json().replace(cap.value,"[ACTOR_CAPABILITY]")
        r=(serialized+"\n").encode();name="event-"+str(len(event_index)).zfill(6)+".json"
        write_new(output/name,r);event_index.append({"path":name,"bytes":len(r),
            "sha256":hashlib.sha256(r).hexdigest(),"origin":"actual_native_SDK_callback"})
    prompt=task["prompt"]
    prompt+=("\nUse your issued tools and the available data. You may ask your collaborator for source evidence "
        "or scientific help when needed. Perform computations with real tools, retain errors and corrections, "
        "and make results and interpretations traceable to their actual input revisions. "
        "Acknowledge uncertainty and distinguish data checks from biological validation.")
    if task["role"]=="A":
        prompt+=("\nYour available fixed Python is "+proof["fixed_Python"]["path"]+
                 ". Additional permitted runtimes, if any, are listed in the task. "
                 "Write your own analysis code rather than fabricate execution records. "
                 "Requested artifact names: "+", ".join(row["name"] for row in task["artifacts"])+".")
    prompt+=chr(10)+"Task-published runtime availability (not execution permission): "+json.dumps(task.get("available_runtimes",{}),ensure_ascii=False,sort_keys=True)
    prompt+=chr(10)+"For A scientific execution, this profile admits only a literal invocation of the task-published Rscript path with --vanilla and the actual reviewed immutable script after the separate scope and current scientific-execution gates. Python orchestration, inline code and shell pipelines are outside that scientific-execution interface. Do not treat the adapter fixed Python path as scientific execution permission."
    prompt+="\n\nProject-approved method scope (scientific execution remains gated independently):\n"+method_scope_raw.decode("utf-8")
    prompt+=chr(10)+chr(10)+"Public method-scope clarification (same for A/H and both arms):"+chr(10)+method_scope_addendum_raw.decode("utf-8")
    json_new(output/"prompt-manifest.json",{"prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
        "public_task_sha256":proof["public_task"]["sha256"],"role":task["role"],
        "public_method_scope_sha256":hashlib.sha256(method_scope_raw).hexdigest(),
        "public_method_scope_addendum_sha256":hashlib.sha256(method_scope_addendum_raw).hexdigest(),
        "prompt_includes_public_method_scope":True,
        "prewritten_analysis_script_supplied":False,"scientific_method_or_answer_supplied_by_adapter":False,
        "model_call_limit":None,"model_turn_limit":None,"condenser_and_system_prompt":"native_Agent_defaults",
        "stuck_detection":"native_Conversation_default_preserved","full_native_configuration":False})
    conversation=None;failure=None;close_error=None
    started=time.monotonic_ns()
    try:
        conversation=Conversation(agent=agent,workspace=str(workspace),
            persistence_dir=str(output/"native-persistence"),callbacks=[observe],
            max_iteration_per_run=None,delete_on_close=False)
        conversation.send_message(prompt)
        json_new(output/"initial-public-task-send-receipt.json",{
            "schema":"bioduet-native-initial-public-task-send/1",
            "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
            "public_task_sha256":proof["public_task"]["sha256"],
            "public_method_scope_sha256":hashlib.sha256(method_scope_raw).hexdigest(),
            "public_method_scope_addendum_sha256":hashlib.sha256(method_scope_addendum_raw).hexdigest(),
            "role":task["role"],"SDK_send_message_returned":True,
            "model_read_or_understanding_verified":None})
        # SDK's normal runtime warns and continues when an MCP server fails.
        # This qualification must instead fail before the first model call.
        tools=conversation.agent.tools_map
        from openhands.sdk.tool import FinishTool,ThinkTool
        for offered in tools.values():
            official_mcp=(type(offered).__module__=="openhands.sdk.mcp.tool" and type(offered).__name__=="MCPToolDefinition")
            expected=type(offered) in (TerminalTool,FileEditorTool,FinishTool,ThinkTool)
            require(official_mcp or expected,"NO_UNGATED_ADDITIONAL_TOOL_OR_SUBAGENT_EXECUTION_ROUTE")
            if type(offered) in (TerminalTool,FileEditorTool):
                require(task["role"]=="A" and getattr(offered.executor,"science_gate",None) is prefit_gate,"ACTUAL_NATIVE_EXECUTOR_PERMISSION_WRAPPER_REQUIRED")
        native_mcp=[t for t in tools.values() if type(t).__module__=="openhands.sdk.mcp.tool"
                    and type(t).__name__=="MCPToolDefinition"]
        require(len(native_mcp)==1 and native_mcp[0].mcp_tool.name.endswith("bioduet_invoke"),
                "NATIVE_MCP_TOOL_MUST_NOT_SILENTLY_DISAPPEAR")
        json_new(output/"native-MCP-tool-offering.json",{
            "native_tool_names":list(tools),"MCP_tool_name":native_mcp[0].name,
            "input_schema_sha256":hashlib.sha256(json.dumps(
                native_mcp[0].mcp_tool.inputSchema,sort_keys=True).encode()).hexdigest(),
            "registration_only_not_actual_Agent_use":True,
            "actual_notice_calls_require_independent_child_JSON_RPC_audit":True})
        conversation.run()
        # A normal native conversation may finish while awaiting external scope.
        # Keep that same conversation/World; resume only on new protected status.
        # This is a platform-permission notification, never a solution or planner.
        seen_permission_receipts=set()
        while prefit_gate is not None and prefit_gate.awaiting_scope:
            json_new(output/("prefit-source-ready-"+str(len(seen_permission_receipts))+".json"),{
                "schema":"bioduet-science-prefit-source-ready/1","state":"actual_source_captured_scientific_execution_pending",
                "source_requests":prefit_gate.audit,"scientific_fit_started_by_this_notice":False})
            ready=None
            while time.monotonic()<prefit_gate.cfg["unit_deadline_monotonic"]:
                try:
                    _,ref,command=prefit_gate.current_approved_execution()
                    if ref["sha256"] not in seen_permission_receipts:ready=("permission",ref,command);break
                except PendingScientificExecution:pass
                try:
                    feedback,fref=prefit_gate.current_scope_feedback()
                    if fref["sha256"] not in seen_permission_receipts:ready=("author_scope_feedback",fref,feedback["actor_message"]);break
                except PendingScientificExecution:pass
                time.sleep(0.25)
            require(ready is not None,"SCIENTIFIC_EXECUTION_SCOPE_PENDING_AT_FINITE_UNIT_END")
            control_kind,ref,control_text=ready;seen_permission_receipts.add(ref["sha256"])
            if control_kind=="permission":
                permission_message="New protected platform execution status is available. Scientific judgment remains separate. The current immutable approved command is: "+control_text+". Continue the same scientific task using normal tools; do not assume a scientific verdict."
            else:
                permission_message="Author method-scope feedback is available for your submitted code; this is not H assistance, an independent scientific verdict, or execution permission. "+control_text+". Revise your own code if needed and submit the complete changed closure. No command was executed by this feedback."
            conversation.send_message(permission_message)
            json_new(output/("platform-permission-resume-"+str(len(seen_permission_receipts))+".json"),{
                "schema":"bioduet-native-conversation-platform-permission-notice/1",
                "source_kind":"platform_execution_permission_not_H" if control_kind=="permission" else "operator_author_method_scope_feedback_not_H",
                "actual_protected_receipt_sha256":ref["sha256"],
                "message_sha256":hashlib.sha256(permission_message.encode()).hexdigest(),
                "SDK_send_message_returned":True,"model_read_or_understanding_verified":None})
            conversation.run()
    except BaseException as exc:
        failure=type(exc).__name__
        write_new(output/"actor-failure.txt",traceback.format_exc().replace(cap.value,"[ACTOR_CAPABILITY]").encode())
    finally:
        if conversation is not None:
            try:conversation.close()
            except BaseException as exc:close_error=type(exc).__name__
    files={};artifact_raw={}
    for item in task["artifacts"]:
        name=item["name"]
        try:
            r=read_artifact_snapshot(workspace/name,max_bytes=item["max_bytes"]);artifact_raw[name]=r
            files[name]={"bytes":len(r),"sha256":hashlib.sha256(r).hexdigest(),"kind":item.get("kind")}
        except FileNotFoundError:
            files[name]={"present":False,"required":item["required"]}
        except (OSError,AssertionError,ValueError) as exc:
            files[name]={"error_type":type(exc).__name__,"stable_regular_snapshot":False}
    structurally_complete=all(not row["required"] or row["name"] in artifact_raw for row in task["artifacts"])
    groups=task.get("require_any_artifact_groups",[])
    assert type(groups) is list and len(groups)<=8,"FINITE_ARTIFACT_REQUIREMENT_GROUPS"
    known={item["name"] for item in task["artifacts"]}
    for group in groups:
        assert type(group) is list and 1<=len(group)<=16 and all(type(name) is str and name in known for name in group),"KNOWN_ARTIFACT_GROUP"
        structurally_complete=structurally_complete and any(name in artifact_raw for name in group)
    report={"schema":"bioduet-openhands-science-loop-native-actor-observation/1","nonce":proof["nonce"],
        "task_id":"BW-01","role":task["role"],"information_mode":"change_notice",
        "model_source_kind":proof["model_source_kind"],"tool_profile":proof["tool_profile"],
        "native_Agent_constructed":True,"native_MCP_configured":True,
        "MCP_world_and_messages_require_actual_host_and_child_RPC_evidence":True,
        "actual_World_and_execution_authority_not_inferred_from_tool_registration":True,
        "native_Conversation_max_iteration_per_run":None,"model_call_limit":None,"model_turn_limit":None,
        "event_index":event_index,"artifact_files":files,"required_artifacts_present":structurally_complete,
        "artifact_snapshot_bytes_used_for_hash_are_same":True,"failure_type":failure,
        "native_close_exception":close_error,"started_ns":started,"completed_ns":time.monotonic_ns(),
        "agent_code_origin_requires_independent_trace_linkage":True,
        "interpreter_actual_execution_requires_independent_descendant_trace_linkage":True,
        "provider_cost_and_H_help_actual_sources_require_separate_collectors":True,
        "SDK_cost_estimate_is_provider_bill":False,"provider_bill":None,
        "process_retirement_requires_Root_independent_review":True,
        "scientific_episode_accepted":False,"independent_method_or_output_review_inferred":False,
        "blinding_requires_actual_OS_paths_logs_and_Role_view_checks":True,
        "full_native_end_to_end_qualified":False,"formal_score":None,"strict_score":None}
    json_new(output/"actor-observation.json",report)
    if failure or close_error or not structurally_complete:
        raise RuntimeError("NATIVE_SCIENCE_ACTOR_EXECUTION_OR_REQUIRED_ARTIFACTS_INCOMPLETE")
def main():
    p=argparse.ArgumentParser();p.add_argument("--proof",required=True);p.add_argument("--proof-sha256",required=True)
    args=p.parse_args();r=Path(args.proof).read_bytes()
    require(hashlib.sha256(r).hexdigest()==args.proof_sha256,"ROOT_ACTOR_PROOF_SHA")
    run(json.loads(r))
if __name__=="__main__":main()
