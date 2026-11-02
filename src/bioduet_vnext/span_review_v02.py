"""Pinned whole-text review queue and actual accepted-scorer consumer.
Trusted host callbacks bind disclosure/assignment/assessor provenance. Candidate
spans are prompts to assessors, never automatic scientific judgments. Private.
"""
from copy import deepcopy
import hashlib,json
from .contracts_v01 import require,sha,nonempty
from .score_bridge_v02 import read_pinned

STATES={"passed","failed","insufficient"}
DIMENSIONS={"meaning","units","direction","population","uncertainty","causality"}
def encoded(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(x):return hashlib.sha256(x).hexdigest()
def parse(raw):
    def pairs(items):
        d={}
        for k,v in items:
            require(k not in d,"REVIEW_DUPLICATE_KEY");d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
def tri(values):
    return "failed" if "failed" in values else "insufficient" if not values or "insufficient" in values else "passed"
def _claims(text,claims):
    require(type(claims) is list and bool(claims),"REVIEW_CANDIDATE_SPANS")
    seen=set()
    for c in claims:
        require(set(c)=={"id","start_byte","end_byte","quote"} and nonempty(c["id"]) and c["id"] not in seen,"REVIEW_CLAIM_ID")
        seen.add(c["id"]);start,end=c["start_byte"],c["end_byte"]
        require(type(start) is int and type(end) is int and 0<=start<end<=len(text),"REVIEW_SPAN_RANGE")
        require(text[start:end].decode("utf-8")==c["quote"],"REVIEW_SPAN_BYTES")
        # Enforce character boundaries as offsets are UTF-8 bytes, not codepoints.
        text[:start].decode("utf-8");text[:end].decode("utf-8")
    return deepcopy(claims)

def prepare_packet(root,*,task,episode_id,interpretation,artifacts,registry,
                   claims,assignment_id,reviewer_ids,blind_audit_sha256,verify_disclosure):
    """Controller-pinned file references and explicit trusted disclosure callback."""
    require(nonempty(assignment_id) and nonempty(episode_id) and sha(blind_audit_sha256),"REVIEW_ASSIGNMENT")
    require(type(reviewer_ids) is list and len(reviewer_ids)==2 and len(set(reviewer_ids))==2 and all(nonempty(x) for x in reviewer_ids),"REVIEW_TWO_ASSESSORS")
    require(callable(verify_disclosure) and verify_disclosure(episode_id,deepcopy(artifacts),tuple(reviewer_ids),blind_audit_sha256) is True,"REVIEW_DISCLOSURE_AUTHORITY")
    text=read_pinned(root,interpretation["path"],interpretation["sha256"]);text.decode("utf-8")
    require(0<len(text)<=1024*1024,"REVIEW_TEXT_SIZE")
    reg=parse(read_pinned(root,registry["path"],registry["sha256"]))
    require(reg["schema"]=="bioduet-task-rule-registry/1","REVIEW_REGISTRY_SCHEMA")
    cards=[c for c in reg["cards"] if c["task"]==task];require(len(cards)==1,"REVIEW_CARD")
    evidence={};hashes={"interpretation":interpretation["sha256"]}
    require(set(artifacts)=={"authority","observed","trace"},"REVIEW_EVIDENCE_ROLES")
    for role,spec in artifacts.items():
        raw=read_pinned(root,spec["path"],spec["sha256"])
        evidence[role]=parse(raw);hashes[role]=spec["sha256"]
    require(evidence["authority"]["task"]==evidence["observed"]["task"]==task and
            evidence["observed"]["episode_id"]==evidence["trace"]["episode_id"]==episode_id,"REVIEW_EPISODE")
    return {"schema":"bioduet-private-review-packet/1","task":task,"episode_id":episode_id,
        "assignment_id":assignment_id,"reviewer_ids":sorted(reviewer_ids),"registry_sha256":registry["sha256"],
        "covered_rules":sorted(r["id"] for r in cards[0]["rules"]),
        "registry_canonical_sha256":digest(encoded(reg)),
        "evidence_canonical_sha256":{k:digest(encoded(v)) for k,v in evidence.items()},
        "text_utf8":text.decode("utf-8"),"text_sha256":interpretation["sha256"],
        "artifact_hashes":hashes,"evidence":evidence,"claims":_claims(text,claims),
        "dimensions":sorted(DIMENSIONS),"blind_audit_sha256":blind_audit_sha256,
        "blinding_boundary":"Host-screened metadata; original text/evidence are unchanged and may still disclose identity. No automatic anonymity guarantee.",
        "publication":"private_assessor_only_not_public_export","candidate_claims_not_exhaustive_proof":True,
        "expert_approval_claimed":False}

def _validated_review(packet,review,verify_assessor,allowed_reviewers=None):
    require(type(review) is dict and review.get("schema")=="bioduet-span-assessment/1","SPAN_REVIEW_SCHEMA")
    body={k:v for k,v in review.items() if k!="trust_ref"};h=digest(encoded(body))
    require(review["packet_sha256"]==digest(encoded(packet)) and review["assignment_id"]==packet["assignment_id"],"SPAN_REVIEW_JOIN")
    who=review["reviewer_id"];require(who in (packet["reviewer_ids"] if allowed_reviewers is None else allowed_reviewers),"SPAN_REVIEW_ASSIGNMENT")
    require(review["assessment_kind"]=="independent_human_assessment","SPAN_REVIEW_NOT_MODEL_ONLY")
    require(callable(verify_assessor) and verify_assessor(review["trust_ref"],h,who) is True,"SPAN_REVIEW_TRUST")
    require(type(review["coverage_complete"]) is bool and type(review["additional_claims"]) is list,"SPAN_REVIEW_COVERAGE")
    require(review["goal_state"] in STATES and nonempty(review["goal_rationale"]),"SPAN_GOAL")
    annotations=review["annotations"];require(type(annotations) is list,"SPAN_ROWS")
    expected={c["id"]:c for c in packet["claims"]};seen=set()
    for row in annotations:
        require(row["claim_id"] in expected and row["claim_id"] not in seen,"SPAN_ROW_JOIN");seen.add(row["claim_id"])
        require(set(row["dimensions"])==DIMENSIONS,"SPAN_DIMENSION_COVERAGE")
        for name,result in row["dimensions"].items():
            require(type(result) is dict and result["state"] in STATES and nonempty(result["rationale"]),"SPAN_DIMENSION_RESULT")
            require(type(result["evidence"]) is list,"SPAN_EVIDENCE")
            if result["state"]!="insufficient":require(bool(result["evidence"]),"SPAN_NO_GROUNDED_EVIDENCE")
            for e in result["evidence"]:
                require(e["role"] in packet["artifact_hashes"] and e["sha256"]==packet["artifact_hashes"][e["role"]] and nonempty(e["locator"]),"SPAN_EVIDENCE_BINDING")
    require(seen==set(expected),"SPAN_ALL_CANDIDATES")
    # Additional claims require a new packet/adjudication; never discarded.
    return {"reviewer_id":who,"body_sha256":h,"trust_ref":deepcopy(review["trust_ref"]),
        "goal_state":review["goal_state"],"coverage_complete":review["coverage_complete"],
        "additional_claims":deepcopy(review["additional_claims"]),"annotations":deepcopy(annotations),
        "goal_rationale":review["goal_rationale"]}

def resolve_reviews(packet,reviews,*,verify_assessor):
    require(packet["schema"]=="bioduet-private-review-packet/1","PACKET_SCHEMA")
    require(type(reviews) is list and len(reviews)<=2,"REVIEW_COUNT")
    validated=[];errors=[]
    for i,r in enumerate(reviews):
        try:validated.append(_validated_review(packet,r,verify_assessor))
        except (KeyError,ValueError,TypeError,UnicodeError) as e:errors.append({"index":i,"error":type(e).__name__+":"+str(e)})
    require(len({r["reviewer_id"] for r in validated})==len(validated),"DUPLICATE_REVIEWER")
    reason="independent paired whole-text assessment missing or incomplete"
    state="insufficient";goal="insufficient";disputes=[]
    if len(validated)==2 and not errors:
        left,right=validated
        for c in packet["claims"]:
            a=next(r for r in left["annotations"] if r["claim_id"]==c["id"])
            b=next(r for r in right["annotations"] if r["claim_id"]==c["id"])
            for d in sorted(DIMENSIONS):
                if a["dimensions"][d]["state"]!=b["dimensions"][d]["state"]:disputes.append({"claim_id":c["id"],"dimension":d})
        if left["goal_state"]!=right["goal_state"]:disputes.append({"dimension":"goal"})
        if any(r["additional_claims"] for r in validated):disputes.append({"dimension":"additional_claims_require_new_packet"})
        if not all(r["coverage_complete"] for r in validated):disputes.append({"dimension":"whole_text_coverage"})
        if not disputes:
            state=tri([v["state"] for r in left["annotations"] for v in r["dimensions"].values()])
            goal=left["goal_state"];reason="Two trusted human assessors agree on candidate dimensions and goal; both attest whole-text coverage. See retained per-span rationales; this is not biological or method approval."
        else:reason="adjudication/new packet required; disagreements and additional claims retained"
    review={"schema":"bioduet-whole-text-review/1","task":packet["task"],"text_sha256":packet["text_sha256"],
        "artifact_hashes":deepcopy(packet["artifact_hashes"]),"covered_rules":packet["covered_rules"],
        "reviewer_role":"independent_assessor","rationale":reason,"state":state,"goal_state":goal,
        "expert_approval_claimed":False,"packet_sha256":digest(encoded(packet)),
        "assessments":validated,"disputes":disputes,"ingestion_errors":errors,"formal_score":None,"strict_score":None}
    return review


def adjudicate_reviews(packet,reviews,adjudication,*,verify_assessor,verify_adjudicator):
    """Third separately assigned human resolves state disputes; originals retained.
    Missing original provenance/coverage or a new unlisted claim requires new
    packet/reviews instead; adjudication cannot repair absent source evidence.
    """
    previous=resolve_reviews(packet,reviews,verify_assessor=verify_assessor)
    require(len(previous["assessments"])==2 and not previous["ingestion_errors"] and
            previous["disputes"],"ADJUDICATION_ORIGINAL_PAIR")
    require(all(d["dimension"] not in ("additional_claims_require_new_packet","whole_text_coverage")
                for d in previous["disputes"]),"ADJUDICATION_NEEDS_NEW_PACKET")
    who=adjudication["reviewer_id"]
    require(nonempty(who) and who not in packet["reviewer_ids"] and callable(verify_adjudicator),"ADJUDICATOR_INDEPENDENT_ASSIGNMENT")
    def verified(ref,body_sha,reviewer):
        return verify_adjudicator(ref,body_sha,reviewer,digest(encoded(packet)),packet["assignment_id"]) is True
    third=_validated_review(packet,adjudication,verified,allowed_reviewers={who})
    require(third["coverage_complete"] and not third["additional_claims"],"ADJUDICATOR_NEW_CLAIMS_OR_COVERAGE")
    left,right=previous["assessments"]
    for c in packet["claims"]:
        a=next(x for x in left["annotations"] if x["claim_id"]==c["id"])
        b=next(x for x in right["annotations"] if x["claim_id"]==c["id"])
        z=next(x for x in third["annotations"] if x["claim_id"]==c["id"])
        for dim in DIMENSIONS:
            if a["dimensions"][dim]["state"]==b["dimensions"][dim]["state"]:
                require(z["dimensions"][dim]["state"]==a["dimensions"][dim]["state"],"ADJUDICATOR_ALTERS_UNDISPUTED_STATE")
    if left["goal_state"]==right["goal_state"]:
        require(third["goal_state"]==left["goal_state"],"ADJUDICATOR_ALTERS_UNDISPUTED_GOAL")
    result=deepcopy(previous)
    result["pre_adjudication"]=deepcopy(previous)
    result["adjudication"]=third
    result["state"]=tri([v["state"] for x in third["annotations"] for v in x["dimensions"].values()])
    result["goal_state"]=third["goal_state"]
    result["rationale"]="Trusted third human resolved listed state disputes; both original assessments, disputes and per-span evidence remain attached. No expert method approval."
    result["disputes_resolved_by"]=third["body_sha256"]
    return result

def assess_pinned_review_packet(packet,reviews,*,registry,verify_assessor,adjudication=None,verify_adjudicator=None):
    """Actual accepted scorer consumes resolved whole-text review, not a stub."""
    from bioduet_eval.bioduet_task_assessment_v01 import assess_objects
    require(digest(encoded(registry))==packet["registry_canonical_sha256"],"REVIEW_REGISTRY_CONTENT")
    review=(resolve_reviews(packet,reviews,verify_assessor=verify_assessor) if adjudication is None else
            adjudicate_reviews(packet,reviews,adjudication,verify_assessor=verify_assessor,verify_adjudicator=verify_adjudicator))
    e=packet["evidence"];text=packet["text_utf8"].encode("utf-8")
    require(digest(text)==packet["text_sha256"],"REVIEW_TEXT_RECHECK")
    for role in ("authority","observed","trace"):
        # Raw-byte hash is checked at packet creation; canonical digest detects in-memory mutation.
        require(digest(encoded(e[role]))==packet["evidence_canonical_sha256"][role],"REVIEW_PACKET_MUTATION")
    result=assess_objects(packet["task"],deepcopy(e["authority"]),deepcopy(e["observed"]),deepcopy(e["trace"]),text,
        review,registry,packet["artifact_hashes"])
    return {"schema":"bioduet-span-review-score-consumer/1","assessment":result,"whole_text_review":review,
        "formal_score":None,"strict_score":None,"autonomous_method_approval":False,
        "boundary":"Actual fixed registered scorer only; autonomous applicability gate remains independent and no old grade is inherited."}
