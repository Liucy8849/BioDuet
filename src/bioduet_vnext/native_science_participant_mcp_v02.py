"""Native OpenHands MCP configuration; construction only after fresh admission.
No replacement planner, custom executor, secret lookup or process launch here.
The Root child entry establishes post-exec guards before the fixed server payload.
"""
import hashlib,json,math,os,sys,time
from pathlib import Path
from .contracts_v01 import require,sha

def native_science_participant_config(proof,read_pin):
    part=proof["participant_stdio"]
    require(sha(proof.get("MCP_runtime_review_sha256")),"ROOT_ACCEPTED_MCP_REVIEW_REQUIRED")
    entry=part["Root_child_entry"];read_pin(entry)
    server=part["server_driver"];read_pin(server)
    raw=read_pin(part["server_proof"]);child=json.loads(raw)
    require(child.get("schema")=="bioduet-root-native-science-role-MCP-proof/1"
        and child.get("source_kind")=="real_public_data_with_declared_simulated_researcher","REAL_SCIENCE_ROLE_MCP_NOT_OLD_FIXTURE")
    require(child["nonce"]==proof["nonce"] and child["models"]==0,"FRESH_MCP_CHILD_SCOPE")
    require(child["driver"]==server and child["Root_child_entry"]==entry,"EXACT_ROOT_CHILD_ENTRY_AND_DRIVER")
    require(child["model_call_limit"] is None and child["model_turn_limit"] is None,
            "NO_NUMERICAL_MODEL_CAP_IN_CHILD")
    if "actor_scope" in proof:
        require(child["actor_scope"]==proof["actor_scope"],"SAME_ACTOR_PARTICIPANT_SCOPE")
    require(child["output"]==part["server_output"],"EXACT_MCP_SERVER_OUTPUT")
    require(child.get("world_binding_kind")=="single_existing_canonical_World_with_exact_context_mapping"
        and sha(child.get("world_binding_sha256")) and child.get("host_scope_namespace_mapping_frozen") is True,
        "ACTUAL_WORLD_BINDING_NOT_FIXTURE_COMMIT_OR_NEW_WORLD")
    timeout=part["io_timeout_seconds"]
    require(type(timeout) in (int,float) and math.isfinite(timeout) and 0<timeout<=300
        and timeout<=proof["deadline_monotonic"]-time.monotonic(),"FINITE_MCP_IO_NOT_CALL_CAP")
    python=proof["fixed_Python"];read_pin(python)
    require(Path(python["path"]).resolve()==Path(sys.executable).resolve(),"FIXED_ACCEPTED_PYTHON")
    require(os.environ.get("LITELLM_MODE")=="PRODUCTION"
        and os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP","").lower()=="true","LOCAL_COST_MAP_ONLY")
    require(not any(k in os.environ for k in ("OPENAI_API_KEY","ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY","EXA_API_KEY")),"NO_RAW_PROVIDER_KEY_IN_ACTOR")
    from pydantic import SecretStr
    from openhands.sdk.mcp.config import MCPServer
    env={"HOME":os.environ["HOME"],"PATH":proof["fixed_child_PATH"],"PYTHONDONTWRITEBYTECODE":"1",
         "LITELLM_MODE":"PRODUCTION","LITELLM_LOCAL_MODEL_COST_MAP":"True"}
    # Native SDK -> FastMCP -> stdio; no M-created subprocess or custom MCP executor.
    native=MCPServer(transport="stdio",command=python["path"],
        args=["-I","-S","-B",entry["path"],"--driver",server["path"],
              "--driver-sha256",server["sha256"],"--proof",part["server_proof"]["path"],
              "--proof-sha256",part["server_proof"]["sha256"]],
        env={k:SecretStr(v) for k,v in env.items()},cwd=part["server_output"],
        timeout=float(timeout)).as_literal()
    return {"bioduet":native}
