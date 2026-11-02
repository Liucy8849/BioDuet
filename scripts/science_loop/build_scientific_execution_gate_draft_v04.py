"""Build immutable-byte gate draft after actual S scope check + Root exec grant.
No R/code execution. Root publishes only after protecting copied bytes, current
scope/readonly namespace verification and exact Actor mapping. Draft is not grant.
"""
import argparse,json,os,hashlib,math,time,shlex,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bioduet_vnext.science_execution_gate_v05 import stable,encode,digest,check,PACKET
POLICY="31afdb8cd75413b984fdcd9a3819330e55b90db3e50b5d8dc14af10cae894a4b"
CARD="808049e0bc00be3d15ec68e60c1f5f3af0ead063ad0c670945bc67142f5689b3"
def pinned(ref,control=False):
    raw=stable(ref["path"],64*1024*1024,control);check(len(raw)==ref["bytes"] and digest(raw)==ref["sha256"],"PINNED_ACTUAL_BYTES");return raw
def write_new(p,raw,mode=0o444):
    p.parent.mkdir(parents=True,exist_ok=True);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fchmod(f.fileno(),mode);os.fsync(f.fileno())
def build(proof):
    check(proof["schema"]=="bioduet-root-science-execution-gate-publisher/1" and proof["actor_scope"]["role"]=="A","ACTUAL_PUBLISHER_SCOPE")
    deadline=proof["deadline_monotonic"];check(type(deadline) in (int,float) and math.isfinite(deadline) and time.monotonic()<deadline,"ACTUAL_FINITE_SCOPE")
    check(proof["actual_controller_phase"]=="after_current_scientific_exec_grant_before_actor_command","NO_FUTURE_GRANT_REFERENCE")
    actual=proof["actual_scientific_exec_admission_ref"];admission=json.loads(pinned(actual,True));check(admission["actor_scope"]==proof["actor_scope"] and admission["deadline_monotonic"]==deadline and admission["scope_id"]==proof["actual_exec_scope_id"],"ACTUAL_EXEC_ADMISSION_BINDING")
    sr=json.loads(pinned(proof["S_actual_scope_check_ref"],True));intake_raw=pinned(proof["actual_scope_intake_ref"],True);intake=json.loads(intake_raw)
    check(sr["schema"]=="bioduet-method-scope-author-check/1" and sr["record_kind"]=="actual" and sr["performed"] is True and sr["verdict"]=="within_scope_for_calibration","ACTUAL_S_SCOPE_NOT_TEMPLATE")
    check(sr["approved_method_packet_sha256"]==PACKET and sr["input_policy_sha256"]==POLICY and sr["method_scope_card_sha256"]==CARD and sr["intake_sha256"]==digest(intake_raw),"EXACT_EXISTING_SCOPE_AND_INTAKE")
    check(intake["schema"]=="bioduet-method-scope-intake/1" and intake["record_kind"]=="actual" and intake["actual_submission"] is True,"ACTUAL_CODEGEN_SUBMISSION")
    for k in ["episode_id","attempt_id"]:check(intake["case_binding"][k]==proof["actor_scope"][k],"CURRENT_CASE_INTAKE")
    for key,ref in [("dependency_manifest_sha256",intake["code_bundle"]["transitive_dependency_manifest_ref"]),("settings_sha256",intake["declared_settings_ref"]),("invocation_sha256",intake["actual_invocation_ref"])]:
        pinned(ref,True);check(sr[key]==ref["sha256"],"EXACT_DEPENDENCY_OPTIONS_INVOCATION_SHA")
    check(sr["code_bundle_sha256"]==intake["code_bundle"]["sha256"],"S_CODE_BUNDLE_SHA")
    root=Path(proof["fresh_P_stage_root"]).resolve();P=Path(__file__).resolve().parents[2];check(root.is_relative_to(P) and not root.exists(),"FRESH_P_ONLY_STAGE");root.mkdir(mode=0o700)
    refs=[];source_rows=[];total=0;actor_aliases=set()
    for section in ["code_files","actual_input_files"]:
        for index,row in enumerate(proof[section]):
            raw=pinned(row["source_ref"]);total+=len(raw);check(len(refs)<256 and total<=128*1024*1024,"BOUNDED_STAGE_BYTES")
            rel=Path(row["relative_path"]);check(not rel.is_absolute() and ".." not in rel.parts,"SAFE_RELATIVE_FILE")
            physical=root/section/rel;write_new(physical,raw)
            actor=Path(row["actor_readonly_path"]);check(actor.is_absolute() and str(actor) not in actor_aliases,"EXACT_UNIQUE_READONLY_ACTOR_ALIAS");actor_aliases.add(str(actor))
            refs.append({"path":str(actor),"bytes":len(raw),"sha256":digest(raw)})
            source_rows.append({"physical_stage":str(physical),"actor_ref":refs[-1],"section":section,"relative_path":str(rel)})
    tree=sorted([{"relative_path":r["relative_path"],"bytes":r["actor_ref"]["bytes"],"sha256":r["actor_ref"]["sha256"]} for r in source_rows if r["section"]=="code_files"],key=lambda x:x["relative_path"])
    check(digest(encode(tree))==sr["code_bundle_sha256"],"ACTUAL_FROZEN_COMPLETE_CODE_TREE")
    invocation=json.loads(pinned(intake["actual_invocation_ref"],True));argv=invocation["argv"];script=next(r["actor_ref"] for r in source_rows if r["section"]=="code_files" and r["actor_ref"]["path"]==argv[2]);check(argv[:3]==[proof["fixed_Rscript_path"],"--vanilla",script["path"]],"ACTUAL_REVIEWED_FIXED_R_INVOCATION")
    receipt={"schema":"bioduet-root-scientific-execution-admission/1","actor_scope":proof["actor_scope"],"deadline_monotonic":deadline,"method_packet_sha256":PACKET,"environment_manifest_sha256":proof["qualified_environment_manifest_sha256"],"root_actual_exec_grant_sha256":actual["sha256"],"actual_exec_scope_id":proof["actual_exec_scope_id"],"data_binding_sha256":proof["actual_data_binding_sha256"],"metadata_binding_sha256":proof["actual_metadata_binding_sha256"],"code_bundle_manifest_sha256":sr["code_bundle_sha256"],"S_author_scope_check_ref":proof["S_scope_check_actor_readonly_ref"],"immutable_execution_files":refs,"script_ref":script,"argv":argv,"command":shlex.join(argv),"execution_id":proof["actual_execution_id"],**{k:sr[k] for k in ["code_bundle_sha256","dependency_manifest_sha256","settings_sha256","intake_sha256","invocation_sha256"]}}
    check(proof["S_scope_check_actor_readonly_ref"]["sha256"]==proof["S_actual_scope_check_ref"]["sha256"] and proof["S_scope_check_actor_readonly_ref"]["bytes"]==proof["S_actual_scope_check_ref"]["bytes"],"EXACT_S_PROTECTED_COPY_ALIAS")
    write_new(root/"receipt.draft.json",encode(receipt)+b"\n")
    result={"schema":"bioduet-scientific-exec-gate-publication-draft/1","state":"draft_requires_Root_protected_owner_readonly_mount_and_current_publication","receipt_draft_ref":{"path":str(root/"receipt.draft.json"),"bytes":(root/"receipt.draft.json").stat().st_size,"sha256":digest((root/"receipt.draft.json").read_bytes())},"copy_map":source_rows,"source_code_changed":False,"R_or_science_executed":False,"Root_before_publication":["independently verify actual live grant/scope/deadline and S input policy, do not infer from this JSON","copy/protect immutable files with foreign Root owner0444 and actual readonly Actor namespace mounts; exact hash/paths before publication","bind exact S scope-check protected copy0444 and verify current R environment manifest","only then create Root current pointer to exact protected receipt; no Actor write access","all current scope/namespace/cgroup/birth/input/outputs and retirement independently retained"]}
    write_new(root/"publication-draft.json",encode(result)+b"\n");return result
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--proof",required=True);ap.add_argument("--proof-sha256",required=True);a=ap.parse_args();raw=stable(a.proof,1024*1024,True);check(digest(raw)==a.proof_sha256,"ACTUAL_PUBLISHER_PROOF_SHA");result=build(json.loads(raw));print(json.dumps(result,sort_keys=True))
