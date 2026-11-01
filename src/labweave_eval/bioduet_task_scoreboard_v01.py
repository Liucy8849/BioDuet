"""Score a pinned start ledger through the BW-02..24 evidence evaluator.

Every started episode stays in its source-specific denominator, including
missing bundles and failed ingestion. No cached Agent-supplied score is trusted.
"""
import argparse,json
from .bioduet_task_assessment_v01 import assess,safe_read,digest,parse,require
def score_plan(root,plan_path,expected_plan_sha256):
    raw=safe_read(root,plan_path);require(digest(raw)==expected_plan_sha256,"PLAN_PIN")
    plan=parse(raw);require(plan["schema"]=="bioduet-multicard-score-plan/1","PLAN_SCHEMA")
    require(plan["call_limit"] is None and plan["turn_limit"] is None,"NO_CALL_OR_TURN_CAP")
    episodes=plan["started_episodes"];require(isinstance(episodes,list),"START_LEDGER")
    seen=set();rows=[];groups={}
    for e in episodes:
        key=(e["task"],e["episode_id"])
        require(key not in seen,"DUPLICATE_STARTED_EPISODE");seen.add(key)
        require(e["task"] in [f"BW-{n:02d}" for n in range(2,25)],"UNSUPPORTED_TASK")
        source=e["behavior_source"]
        require(source in ("simulated_replay","interactive_simulated_user","actual_human"),"SOURCE_LABEL")
        result=None;error=None
        if e.get("bundle") is not None:
            try:
                result=assess(root,e["bundle"],expected_bundle_sha256=e["bundle_sha256"],
                  trusted_path=e["trust"],expected_trusted_sha256=e["trust_sha256"],
                  registry_path=plan["registry"],expected_registry_sha256=plan["registry_sha256"])
                require((result["task"],result["episode_id"],result["behavior_source"])==(key[0],key[1],source),"EPISODE_JOIN")
            except (ValueError,KeyError,TypeError,OSError,StopIteration) as exc:
                error=type(exc).__name__+":"+str(exc);result=None
        state=result["internal_state"] if result else "insufficient"
        rows.append({"task":key[0],"episode_id":key[1],"behavior_source":source,
            "internal_state":state,"assessment":result,"ingestion_error":error,
            "reason":None if result else "started episode retained; pinned evidence unavailable or rejected",
            "formal_score":None,"strict_score":None})
        g=groups.setdefault((key[0],source),{"started":0,"passed":0,"failed":0,"insufficient":0})
        g["started"]+=1;g[state]+=1
    summaries=[]
    for (task,source),g in sorted(groups.items()):
        n=g["started"]
        summaries.append({"task":task,"behavior_source":source,**g,
            "internal_completion_lower":g["passed"]/n,
            "internal_completion_upper":(g["passed"]+g["insufficient"])/n,
            "formal_rate":None,"strict_rate":None})
    return {"schema":"bioduet-multicard-scoreboard/1","plan_sha256":expected_plan_sha256,
      "rows":rows,"groups":summaries,"all_started":len(rows),
      "formal_score":None,"strict_score":None,"model_calls":None,"monetary_cost":None,
      "boundary":"internal engineering assessment; source strata separate; no missing-episode exclusion, posterior formal promotion or biological validation claim"}
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--root",required=True)
    p.add_argument("--plan",required=True);p.add_argument("--plan-sha256",required=True);x=p.parse_args(argv)
    print(json.dumps(score_plan(x.root,x.plan,x.plan_sha256),ensure_ascii=False,allow_nan=False))
if __name__=="__main__":main()
