"""Actual first-science result candidate; never converts engineering into science.
Only actual pinned current-attempt inputs are read. No legacy BW02-24 tag/scorer
or synthetic 144-cell output is reused for BW01. No public release is performed.
"""
import argparse,json,hashlib,os,math
from pathlib import Path

def pinned(row,limit=32*1024*1024):
    p=Path(row["path"]);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        import stat
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0<=before.st_size<=limit:raise ValueError("BOUNDED_REGULAR_INPUT")
        raw=bytearray()
        while True:
            block=os.read(fd,65536)
            if not block:break
            raw.extend(block)
            if len(raw)>limit:raise ValueError("INPUT_LIMIT")
        after=os.fstat(fd);current=os.lstat(p)
        if any(getattr(before,k)!=getattr(after,k) or getattr(after,k)!=getattr(current,k)
               for k in ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")):
            raise ValueError("INPUT_CHANGED")
        if len(raw)!=row["bytes"] or hashlib.sha256(raw).hexdigest()!=row["sha256"]:raise ValueError("INPUT_SHA")
        return bytes(raw)
    finally:os.close(fd)
def load(row):return json.loads(pinned(row))
def build_candidate(binding):
    identity={k:binding[k] for k in ("episode_id","attempt_id","project_id")}
    if binding["task_id"]!="BW-01" or binding["track"]!="common_environment" or binding["information_mode"]!="change_notice":
        raise ValueError("EXACT_CURRENT_FIRST_SCIENCE_CASE")
    if binding["delivery_scope"]!="internal_preview":raise ValueError("UNREVIEWED_CANDIDATE_NOT_PUBLIC_RELEASE")
    host=load(binding["host_state_ref"])
    if host["identity"]!=identity:raise ValueError("SAME_ACTUAL_ATTEMPT_HOST")
    artifacts=[];code=[]
    for item in binding["artifacts"]:
        if item["role"] not in ("A","H") or item["kind"] not in ("code","result","native_events","kernel_trace","tool_trace","transcript"):
            raise ValueError("ACTUAL_ARTIFACT_ROLE_KIND")
        raw=pinned(item["ref"]);row={"artifact_id":item["kind"]+":"+item["ref"]["sha256"],
            "role":item["role"],"kind":item["kind"],"source_ref":dict(item["ref"]),
            "bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
            "authorship":"unverified_until_actual_native_event_and_kernel_join"}
        artifacts.append(row)
        if item["kind"]=="code":
            # Full source is allowed only inside the authorized internal preview.
            code.append({**row,"text":raw.decode("utf-8"),"verbatim":True})
    if binding["author_runtime_outcome"]=="completed":
        if not any(a["role"]=="A" and a["kind"]=="code" for a in artifacts) or not any(a["role"]=="A" and a["kind"]=="result" for a in artifacts):
            raise ValueError("COMPLETED_RUNTIME_REQUIRES_ACTUAL_CODE_AND_RESULT_BYTES")
    engineering_ref=binding.get("independent_engineering_review_ref")
    engineering=None if engineering_ref is None else load(engineering_ref)
    scientific_ref=binding.get("independent_scientific_review_ref")
    scientific=None if scientific_ref is None else load(scientific_ref)
    if engineering is not None and (engineering.get("identity")!=identity or engineering.get("task_id")!="BW-01"):
        raise ValueError("ENGINEERING_REVIEW_SAME_ACTUAL_ATTEMPT")
    pending_template_ref=None
    if scientific is not None and scientific.get("schema")=="bioduet-science-verdict/1" and scientific.get("record_kind")=="template":
        pending_template_ref=scientific_ref;scientific=None;scientific_ref=None
    scientific_verification_ref=binding.get("trusted_scientific_host_verification_ref")
    scientific_verification=None
    if scientific is not None:
        from bioduet_vnext.science_review_host_v02 import bind_record
        artifact_map=binding.get("trusted_actual_artifact_map")
        if type(artifact_map) is not dict:raise ValueError("TRUSTED_CURRENT_ARTIFACT_MAP_REQUIRED")
        bind_record(scientific,identity,artifact_map)
        if scientific_verification_ref is not None:
            # This binding is frozen by the protected collector, not an Actor.
            # No trust is derived from scientific.independence boolean claims.
            receipt=load(scientific_verification_ref)
            if receipt.get("schema")!="bioduet-science-verdict-host-verification/1" or receipt.get("identity")!=identity or receipt.get("record_sha256")!=scientific_ref["sha256"] or receipt.get("binding")!=scientific["binding"] or receipt.get("criterion_catalog_sha256")!=scientific["criterion_catalog_sha256"] or receipt.get("reported_verdict")!=scientific["verdict"]:
                raise ValueError("EXACT_PROTECTED_SCIENTIFIC_RECEIPT_JOIN")
            scientific_verification=receipt
    elif scientific_verification_ref is not None:raise ValueError("NO_RECEIPT_WITHOUT_ACTUAL_REVIEW")
    # Preserve judgments as their own source-backed records. This producer does not
    # silently assign grade, method equivalence, biological truth or strict score.
    tasks=[]
    for n in range(1,25):
        task_id="BW-"+str(n).zfill(2)
        tasks.append({"task_id":task_id,"evidence_state":"current_attempt" if task_id=="BW-01" else "unrun",
            "formal_score":None,"strict_score":None,"independent_scientific_acceptance":None})
    costs={"model_records":None,"source_ref":None,"normalization_state":"unavailable",
           "provider_bill_amount":None,"provider_bill_source_ref":None,
           "estimated_cost_is_not_bill":True}
    if binding.get("usage_source_ref") is not None:
        usage=load(binding["usage_source_ref"])
        if usage["identity"]!=identity or type(usage["records"]) is not list:raise ValueError("CURRENT_ATTEMPT_USAGE_ONLY")
        ids=set()
        for row in usage["records"]:
            if type(row.get("dispatch_id")) is not str or row["dispatch_id"] in ids:raise ValueError("UNIQUE_ACTUAL_DISPATCH_ID")
            ids.add(row["dispatch_id"])
            if row["role"] not in ("A","H") or row["status"] not in ("rejected","confirmed","unknown"):
                raise ValueError("ACTUAL_USAGE_ROLE_STATUS")
            for field in ("input_tokens","output_tokens","reasoning_tokens"):
                value=row.get(field)
                if value is not None and (type(value) is not int or value<0):raise ValueError("ACTUAL_USAGE_SCALAR")
        costs.update(model_records=usage["records"],source_ref=binding["usage_source_ref"],
            normalization_state="source_backed_records_preserved_not_billing_or_model_understanding")
    review_state={"engineering":{"source_ref":engineering_ref,"record":engineering},
        "scientific":{"source_ref":scientific_ref,"record":scientific,"pending_template_ref":pending_template_ref,"host_verification_ref":scientific_verification_ref,"host_verification":scientific_verification,"independent_state":"pending" if scientific is None else ("source_verified" if scientific_verification is not None and scientific_verification.get("independent_source_verified") is True else "source_unverified")},
        "formal_score":None,"strict_score":None,
        "actual_Agent_authorship_execution_method_validity_are_separate":True}
    return {"schema":"bioduet-real-science-release-candidate/1",
        "release_id":"science-candidate:"+binding["host_state_ref"]["sha256"][:24],
        "release_state":"internal_candidate_not_published","task_id":"BW-01",
        **identity,"track":binding["track"],"information_mode":binding["information_mode"],
        "source_kind":"real_public_data_with_declared_simulated_researcher",
        "author_runtime_outcome":binding["author_runtime_outcome"],
        "all_started_attempt_refs":binding["all_started_attempt_refs"],
        "host_state_ref":binding["host_state_ref"],"artifacts":artifacts,"code_artifacts":code,
        "costs":costs,"reviews":review_state,"tasks":tasks,"source_generation":"actual_current_attempt",
        "dataset_tables_exported_as_separate_content":False,
        "code_embedded_data_disclosure_review":"pending_internal_preview_only",
        "legacy_synthetic144_cells_or_legacy_score_tag_reused":False,
        "scientific_episodes_accepted_by_this_producer":0,
        "ack_or_return_or_code_snapshot_proves_science":False}
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--binding",required=True);ap.add_argument("--binding-sha256",required=True)
    ap.add_argument("--output",required=True);args=ap.parse_args()
    p=Path(args.binding);raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.binding_sha256:raise ValueError("ACTUAL_INPUT_BINDING_SHA")
    result=build_candidate(json.loads(raw))
    out=(json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False,indent=2)+"\n").encode()
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:f.write(out);f.flush();os.fsync(f.fileno())
    print(json.dumps({"output_bytes":len(out),"output_sha256":hashlib.sha256(out).hexdigest(),
        "release_state":result["release_state"],"formal_score":None,"strict_score":None}))
if __name__=="__main__":main()
