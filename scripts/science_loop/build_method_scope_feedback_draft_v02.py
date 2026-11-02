"""Source-backed public method-scope feedback draft; never grants execution.
Preserve the exact original S source privately. Only a bounded redacted reason
and criterion references go to the model as author/platform assistance, not H.
"""
import argparse,json,sys,time,math,re,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bioduet_vnext.science_execution_gate_v05 import stable,digest,encode,check,PACKET
def pin_read(ref):
    raw=stable(ref["path"],1024*1024,True);check(len(raw)==ref["bytes"] and digest(raw)==ref["sha256"],"ACTUAL_PROTECTED_SOURCE_SHA");return raw

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--proof",required=True);ap.add_argument("--proof-sha256",required=True);a=ap.parse_args();raw=stable(a.proof,1024*1024,True);check(digest(raw)==a.proof_sha256,"CURRENT_FEEDBACK_PROOF_SHA");p=json.loads(raw)
    check(p["schema"]=="bioduet-root-method-scope-feedback-publisher/1" and p["actor_scope"]["role"]=="A","CURRENT_CODEGEN_FEEDBACK_SCOPE")
    check(math.isfinite(p["unit_deadline_monotonic"]) and time.monotonic()<p["unit_deadline_monotonic"],"FINITE_CURRENT_SCOPE")
    sr=json.loads(pin_read(p["actual_S_scope_check_ref"]));check(sr["schema"]=="bioduet-method-scope-author-check/1" and sr["record_kind"]=="actual" and sr["performed"] is True and sr["verdict"] in ("out_of_scope","insufficient") and sr["approved_method_packet_sha256"]==PACKET,"ACTUAL_NONPASSING_SCOPE_REVIEW_NOT_TEMPLATE")
    intake=json.loads(pin_read(p["actual_scope_intake_ref"]));check(p["actual_scope_intake_ref"]["sha256"]==sr["intake_sha256"] and intake["code_bundle"]["sha256"]==sr["code_bundle_sha256"],"EXACT_SUBMITTED_CODE_INTAKE")
    for k in ["episode_id","attempt_id"]:check(intake["case_binding"][k]==p["actor_scope"][k],"EXACT_CASE_FEEDBACK")
    reason=sr["reason"];check(type(reason) is str and len(reason)<=8192,"BOUNDED_AUTHOR_REASON")
    reason=re.sub(r"(?i)(?:[A-Z]:[\\/]|/(?:data1|root|home|run|var|tmp)/)\S+","[private host path redacted]",reason)
    reason=re.sub(r"\bH[01]\b","[arm hidden]",reason)
    criterion=sr["criterion_references"];check(type(criterion) is list and all(type(x) is str and x.startswith("BW01.") for x in criterion),"PUBLIC_CRITERION_IDENTIFIERS")
    feedback={"schema":"bioduet-root-scientific-code-scope-feedback/1","actor_scope":p["actor_scope"],"actual_S_scope_check_ref":p["S_scope_check_actor_readonly_ref"],"reported_verdict":sr["verdict"],"code_bundle_sha256":sr["code_bundle_sha256"],"intake_sha256":sr["intake_sha256"],"scientific_execution_authorized":False,"actor_message":"Author applicability check: "+sr["verdict"]+". "+reason+" Criteria: "+", ".join(criterion),"source_kind":"operator_author_scope_feedback_not_H_or_independent_science","root_protected_publication_required":True}
    check(p["S_scope_check_actor_readonly_ref"]["bytes"]==p["actual_S_scope_check_ref"]["bytes"] and p["S_scope_check_actor_readonly_ref"]["sha256"]==p["actual_S_scope_check_ref"]["sha256"],"EXACT_SOURCE_COPY_ALIAS")
    out=Path(p["fresh_P_feedback_draft_path"]);check(out.is_relative_to(Path(__file__).resolve().parents[2]) and not out.exists(),"FRESH_P_OWNED_DRAFT")
    b=encode(feedback)+b"\n";fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
    with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fchmod(f.fileno(),0o444);os.fsync(f.fileno())
    print(json.dumps({"schema":"bioduet-method-scope-feedback-draft-observation/1","draft_path":str(out),"bytes":len(b),"sha256":digest(b),"execution_authorized":False,"Root_must_protect_copy_and_publish_current_pointer_before_Actor_read":True,"model_called_or_R_executed":False}))
if __name__=="__main__":main()
