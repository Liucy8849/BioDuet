"""Causal request lifecycle evidence validation. No inference from model overlap."""
from .contracts_v01 import require,nonempty
LIFECYCLE=("client_send","server_receive","validation_begin","validation_end",
           "commit_or_reject","server_reply","client_receipt")
SERVER=LIFECYCLE[1:6]

def _timestamp(e):
    require(type(e.get("time_ns")) is int and e["time_ns"]>=0, "EVENT_TIME")
    require(type(e.get("error_ns")) is int and e["error_ns"]>=0, "TIME_ERROR")
    require(all(nonempty(e.get(k)) for k in ("event_id","clock_domain","boot_id",
                                           "request_id","episode_id","attempt_id","kind")), "EVENT_IDENTITY")

def validate_request_trace(events):
    require(type(events) is list, "EVENT_LIST")
    ids={}; groups={}
    for event in events:
        require(type(event) is dict, "EVENT_OBJECT");_timestamp(event)
        require(event["event_id"] not in ids, "DUPLICATE_EVENT")
        require(event["kind"] in LIFECYCLE, "LIFECYCLE_KIND")
        require(type(event.get("causes")) is list and
                all(nonempty(x) for x in event["causes"]), "CAUSES")
        require(type(event.get("resources")) is list and
                all(nonempty(x) for x in event["resources"]), "RESOURCES")
        ids[event["event_id"]]=event
        group=groups.setdefault((event["episode_id"],event["attempt_id"],event["request_id"]),{})
        require(event["kind"] not in group, "DUPLICATE_PHASE")
        group[event["kind"]]=event
    for e in events:
        for parent_id in e["causes"]:
            require(parent_id in ids,"MISSING_CAUSAL_PARENT")
            p=ids[parent_id]
            require((p["episode_id"],p["attempt_id"])==(e["episode_id"],e["attempt_id"]),
                    "CROSS_EPISODE_CAUSE")
    visiting=set();visited=set()
    def visit(key):
        require(key not in visiting,"CAUSAL_CYCLE")
        if key in visited:return
        visiting.add(key)
        for parent in ids[key]["causes"]:visit(parent)
        visiting.remove(key);visited.add(key)
    for key in ids:visit(key)
    def ancestor(earlier,later):
        stack=list(later["causes"]);seen=set()
        while stack:
            key=stack.pop()
            if key==earlier["event_id"]:return True
            if key not in seen:seen.add(key);stack.extend(ids[key]["causes"])
        return False
    rows=[]
    for key,phases in groups.items():
        missing=[x for x in LIFECYCLE if x not in phases]
        issues=[]
        for left,right in zip(LIFECYCLE,LIFECYCLE[1:]):
            if left not in phases or right not in phases:continue
            a,b=phases[left],phases[right]
            if not ancestor(a,b):issues.append("causal_gap:"+left+":"+right)
            if (a["clock_domain"],a["boot_id"])==(b["clock_domain"],b["boot_id"]):
                if a["time_ns"]-a["error_ns"]>b["time_ns"]+b["error_ns"]:
                    issues.append("time_reversal:"+left+":"+right)
        server=[phases[x] for x in SERVER if x in phases]
        domains={(e["clock_domain"],e["boot_id"]) for e in server}
        if len(domains)>1:issues.append("server_clock_domain_changed")
        rows.append({"episode_id":key[0],"attempt_id":key[1],"request_id":key[2],
                     "state":"failed" if issues else "insufficient" if missing else "passed",
                     "missing":missing,"issues":issues})
    return rows

def relevant_overlap(left_events,right_events):
    combined=left_events+right_events
    rows=validate_request_trace(combined)
    if len(rows)!=2 or any(row["state"]!="passed" for row in rows):
        return {"state":"unknown","reason":"incomplete_or_invalid_lifecycle"}
    left={e["kind"]:e for e in left_events};right={e["kind"]:e for e in right_events}
    a0,a1=left["server_receive"],left["commit_or_reject"]
    b0,b1=right["server_receive"],right["commit_or_reject"]
    if (a0["episode_id"],a0["attempt_id"])!=(b0["episode_id"],b0["attempt_id"]):
        return {"state":"unknown","reason":"different_episode"}
    shared=set(a0["resources"])&set(b0["resources"])
    if not shared:return {"state":"not_relevant","reason":"disjoint_resources"}
    if len({(e["clock_domain"],e["boot_id"]) for e in (a0,a1,b0,b1)})!=1:
        return {"state":"unknown","reason":"incomparable_clocks"}
    lower=min(a1["time_ns"]-a1["error_ns"],b1["time_ns"]-b1["error_ns"])-max(
              a0["time_ns"]+a0["error_ns"],b0["time_ns"]+b0["error_ns"])
    upper=min(a1["time_ns"]+a1["error_ns"],b1["time_ns"]+b1["error_ns"])-max(
              a0["time_ns"]-a0["error_ns"],b0["time_ns"]-b0["error_ns"])
    return {"state":"verified" if lower>0 else "not_overlapping" if upper<=0 else "unknown",
            "overlap_kind":"server_request_processing","lower_ns":lower,"upper_ns":upper,
            "shared_resources":sorted(shared),
            "boundary":"Clock/causal consistency only; collector authenticity requires external trust binding."}
