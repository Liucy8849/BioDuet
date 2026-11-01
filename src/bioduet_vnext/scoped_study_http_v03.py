"""Finite private-loopback transport for the single existing science host.
Passive listener READY is not a grant. Only a trusted actual-admission verifier
can activate business, and role capabilities never select caller-supplied Scope.
"""
import json,hashlib,secrets,threading,time,math
from http.server import BaseHTTPRequestHandler,HTTPServer
from socketserver import ThreadingMixIn,TCPServer
from .contracts_v01 import require

class _BoundedThreads(ThreadingMixIn,HTTPServer):
    daemon_threads=False
    block_on_close=True
    def __init__(self,*args,max_handlers=4,**kwargs):
        self._slots=threading.BoundedSemaphore(max_handlers)
        super().__init__(*args,**kwargs)
    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name="localhost";self.server_port=self.server_address[1]
    def process_request(self,request,address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:self._slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self._slots.release()

class ScopedStudyHTTPService:
    def __init__(self,*,role_capability_digests,verify_actual_admission,endpoint_factory,
                 final_deadline_monotonic,transport_recorder,max_handlers=4):
        require(set(role_capability_digests)=={"A","H"} and
                len(set(role_capability_digests.values()))==2 and
                all(type(x) is str and len(x)==64 for x in role_capability_digests.values()),
                "INDEPENDENT_ROOT_BOUND_ROLE_CAPABILITY_DIGESTS")
        require(callable(verify_actual_admission) and callable(endpoint_factory),"TRUSTED_ADMISSION_AND_ONE_HOST_FACTORY")
        require(type(final_deadline_monotonic) in (int,float) and
                math.isfinite(final_deadline_monotonic) and final_deadline_monotonic>time.monotonic(),
                "FINITE_HOST_UNIT_DEADLINE")
        require(type(max_handlers) is int and 1<=max_handlers<=4,"FINITE_HANDLER_TASKS")
        self.cap_digests=dict(role_capability_digests);self.verify=verify_actual_admission
        self.factory=endpoint_factory;self.final_deadline=final_deadline_monotonic
        require(callable(transport_recorder.begin) and callable(transport_recorder.end),"ACTUAL_INGRESS_CONTEXT_RECORDER")
        self.transport=transport_recorder
        self.endpoint=None;self.active=False;self.deadline=None;self.audit=[];self.server=None
        self.max_handlers=max_handlers
    def activate(self,actual_admission):
        require(not self.active and self.endpoint is None,"FRESH_HOST_ACTIVATION_ONLY")
        require(self.verify(actual_admission) is True,"ACTUAL_CURRENT_CONTROLLER_ADMISSION_REQUIRED")
        deadline=actual_admission["deadline_monotonic"]
        require(type(deadline) in (int,float) and math.isfinite(deadline) and
                time.monotonic()<deadline<=self.final_deadline,"CURRENT_FINITE_HOST_LEASE")
        # Construction/registration occurs only after verified actual GO.
        endpoint=self.factory(actual_admission)
        require(endpoint.deadline==deadline and set(endpoint.scopes)=={"A","H"},"ONE_CURRENT_ROLE_BOUND_ENDPOINT")
        self.endpoint=endpoint;self.deadline=deadline;self.active=True
    def bind_passive(self,port=0):
        require(self.server is None and type(port) is int and 0<=port<=65535,"FRESH_FIXED_PRIVATE_LISTENER")
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version="HTTP/1.0"
            def log_message(self,*args):pass
            def do_POST(self):
                self.connection.settimeout(30)
                body=None;role=None;context_token=None;received_ns=time.monotonic_ns();row={"state":"received","business_invoked":False,
                    "request_sha256":None,"role":None,"error_type":None}
                owner.audit.append(row)
                try:
                    if self.path!="/invoke":return self.reply(404,{"error":"NOT_FOUND"})
                    header=self.headers.get("Authorization","")
                    digest=hashlib.sha256(header[7:].encode()).hexdigest() if header.startswith("Bearer ") else ""
                    for candidate,expected in owner.cap_digests.items():
                        if secrets.compare_digest(digest,expected):role=candidate
                    if role is None:return self.reply(403,{"error":"NOT_AUTHORIZED"})
                    row["role"]=role
                    if not owner.active or time.monotonic()>=owner.deadline:
                        return self.reply(403,{"error":"NO_CURRENT_ADMISSION"})
                    length=int(self.headers.get("Content-Length","-1"))
                    require(0<length<=1048576,"FINITE_REQUEST_BYTES")
                    body=self.rfile.read(length);require(len(body)==length,"COMPLETE_REQUEST_BODY")
                    row["request_sha256"]=hashlib.sha256(body).hexdigest()
                    request=json.loads(body)
                    require(type(request) is dict and set(request)=={"tool_name","arguments_json"}
                            and type(request["tool_name"]) is str
                            and type(request["arguments_json"]) is str,"EXACT_NATIVE_TOOL_WIRE")
                    scope=owner.endpoint.scopes[role]
                    row["business_invoked"]=True
                    context_token=owner.transport.begin(scope=scope,headers=self.headers,body=body,
                        request=request,peer=self.client_address,received_ns=received_ns)
                    result=owner.endpoint.invoke(scope,request["tool_name"],request["arguments_json"])
                    row["state"]="business_returned_not_commit_proof"
                    self.reply(200,result);row["state"]="response_written_not_model_receipt"
                except Exception as exc:
                    row["error_type"]=type(exc).__name__
                    row["state"]="error_or_transport_unknown"
                    try:self.reply(500,{"error_type":type(exc).__name__,"state":"outcome_unknown",
                        "do_not_blindly_resubmit":True})
                    except (OSError,ValueError):pass
                finally:
                    if context_token is not None:owner.transport.end(context_token)
            def reply(self,status,value):
                data=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
                require(len(data)<=1048576,"FINITE_RESPONSE_BYTES")
                self.send_response(status);self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
        self.server=_BoundedThreads(("127.0.0.1",port),Handler,max_handlers=self.max_handlers)
        self.server.timeout=.2
        return {"host":"127.0.0.1","port":self.server.server_port,"passive_READY":True,
                "lease":None,"business_constructed":False,"role_capabilities_exported":False}
    def serve_until(self,stop):
        require(self.server is not None and callable(stop),"PASSIVE_LISTENER_REQUIRED")
        try:
            while time.monotonic()<self.final_deadline and not stop():self.server.handle_request()
        finally:self.active=False;self.server.server_close()
