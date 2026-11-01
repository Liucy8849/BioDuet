"""Credential-worker broker core for an OpenAI-compatible chat route.
Run only in a separately isolated provider process. Actor tokens are scoped random
capabilities, not upstream credentials. No HTTP listener, secret lookup or network
starts on construction. Root supplies admission/transport and proves OS separation.
"""
import fcntl,hashlib,hmac,json,math,os,re,stat,threading,time,uuid
from dataclasses import dataclass
from pathlib import Path
from .contracts_v01 import Scope,require,sha,nonempty

def strict(raw):
    def pairs(items):
        out={}
        for key,value in items:
            require(key not in out,"GATEWAY_DUPLICATE_JSON");out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("GATEWAY_NONFINITE")))

@dataclass(frozen=True)
class ActorBinding:
    scope: Scope
    model: str
    token_sha256: str
    category: str
    source_kind: str
    clock_domain: str
    boot_id: str
    def __post_init__(self):
        require(type(self.scope) is Scope and self.scope.role in ("A","H"),"MODEL_ACTOR_SCOPE")
        require(nonempty(self.model) and sha(self.token_sha256),"MODEL_BINDING")
        require(self.category in ("model_primary","model_auxiliary","human_simulator","model_unclassified"),
                "MODEL_CATEGORY")
        require((self.scope.role=="H")==(self.category=="human_simulator"),"MODEL_ROLE_CATEGORY")
        require(self.source_kind in ("live","simulated_fixture") and
                nonempty(self.clock_domain) and nonempty(self.boot_id),"MODEL_SOURCE_CLOCK")

