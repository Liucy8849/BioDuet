"""Versioned consumer of the accepted multicard scorer and pinned evidence facets."""
import hashlib,json,os,stat
from pathlib import Path
from .protocol_export_v02 import derive_protocol_counts
from .trace_v01 import validate_request_trace
from .contracts_v01 import require,sha

def read_pinned(root,relative,expected,max_bytes=4194304):
    require(sha(expected),"EVIDENCE_SHA")
    require(type(relative) is str and relative and not relative.startswith("/") and
            all(x not in ("",".","..") for x in relative.split("/")) and "\\" not in relative,"EVIDENCE_PATH")
    base=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in relative.split("/")[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=base)
            os.close(base);base=child
        fd=os.open(relative.split("/")[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=base)
        with os.fdopen(fd,"rb") as stream:
            st=os.fstat(stream.fileno());require(stat.S_ISREG(st.st_mode) and st.st_size<=max_bytes,"EVIDENCE_SIZE")
            raw=stream.read(max_bytes+1)
    finally:os.close(base)
    require(len(raw)<=max_bytes and hashlib.sha256(raw).hexdigest()==expected,"EVIDENCE_PIN")
    return raw

def score_with_facets(root,plan_path,plan_sha256,facets,*,score_plan):
    """score_plan is a trusted host callback bound to the accepted scorer, not role-supplied."""
    require(callable(score_plan),"TRUSTED_SCORER")
    result=score_plan(root,plan_path,plan_sha256)
    require(result.get("schema")=="bioduet-multicard-scoreboard/1" and
            result.get("plan_sha256")==plan_sha256,"SCORE_JOIN")
    require(type(facets) is list,"FACET_LIST")
    keys={(row["task"],row["episode_id"]) for row in result["rows"]}
    seen=set();details=[]
    for facet in facets:
        key=(facet["task"],facet["episode_id"])
        require(key in keys and key not in seen,"FACET_EPISODE_JOIN");seen.add(key)
        detail={"task":key[0],"episode_id":key[1],"protocol":None,"request_lifecycle":None,
                "ingestion_error":None}
        try:
            if facet.get("report") is not None:
                spec=facet["report"];raw=read_pinned(root,spec["path"],spec["sha256"])
                detail["protocol"]=derive_protocol_counts(raw,source_sha256=spec["sha256"],
                    source_schema=spec["source_schema"],mappings=spec["mappings"])
            if facet.get("trace") is not None:
                spec=facet["trace"];raw=read_pinned(root,spec["path"],spec["sha256"])
                events=json.loads(raw)
                require(type(events) is list and all((e.get("episode_id"),e.get("attempt_id"))==
                    (key[1],facet["attempt_id"]) for e in events),"TRACE_EPISODE_JOIN")
                detail["request_lifecycle"]=validate_request_trace(events)
        except (ValueError,TypeError,KeyError,OSError) as exc:
            detail["ingestion_error"]=type(exc).__name__+":"+str(exc)
        details.append(detail)
    return {"schema":"bioduet-score-evidence-bridge/1","base_scoreboard":result,"facets":details,
            "missing_facets":[{"task":k[0],"episode_id":k[1]} for k in sorted(keys-seen)],
            "formal_score":None,"strict_score":None,
            "boundary":"Facets do not promote scientific/authorization/strict axes. Trace authenticity and scientific review remain external."}

def accepted_score_plan(*args):
    # Actual host consumer; standalone release must package this accepted module before publication.
    from bioduet_eval.bioduet_task_scoreboard_v01 import score_plan
    return score_plan(*args)
