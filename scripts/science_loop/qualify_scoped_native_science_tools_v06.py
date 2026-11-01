"""Four actual fixed191/SDK/tool-factory permission ABI checks; all inputs synthetic.
No Agent/LLM/R/real data/subprocess executor. A supplied fake terminal counter
must remain0. Root independently controls import/bootstrap/syscall observation.
"""
import argparse,json,os,sys,time,math,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bioduet_vnext.science_execution_gate_v06 import stable,digest,check,PACKET,ScienceExecutionGate,ScientificGateIntegrityError

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--proof",required=True);ap.add_argument("--proof-sha256",required=True);a=ap.parse_args();raw=stable(a.proof,1024*1024,True);check(digest(raw)==a.proof_sha256,"CURRENT_PROOF_SHA");p=json.loads(raw)
    check(p["schema"]=="bioduet-root-scoped-science-tools-ABI/1" and p["source_kind"]=="synthetic_tool_permission_ABI_only" and sys.version_info[:3]==(3,12,10),"FIXED_CURRENT_ZERO_MODEL_ABI_SCOPE")
    check(os.geteuid()==1008 and os.getgroups()==[],"ACTUAL_SCOPED_UID_GROUPS")
    check(math.isfinite(p["unit_deadline_monotonic"]) and time.monotonic()<p["unit_deadline_monotonic"],"FINITE_CURRENT_ABI_SCOPE")
    check(p["fixed191_installation_review_sha256"]=="547d9c182ce5fe53cb6841b910acdc310fce22b8eee99b32b304daa4cb0687da" and p["SDK03_affected_review_sha256"]=="966405e08242d62296280d593c7fbb3f2143820250f18b56ea6be5596f1cd38a","EXACT_ACCEPTED_BASELINE_NOT_INHERITED_NEW_ABI")
    manifest=p["source_manifest_ref"];mraw=stable(manifest["path"],2*1024*1024,True);check(len(mraw)==manifest["bytes"] and digest(mraw)==manifest["sha256"],"ACTUAL_SOURCE_MANIFEST")
    for row in json.loads(mraw)["files"]:
        b=stable(row["path"],32*1024*1024);check(len(b)==row["bytes"] and digest(b)==row["sha256"],"ALL_ROOT_FIXED_SOURCE_INPUTS")
    for root in reversed(p["readonly_import_roots"]):sys.path.insert(0,root)
    os.environ["PRODUCTION"]="1";os.environ["LITELLM_LOCAL_MODEL_COST_MAP"]="True"
    from types import SimpleNamespace
    from openhands.sdk import Tool
    from openhands.sdk.tool import ToolExecutor
    from openhands.sdk.tool.registry import resolve_tool
    from openhands.tools.terminal.definition import TerminalTool,TerminalAction,TerminalObservation
    from openhands.tools.file_editor.definition import FileEditorTool,FileEditorAction
    from bioduet_vnext.scoped_native_science_tools_v07 import register_scoped_native_tools
    class NoModelVision:
        def vision_is_active(self):return False
        def __getattr__(self,key):raise AssertionError("NO_MODEL_INTERFACE_IN_FIXTURE:"+key)
    class NoExecutionCounter(ToolExecutor):
        def __init__(self):self.calls=0
        def __call__(self,action,conversation=None):
            self.calls+=1;raise AssertionError("UNREVIEWED_COMMAND_REACHED_EXECUTOR")
        def close(self):pass
    results=[]
    with tempfile.TemporaryDirectory(dir=p["private_output_root"]) as td:
        root=Path(td);work=root/"workspace";work.mkdir();persist=root/"observations";persist.mkdir();scope={"role":"A","episode_id":"synthetic-e","attempt_id":"synthetic-a","project_id":"synthetic-p","principal_id":"synthetic-person"}
        cfg={"schema":"bioduet-root-science-prefit-gate-config/1","actor_scope":scope,"method_packet_sha256":PACKET,"unit_deadline_monotonic":p["unit_deadline_monotonic"],"private_gate_journal_root":str(root/"guard-private"),"max_private_capture_bytes":128*1024*1024,"public_readonly_view_refs":[],"gate_pointer_path":str(root/"not_issued"),"qualified_environment_manifest_sha256":"1"*64,"fixed_Rscript_path":"/synthetic/not_executed/Rscript"}
        gate=ScienceExecutionGate(cfg,scope,work);register_scoped_native_tools(gate);state=SimpleNamespace(workspace=SimpleNamespace(working_dir=str(work)),env_observation_persistence_dir=str(persist),agent=SimpleNamespace(llm=NoModelVision()));counter=NoExecutionCounter()
        terminal=resolve_tool(Tool(name="TerminalTool",params={"executor":counter}),state)[0];editor=resolve_tool(Tool(name="FileEditorTool"),state)[0]
        check(type(terminal) is TerminalTool and type(editor) is FileEditorTool and terminal.action_type is TerminalAction and editor.action_type is FileEditorAction,"ORIGINAL_OFFICIAL_SCHEMAS_AND_TYPES")
        check(terminal.executor.science_gate is gate and editor.executor.science_gate is gate,"BOTH_OFFICIAL_EXECUTORS_WRAPPED")
        results.append({"case":"native_registry_official_types_schemas_permission_wrappers","passed":True})
        observation=terminal.executor(TerminalAction(command="Rscript unreviewed.R"));check(observation.is_error is True and counter.calls==0,"PENDING_SCOPE_NO_NATIVE_EXECUTOR_CALL")
        results.append({"case":"actual_terminal_schema_unreviewed_command_blocked","passed":True,"delegate_calls":counter.calls})
        conversation=SimpleNamespace(agent=SimpleNamespace(llm=NoModelVision()));file=work/"analysis.R";editor.executor(FileEditorAction(command="create",path=str(file),file_text="synthetic code only\n"),conversation);check(file.read_text()=="synthetic code only\n","OFFICIAL_FILE_EDITOR_ACTUAL_CREATE")
        results.append({"case":"official_file_editor_create_in_own_workspace","passed":True})
        outside=root/"not_actor_readable";outside.write_text("synthetic boundary only")
        try:editor.executor(FileEditorAction(command="view",path=str(outside)),conversation)
        except ScientificGateIntegrityError:pass
        else:raise AssertionError("FILE_VIEW_OUTSIDE_ROLE_SCOPE")
        results.append({"case":"official_file_editor_private_view_denied_before_delegate","passed":True})
    check(len(results)==4 and counter.calls==0,"FOUR_CASES_ZERO_COMMAND_EXECUTION")
    print(json.dumps({"schema":"bioduet-scoped-science-tools-ABI-observation/1","cases":results,"actual_scientific_fit":False,"Agent_or_model_created":False,"native_terminal_delegate_calls":counter.calls,"all_process_and_R_observations":"Root independent trace required, not inferred from fixture counter","actual_Root_scientific_exec_grants":0,"source_kind":"synthetic_tool_permission_ABI_only","retirement":"Root_independent_not_asserted_by_fixture"},sort_keys=True))
if __name__=="__main__":main()