class PrivateJournal:
    def __init__(self,root):
        self.root=Path(root)
        require(self.root.is_absolute() and not self.root.exists() and not self.root.is_symlink(),
                "FRESH_PRIVATE_PROVIDER_JOURNAL")
        self.root.mkdir(mode=0o700);self.fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self._lock=threading.RLock()
    @classmethod
    def open_existing(cls,root):
        """Trusted restart only; rejects shared/permissive journals and workers."""
        value=cls.__new__(cls);value.root=Path(root)
        require(value.root.is_absolute(),"PRIVATE_PROVIDER_JOURNAL")
        fd=os.open(value.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,
                    "PRIVATE_PROVIDER_JOURNAL_OWNER_MODE")
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:os.close(fd);raise
        value.fd=fd;value._lock=threading.RLock();return value
    def save(self,name,raw):
        require(type(name) is str and name and "/" not in name and "\\" not in name and
                type(raw) is bytes and name not in (".",".."),"PROVIDER_JOURNAL_ENTRY")
        with self._lock:
            require(self.fd is not None,"PROVIDER_JOURNAL_CLOSED")
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
            with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
            os.fsync(self.fd)
        return {"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"entry":name}
    def close(self):
        with self._lock:
            if self.fd is not None:os.close(self.fd);self.fd=None

@dataclass
class ProviderStream:
    status: int
    media_type: str
    chunks: object
    close: object
    credential_values: tuple = () # Remains in credential worker, never Actor/HTTP metadata.

class ProviderNotDispatched(RuntimeError):
    """Trusted worker failure before any upstream network/request operation."""

class GatewayReply:
    def __init__(self,status,media_type,chunks):
        self.status=status;self.media_type=media_type;self.chunks=chunks

class CredentialBroker:
    def __init__(self,*,bindings,journal,authorize,transport,clock=time.monotonic,
                 max_request_bytes=4194304,max_response_bytes=16777216,
                 model_call_limit=None,model_turn_limit=None):
        require(model_call_limit is None and model_turn_limit is None,"UNBOUNDED_MODEL_CALLS_AND_TURNS")
        require(type(bindings) is list and all(type(b) is ActorBinding for b in bindings)
                and len({b.token_sha256 for b in bindings})==len(bindings),"MODEL_BINDINGS")
        require(callable(authorize) and callable(transport),"TRUSTED_PROVIDER_CALLBACKS")
        require(type(max_request_bytes) is int and max_request_bytes>0 and
                type(max_response_bytes) is int and max_response_bytes>0,"GATEWAY_IO_LIMIT")
        self.bindings=tuple(bindings);self.journal=journal;self.authorize=authorize;self.transport=transport
        self.clock=clock;self.max_request=max_request_bytes;self.max_response=max_response_bytes
        self._poisoned=False;self._lock=threading.RLock();self.records=[];self._finished=set()
    def _bind(self,capability):
        require(type(capability) is str and 32<=len(capability)<=512,"MODEL_CAPABILITY")
        hashed=hashlib.sha256(capability.encode()).hexdigest()
        for b in self.bindings:
            if hmac.compare_digest(b.token_sha256,hashed):return b
        raise ValueError("MODEL_CAPABILITY")
    @staticmethod
    def _error(status,code):
        raw=json.dumps({"error":{"type":"bioduet_gateway_error","code":code,
                                "message":"Provider request was rejected or could not complete."}}).encode()
        return GatewayReply(status,"application/json",iter([raw]))
    def _capture(self,name,raw):
        try:return self.journal.save(name,raw)
        except BaseException:
            with self._lock:self._poisoned=True
            raise
    def _record(self,row):
        raw=(json.dumps(row,sort_keys=True,allow_nan=False)+"\n").encode()
        try:self._capture(row["dispatch_id"]+"-record.json",raw)
        except BaseException:
            with self._lock:self._poisoned=True
            raise
        with self._lock:
            self.records.append(dict(row));self._finished.add(row["dispatch_id"])
    def recover_unfinished(self):
        """Trusted private-worker restart reconciliation. Never dispatches/retries.
        An intent without a final receipt stays unknown even if it never reached
        the provider. The external controller must reconcile lease/whole-run scope.
        Call before serving actors, under exclusive ownership of this journal.
        """
        with self._lock:
            require(not self._poisoned,"PROVIDER_JOURNAL_UNAVAILABLE")
            recovered=[]
            for name in sorted(os.listdir(self.journal.fd)):
                if not name.endswith("-dispatch-intent.json"):continue
                dispatch=name[:-len("-dispatch-intent.json")]
                require(re.fullmatch("[0-9a-f]{32}",dispatch) is not None,"RECOVERY_DISPATCH_ID")
                final=dispatch+"-record.json"
                try:os.stat(final,dir_fd=self.journal.fd,follow_symlinks=False)
                except FileNotFoundError:pass
                else:continue
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.journal.fd)
                with os.fdopen(fd,"rb") as f:raw=f.read(self.max_request+65537)
                require(len(raw)<=self.max_request+65536,"RECOVERY_INTENT_SIZE")
                row=strict(raw)
                require(type(row) is dict and row.get("dispatch_id")==dispatch and
                        row.get("dispatch_intent") is True,"RECOVERY_INTENT")
                row.pop("dispatch_intent")
                row.update(status="unknown",model_execution="unknown",upstream_dispatched=True,
                           input_tokens=None,output_tokens=None,provider_bill=None,
                           recovered_unfinished_intent=True,actor_protocol_receipt_observed=False,
                           completed_ns=None)
                self._record(row);recovered.append(dict(row))
            return recovered
    def request(self,capability,path,raw):
        b=self._bind(capability)
        with self._lock:require(not self._poisoned,"PROVIDER_JOURNAL_UNAVAILABLE")
        dispatch=uuid.uuid4().hex
        row={"schema":"bioduet-isolated-model-dispatch/1","dispatch_id":dispatch,
             "episode_id":b.scope.episode_id,"attempt_id":b.scope.attempt_id,
             "actor_id":b.scope.principal_id,"role":b.scope.role,"project_id":b.scope.project_id,
             "category":b.category,"source_kind":b.source_kind,"model":b.model,
             "started_ns":time.monotonic_ns(),"completed_ns":None,
             "clock_domain":b.clock_domain,"boot_id":b.boot_id,
             "upstream_dispatched":False,"model_execution":"rejected_before_generation",
             "provider_bill":None,"input_tokens":None,"output_tokens":None,
             "status":"not_sent","request":None,"response":None}
        response=None
        try:
            require(path=="/v1/chat/completions" and type(raw) is bytes and len(raw)<=self.max_request,
                    "MODEL_ROUTE_OR_SIZE")
            row["request"]=self._capture(dispatch+"-request.body",raw)
            doc=strict(raw)
            require(type(doc) is dict and doc.get("model")==b.model and
                    type(doc.get("messages")) is list and bool(doc["messages"]),"MODEL_REQUEST")
            # Preserve all native tools, memory/prompt and generation parameters as bytes.
            # No historical research_* whitelist, tool execution or planner substitution.
            require(not set(doc).intersection({"api_key","base_url","api_base","headers","extra_headers",
                                              "http_client","proxy","url"}),"MODEL_ROUTE_OVERRIDE")

            admission=self.authorize(b,hashlib.sha256(raw).hexdigest())
            require(type(admission) is dict and admission.get("allowed") is True and
                    sha(admission.get("admission_ref_sha256")),"MODEL_NOT_ADMITTED")
            deadline=admission["deadline_monotonic"]
            require(type(deadline) in (int,float) and math.isfinite(deadline) and
                    deadline>self.clock(),"MODEL_DEADLINE")
            row["admission_ref_sha256"]=admission["admission_ref_sha256"]
            # Intent persistence failure is known not-sent. A crash after intent is
            # independently recovered as unknown, never blindly retried.
            intent=dict(row,dispatch_intent=True)
            self._capture(dispatch+"-dispatch-intent.json",json.dumps(intent,sort_keys=True).encode())
            row["upstream_dispatched"]=True;row["model_execution"]="unknown";row["status"]="dispatched"
            response=self.transport(raw,deadline)
            require(type(response) is ProviderStream and type(response.status) is int and
                    100<=response.status<=599 and type(response.media_type) is str and
                    callable(response.close),"PROVIDER_STREAM")
            row["http_status"]=response.status
            rejected=(response.status!=200 or response.media_type.split(";",1)[0].strip()
                      not in ("application/json","text/event-stream"))
            if rejected:
                row["upstream_response_rejected"]=True
                # Drain into private raw capture, but never send a credential-
                # echoing provider error to the actor.
                public_status=response.status if 400<=response.status<=599 else 502
                recorded=_RecordedStream(self,response,row,deadline)
                response=None
                for _ in recorded:pass
                return self._error(public_status,"UPSTREAM_ERROR")
            require(response.status==200 and response.media_type.split(";",1)[0].strip()
                    in ("application/json","text/event-stream"),"PROVIDER_RESPONSE_TYPE")
            return GatewayReply(200,response.media_type.split(";",1)[0].strip(),_RecordedStream(self,response,row,deadline))
        except BaseException as exc:
            if isinstance(exc,ProviderNotDispatched):
                row["upstream_dispatched"]=False;row["model_execution"]="rejected_before_generation"
            if response is not None:
                try:response.close()
                except Exception:pass
            row["status"]="unknown" if row["upstream_dispatched"] else "gate_rejected"
            row["error_type"]=type(exc).__name__;row["completed_ns"]=time.monotonic_ns()
            if row["dispatch_id"] not in self._finished:self._record(row)
            return self._error(502 if row["upstream_dispatched"] else 403,"CALL_FAILED_OR_NOT_ADMITTED")
    def _finish(self,response,row,captured,actor_body,complete,consumed,redactions):
        row["provider_response"]=self._capture(row["dispatch_id"]+"-provider-response.body",captured)
        row["sanitized_provider_body"]=self._capture(row["dispatch_id"]+"-sanitized-provider.body",actor_body)
        row["capture_complete"]=complete;row["response_stream_consumed"]=consumed
        row["actor_protocol_receipt_observed"]=False
        row["credential_redactions"]=redactions
        row["status"]=("upstream_error" if complete and row.get("upstream_response_rejected") is True else
                       "succeeded" if complete and consumed else "unknown")
        row["completed_ns"]=time.monotonic_ns()
        try:
            docs=[]
            if response.status==200 and response.media_type.startswith("application/json"):
                docs=[strict(captured)]
            elif response.status==200 and response.media_type.startswith("text/event-stream"):
                pending=[]
                for line in captured.decode("utf-8").splitlines()+[""]:
                    if line.startswith("data:"):pending.append(line[5:].lstrip())
                    elif not line and pending:
                        text="\n".join(pending);pending=[]
                        if text!="[DONE]":
                            try:docs.append(strict(text))
                            except ValueError:pass
            for data in docs:
                if type(data) is not dict:continue
                if data.get("id") and type(data.get("choices")) is list and data["choices"]:
                    row["model_execution"]="confirmed"
                usage=data.get("usage",{})
                if type(usage) is dict:
                    for dst,src in (("input_tokens","prompt_tokens"),("output_tokens","completion_tokens")):
                        v=usage.get(src)
                        if type(v) is int and v>=0:row[dst]=v
        except (ValueError,TypeError,UnicodeError):pass
        self._record(row)

