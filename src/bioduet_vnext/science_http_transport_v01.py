"""Actual private-loopback ingress correlation for the existing C observer.
The proxy's pre-send dispatch record is not a successful send, server response is
not a client read, and no read is model understanding. Raw args stay unchanged.
"""
import os,json,stat,hashlib,re,time,secrets,contextvars
from pathlib import Path
from copy import deepcopy
from .contracts_v01 import require
from .participant_observer_v04 import request_sha256
_current=contextvars.ContextVar("bioduet_science_actual_http_ingress",default=None)
def canon(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def scope_fields(scope):return {k:getattr(scope,k) for k in ("episode_id","attempt_id","project_id","principal_id")}
class CurrentHTTPTransport:
    def __init__(self,root,*,role_proxy_journal_roots):
        self.root=Path(root);require(self.root.is_absolute() and not self.root.exists(),"FRESH_TRANSPORT_CONTEXT_ROOT")
        require(set(role_proxy_journal_roots)=={"A","H"},"EXACT_ROLE_PROXY_JOURNALS")
        self.roots={r:Path(p) for r,p in role_proxy_journal_roots.items()}
        require(all(p.is_absolute() and not p.is_symlink() for p in self.roots.values()),"PROTECTED_ROLE_JOURNAL_PATHS")
        self.root.mkdir(mode=0o700)
    def begin(self,*,scope,headers,body,request,peer,received_ns):
        request_id=headers.get("X-BioDuet-Request-ID","")
        event_id=headers.get("X-BioDuet-Dispatch-Event-ID","")
        require(re.fullmatch("[a-f0-9]{32}",request_id) is not None and
                event_id==request_id+":dispatch-started","ACTUAL_PROXY_REQUEST_CORRELATION")
        rootfd=os.open(self.roots[scope.role],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        fd=None
        try:
            fd=os.open(request_id+".client.jsonl",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=rootfd)
            st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and st.st_nlink==1,"REGULAR_PROXY_DISPATCH_RECORD")
            line=bytearray()
            while len(line)<=65536:
                b=os.read(fd,1)
                if not b or b==b"\n":break
                line.extend(b)
            require(b==b"\n" and 0<len(line)<=65536,"COMPLETE_DISPATCH_RECORD_BEFORE_BUSINESS")
            client=json.loads(line)
        finally:
            if fd is not None:os.close(fd)
            os.close(rootfd)
        digest=request_sha256(request["tool_name"],request["arguments_json"])
        require(client["stage"]=="proxy_dispatch_started_before_HTTP_request"
                and client["request_id"]==request_id and client["event_id"]==event_id
                and client["scope"]==scope_fields(scope) and client["role"]==scope.role
                and client["canonical_invocation_sha256"]==digest
                and client["HTTP_body_sha256"]==hashlib.sha256(body).hexdigest(),
                "SAME_ACTUAL_PROXY_DISPATCH_AND_HOST_REQUEST")
        row={"schema":"bioduet-real-science-HTTP-ingress/1","scope":scope_fields(scope),"role":scope.role,
            "request_id":request_id,"client_send_event_id":event_id,
            "client_event_semantics":"actual_proxy_dispatch_started_not_successful_kernel_send",
            "client_dispatch_record":{"path":str(self.roots[scope.role]/(request_id+".client.jsonl")),
                "record_offset":0,"record_bytes":len(line)+1,"record_sha256":hashlib.sha256(line+b"\n").hexdigest()},
            "HTTP_received_monotonic_ns":received_ns,"HTTP_peer":list(peer),
            "HTTP_body_sha256":hashlib.sha256(body).hexdigest(),"canonical_invocation_sha256":digest,
            "HTTP_recv_not_BoundMCP_invoke_entry":True,"client_read_or_understanding_inferred":False}
        path=self.root/(secrets.token_hex(16)+".json");raw=canon(row)+b"\n"
        out=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(out,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
        row["transport_context_ref"]=str(path)
        return _current.set(row)
    def end(self,token):_current.reset(token)
    def bind(self,scope,tool_name,arguments_json,digest):
        row=_current.get()
        require(row is not None and row["scope"]==scope_fields(scope) and row["role"]==scope.role
                and digest==request_sha256(tool_name,arguments_json)==row["canonical_invocation_sha256"],
                "SAME_CURRENT_INGRESS_CONTEXT_NOT_SHARED_LAST_REQUEST")
        return {"scope":scope_fields(scope),"request_sha256":digest,
                "request_id":row["request_id"],"client_send_event_id":row["client_send_event_id"],
                "transport_context_ref":row["transport_context_ref"]}
