"""Host-only scientific provenance adapter. No new scorer or source of judgments.
Callbacks must be supplied by the actual trusted review host, never by Actors.
Private packets, reviewer identifiers and trust bodies never enter this receipt.
"""
import hashlib,json
from copy import deepcopy
from . import span_review_v02 as span
CATALOG_SHA="45b5f3c4ae4e5e3941d68ad6fd78cf08e7a28ba807a06b9cf342bab4ccf85159"
SCHEMA_SHA="313a52fac8834bce04db2541917ac05881e1927f97305f53b1ecb4ba674c18de"
def need(ok,reason):
    if not ok:raise ValueError(reason)
def rawsha(raw):return hashlib.sha256(raw).hexdigest()
def bind_record(record,identity,artifact_map,require_complete=False):
    need(record.get("schema")=="bioduet-science-verdict/1" and record.get("record_kind")=="actual","ACTUAL_S_VERDICT_REQUIRED_NOT_TEMPLATE")
    b=record["binding"]
    need(b["episode_id"]==identity["episode_id"] and b["attempt_id"]==identity["attempt_id"] and b["task"]=="BW-01" and b["task_mode"]=="change_notice","SAME_ACTUAL_SCIENCE_BINDING")
    need(record["criterion_catalog_sha256"]==CATALOG_SHA,"FIXED_S_CRITERION_CATALOG")
    refs=[b[k] for k in ("code_ref","interpretation_ref","counts_ref","annotation_ref","public_role_input_ref","role_input_projection_receipt_ref","runtime_ref","authority_ref","observed_ref","trace_ref")]+b["result_refs"]
    if require_complete:need(bool(b["result_refs"]) and all(type(r) is dict for r in refs),"ACTUAL_REVIEW_ARTIFACTS_REQUIRED")
    refs=[r for r in refs if r is not None]
    need(all(type(r) is dict for r in refs),"PROVIDED_ARTIFACT_REFERENCE_SHAPE")
    for r in refs:
        actual=artifact_map.get(r["artifact_id"])
        need(type(actual) is dict and actual.get("project_id")==identity["project_id"] and actual.get("episode_id")==identity["episode_id"] and actual.get("attempt_id")==identity["attempt_id"],"TRUSTED_HOST_ARTIFACT_CONTEXT")
        need(actual["bytes"]==r["bytes"] and actual["sha256"]==r["sha256"],"EXACT_REVIEW_ARTIFACT_BYTES")
    return b

def verify_actual_review(*,record_bytes,schema_bytes,identity,artifact_map,packet,reviews,disclosure_artifacts,verify_disclosure,verify_assessor,verify_verdict_source,adjudication=None,verify_adjudicator=None):
    # This entry runs only in an admitted private review host with fixed191.
    # The collector does not import jsonschema or manufacture these callbacks.
    from jsonschema import Draft202012Validator
    need(rawsha(schema_bytes)==SCHEMA_SHA,"FIXED_S_SCHEMA_BYTES")
    schema=span.parse(schema_bytes);record=span.parse(record_bytes)
    Draft202012Validator(schema).validate(record)
    b=bind_record(record,identity,artifact_map,require_complete=True);ind=record["independence"]
    need(ind["source_type"] in ("independent_human_pair","independent_human_adjudication"),"ACTUAL_INDEPENDENT_HUMAN_SOURCE")
    need(packet["schema"]=="bioduet-private-review-packet/1" and packet["task"]=="BW-01" and packet["episode_id"]==identity["episode_id"],"PRIVATE_PACKET_SAME_CASE")
    need(packet.get("criterion_catalog_sha256")==CATALOG_SHA,"CURRENT_CATALOG_PACKET_NOT_LEGACY_SCORER")
    text=packet["text_utf8"].encode("utf-8");need(rawsha(text)==packet["text_sha256"]==b["interpretation_ref"]["sha256"],"INTERPRETATION_EXACT_UTF8")
    span._claims(text,packet["claims"])
    for name in ("authority","observed","trace"):
        need(packet["artifact_hashes"][name]==b[name+"_ref"]["sha256"],"PACKET_ACTUAL_EVIDENCE_JOIN")
    need(packet["artifact_hashes"]["interpretation"]==b["interpretation_ref"]["sha256"],"PACKET_TEXT_JOIN")
    need(len(packet["reviewer_ids"])==2 and len(set(packet["reviewer_ids"]))==2,"TWO_DISTINCT_ASSIGNED_HUMANS")
    need(sorted(ind["assessor_ids"])==sorted(packet["reviewer_ids"]) and ind["assignment_id"]==packet["assignment_id"] and ind["review_packet_sha256"]==span.digest(span.encoded(packet)) and ind["blind_audit_sha256"]==packet["blind_audit_sha256"],"REVIEW_ASSIGNMENT_AND_PACKET_JOIN")
    need(callable(verify_disclosure) and verify_disclosure(identity["episode_id"],deepcopy(disclosure_artifacts),tuple(packet["reviewer_ids"]),packet["blind_audit_sha256"]) is True,"ACTUAL_DISCLOSURE_AUTHORITY")
    need(callable(verify_assessor) and callable(verify_verdict_source),"TRUSTED_HOST_CALLBACKS_REQUIRED_NO_DEFAULT")
    resolved=span.resolve_reviews(packet,reviews,verify_assessor=verify_assessor)
    need(len(resolved["assessments"])==2 and not resolved["ingestion_errors"],"VERIFIED_ORIGINAL_HUMAN_PAIR")
    need(all(x["coverage_complete"] and not x["additional_claims"] for x in resolved["assessments"]),"WHOLE_TEXT_COVERAGE_OR_NEW_PACKET")
    if resolved["disputes"]:
        need(adjudication is not None and callable(verify_adjudicator) and ind["source_type"]=="independent_human_adjudication","DISPUTES_REQUIRE_ACTUAL_THIRD_HUMAN")
        resolved=span.adjudicate_reviews(packet,reviews,adjudication,verify_assessor=verify_assessor,verify_adjudicator=verify_adjudicator)
    else:need(adjudication is None and ind["source_type"]=="independent_human_pair","EXACT_REVIEW_SOURCE_KIND")
    # The eight-criterion reported verdict is not calculated from six span states.
    # A trusted host must verify its actual human-source/criterion/whole-text links.
    need(verify_verdict_source(rawsha(record_bytes),deepcopy(record),deepcopy(resolved)) is True,"ACTUAL_VERDICT_SOURCE_AND_CRITERION_LINKS")
    return {"schema":"bioduet-science-verdict-host-verification/1","identity":deepcopy(identity),"task_id":"BW-01","task_mode":"change_notice","record_sha256":rawsha(record_bytes),"binding":deepcopy(b),"criterion_catalog_sha256":CATALOG_SHA,"reported_verdict":record["verdict"],"independent_source_verified":True,"verification_scope":"actual source/disclosure/packet/span/human-pair-or-adjudication joins; not new scientific scoring or method approval","private_packet_or_assessor_identity_exported":False,"formal_score":None,"strict_score":None,"trusted_publisher_required":"Receipt shape/boolean is not authority. Consumer must pin the actual protected review-host output through its trusted producer binding."}