class _CredentialFilter:
    """Bounded lookbehind handles credentials split across streaming chunks."""
    def __init__(self,values):
        require(type(values) is tuple and all(type(v) is bytes and v for v in values),
                "PROVIDER_CREDENTIAL_FILTER")
        self.maxlen=max([len(v) for v in values] or [1]);self.pending=b"";self.count=0
        self.pattern=re.compile(b"|".join(re.escape(v) for v in sorted(set(values),key=len,reverse=True))) if values else None
    def feed(self,raw,final=False):
        if self.pattern is None:return raw
        data=self.pending+raw;cut=len(data) if final else max(0,len(data)-self.maxlen+1)
        result=[];pos=0
        for match in self.pattern.finditer(data):
            if match.start()>=cut:break
            result.extend((data[pos:match.start()],b"[REDACTED]"));pos=match.end();self.count+=1
        consumed=max(cut,pos)
        if pos<cut:result.append(data[pos:cut])
        self.pending=data[consumed:]
        return b"".join(result)

class _RecordedStream:
    """Close finalizes even before first iteration, never retrying a dispatch."""
    def __init__(self,broker,response,row,deadline):
        self.broker=broker;self.response=response;self.row=row;self.deadline=deadline
        self.iterator=iter(response.chunks);self.data=bytearray();self.actor=bytearray()
        self.filter=_CredentialFilter(response.credential_values)
        self.closed=False;self.complete=False;self.consumed=False
    def __iter__(self):return self
    def __next__(self):
        if self.closed:raise StopIteration
        if self.complete:self.consumed=True;self.close();raise StopIteration
        try:
            while True:
                require(self.broker.clock()<self.deadline,"MODEL_DEADLINE")
                try:chunk=next(self.iterator)
                except StopIteration:
                    self.complete=True
                    tail=self.filter.feed(b"",final=True)
                    if tail:self.actor.extend(tail);return tail
                    self.consumed=True;self.close();raise
                require(type(chunk) is bytes and len(self.data)+len(chunk)<=self.broker.max_response,
                        "PROVIDER_RESPONSE_LIMIT")
                self.data.extend(chunk);safe=self.filter.feed(chunk)
                if safe:self.actor.extend(safe);return safe
        except StopIteration:raise
        except BaseException as exc:
            self.row["error_type"]=type(exc).__name__;self.close();raise
    def close(self):
        if self.closed:return
        self.closed=True
        try:self.response.close()
        finally:self.broker._finish(self.response,self.row,bytes(self.data),bytes(self.actor),
                                  self.complete,self.consumed,self.filter.count)
