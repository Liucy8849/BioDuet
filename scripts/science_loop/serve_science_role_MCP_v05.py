"""Official FastMCP stdio proxy to the single finite role-bound study endpoint.
No World/Session is constructed in an Actor child. This requires its own admitted
private-loopback connection; an older no-INET MCP window is insufficient.
"""
import argparse,json,hashlib,os,time,math,secrets
from pathlib import Path
from urllib.parse import urlsplit
from http.client import HTTPConnection
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bioduet_vnext.contracts_v01 import require

def pinned(row):
    p=Path(row["path"]);require(p.is_absolute() and not p.is_symlink(),"PINNED_PROXY_INPUT")
    raw=p.read_bytes()
    require(len(raw)==row["bytes"] and hashlib.sha256(raw).hexdigest()==row["sha256"],"PROXY_INPUT_SHA")
    return raw

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--mode",choices=["server"],default="server");ap.add_argument("--proof",required=True);ap.add_argument("--proof-sha256",required=True)
    args=ap.parse_args();raw=Path(args.proof).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==args.proof_sha256,"ROOT_ROLE_PROXY_PROOF")
    proof=json.loads(raw)
    require(proof["schema"]=="bioduet-root-native-science-role-MCP-proof/1"
        and proof["source_kind"]=="real_public_data_with_declared_simulated_researcher"
        and proof["world_binding_kind"]=="single_existing_canonical_World_with_exact_context_mapping",
        "ACTUAL_SHARED_WORLD_BINDING_REQUIRED")
    require(os.getuid()==1008 and os.getgroups()==[] and
        type(proof["deadline_monotonic"]) in (int,float) and math.isfinite(proof["deadline_monotonic"])
        and time.monotonic()<proof["deadline_monotonic"],"FRESH_FINITE_PROXY_SCOPE")
    endpoint=urlsplit(proof["world_endpoint"])
    require(endpoint.scheme=="http" and endpoint.hostname=="127.0.0.1" and
            type(endpoint.port) is int and endpoint.username is None and endpoint.password is None
            and endpoint.path in ("","/") and not endpoint.query and not endpoint.fragment,
            "EXACT_ADMITTED_PRIVATE_LOOPBACK_ONLY")
    capability=pinned(proof["world_role_capability"]).decode("ascii").strip()
    require(16<=len(capability)<=512,"BOUNDED_PRIVATE_WORLD_CAPABILITY")
    import importlib.metadata
    require(importlib.metadata.version("mcp")=="1.28.1","FIXED_NATIVE_MCP")
    from mcp.server.fastmcp import FastMCP
    from bioduet_vnext.mcp_tool_contracts_v01 import tool_description
    service=FastMCP("scoped-research-tools")
    description=("Use your role's research tools. study.schema returns the exact wire schema; study.observe explicitly queries the currently authorized view; "
        "study.next retrieves your next available turn; study.submit takes turn_handle and decision "
        "under the issued profile. After an uncertain result use study.operation with your operation_id instead of blindly repeating a mutation. Use original dataset/workspace/notice tools only when offered. "
        "Metadata registration and acknowledgement do not prove analysis execution or scientific validity.")
    journal=Path(proof["transport_journal_root"])
    require(journal.is_absolute() and journal.is_dir() and not journal.is_symlink(),"ROOT_ROLE_PRIVATE_JOURNAL")
    scope={k:proof["actor_scope"][k] for k in ("episode_id","attempt_id","project_id","principal_id")}
    role=proof["actor_scope"]["role"]
    require(role in ("A","H"),"EXACT_ROLE_PROXY_IDENTITY")
    description=description+"\n"+tool_description()+"\nThis profile uses native Terminal for analysis; job.submit is unavailable. study.next supports a finite 0..30 second IO wait, not a call or turn budget."
    @service.tool(name="bioduet_invoke",description=description)
    def invoke(tool_name:str,arguments_json:str)->str:
        require(time.monotonic()<proof["deadline_monotonic"],"ACTUAL_PROXY_LEASE_EXPIRED")
        require(type(tool_name) is str and type(arguments_json) is str
                and len(arguments_json.encode())<=1048576,"FINITE_NATIVE_REQUEST")
        payload=json.dumps({"tool_name":tool_name,"arguments_json":arguments_json},
                           ensure_ascii=False,separators=(",",":")).encode()
        timeout=min(proof["io_timeout_seconds"],proof["deadline_monotonic"]-time.monotonic())
        require(type(timeout) in (int,float) and math.isfinite(timeout) and timeout>0,"FINITE_IO_WINDOW")
        invocation=json.dumps({"tool_name":tool_name,"arguments_json":arguments_json},
            ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        request_id=secrets.token_hex(16);event_id=request_id+":dispatch-started"
        fd=os.open(journal/(request_id+".client.jsonl"),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        def record(row):
            data=(json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":"))+"\n").encode()
            offset=0
            while offset<len(data):
                n=os.write(fd,data[offset:]);require(n>0,"PROXY_JOURNAL_WRITE");offset+=n
            os.fsync(fd)
        record({"stage":"proxy_dispatch_started_before_HTTP_request","request_id":request_id,
            "event_id":event_id,"scope":scope,"role":role,"monotonic_ns":time.monotonic_ns(),
            "canonical_invocation_sha256":hashlib.sha256(invocation).hexdigest(),
            "HTTP_body_sha256":hashlib.sha256(payload).hexdigest(),"successful_send_inferred":False})
        connection=HTTPConnection("127.0.0.1",endpoint.port,timeout=timeout)
        try:
            connection.request("POST","/invoke",body=payload,headers={
                "Authorization":"Bearer "+capability,"Content-Type":"application/json",
                "X-BioDuet-Request-ID":request_id,"X-BioDuet-Dispatch-Event-ID":event_id})
            response=connection.getresponse();expected=int(response.getheader("Content-Length","-1"))
            require(0<=expected<=1048576,"BOUNDED_EXPLICIT_RESPONSE_LENGTH")
            body=response.read(expected+1)
            complete=len(body)==expected
            record({"stage":"proxy_response_bytes_read","request_id":request_id,
                "event_id":request_id+":read","monotonic_ns":time.monotonic_ns(),
                "HTTP_status":response.status,"response_bytes":len(body),
                "response_sha256":hashlib.sha256(body).hexdigest(),"complete":complete,
                "native_SDK_receipt_or_model_understanding_inferred":False})
            require(response.status==200 and complete,"WORLD_TRANSPORT_NOT_SUCCESS")
            return body.decode("utf-8")
        except Exception as exc:
            record({"stage":"proxy_error_outcome_may_be_unknown","request_id":request_id,
                "error_type":type(exc).__name__,"monotonic_ns":time.monotonic_ns(),
                "automatic_business_retry_authorized":False})
            # Never reflect request headers, capability, endpoint body or credentials.
            raise RuntimeError("WORLD_PROXY_"+type(exc).__name__) from None
        finally:connection.close();os.close(fd)
    service.run(transport="stdio")
if __name__=="__main__":main()
