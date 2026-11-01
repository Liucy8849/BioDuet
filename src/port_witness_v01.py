# Port-side witnesses only. No World/transport/launcher or automatic business commit.
from copy import deepcopy
import time,math,uuid,hashlib,json
PHASES=('client_send','client_receipt','server_receive','validation_begin','validation_end','commit_or_reject','server_reply','server_result_ready','port_failed')
class PortWitness:
    def __init__(self, *, scope, side, request_id, request_sha256, clock_domain, boot_id, source_sha256, write_event):
        if side not in ('client','server') or not callable(write_event):raise ValueError('PORT_CONFIG')
        if set(scope)!={'episode_id','attempt_id','project_id','principal_id'} or not all(type(v) is str and v for v in scope.values()):raise ValueError('PORT_SCOPE')
        if not all(type(x) is str and x for x in (request_id,request_sha256,clock_domain,boot_id,source_sha256)):raise ValueError('PORT_BINDING')
        self.base=deepcopy(dict(scope,request_id=request_id,request_sha256=request_sha256,clock_domain=clock_domain,boot_id=boot_id,collector_source_sha256=source_sha256))
        self.side=side;self.write=write_event;self.failed=False;self.seen=set()
    def record(self,kind,*,causes,resources,boundary,proof_ref=None,details=None):
        if self.failed:raise ValueError('PORT_CAPTURE_POISONED')
        if kind not in PHASES or kind in self.seen:raise ValueError('PORT_PHASE')
        allowed=('client_send','client_receipt','port_failed') if self.side=='client' else tuple(k for k in PHASES if k not in ('client_send','client_receipt'))
        if kind not in allowed:raise ValueError('PORT_WRONG_SIDE')
        if type(causes) is not list or type(resources) is not list or any(type(x) is not str or not x for x in causes+resources):raise ValueError('PORT_REFERENCES')
        if type(boundary) is not str or not boundary:raise ValueError('PORT_BOUNDARY')
        # No resources/authority/version values are invented by this emitter.
        e=dict(self.base,event_id=uuid.uuid4().hex,kind=kind,causes=deepcopy(causes),resources=deepcopy(resources),boundary=boundary,proof_ref=deepcopy(proof_ref),details=deepcopy(details),time_ns=time.monotonic_ns(),error_ns=max(1,math.ceil(time.get_clock_info('monotonic').resolution*1e9)))
        try:self.write(deepcopy(e))
        except BaseException:self.failed=True;raise
        self.seen.add(kind);return e
    def server_invoke(self, existing_bound_mcp, tool_name, arguments_json, *, send_event_ref):
        # Install at the actual server invocation site, never around remote client.
        received=self.record('server_receive',causes=[send_event_ref],resources=[],boundary='BoundMCP.invoke entry')
        try:result=existing_bound_mcp.invoke(tool_name,arguments_json)
        except BaseException as exc:
            self.record('port_failed',causes=[received['event_id']],resources=[],boundary='BoundMCP.invoke raised',details=dict(error_type=type(exc).__name__));raise
        # A tool return is neither a scientific commit nor actual wire reply.
        self.record('server_result_ready',causes=[received['event_id']],resources=[],boundary='BoundMCP.invoke returned')
        return result
    async def client_invoke(self, existing_client_call, tool_name, arguments_json, *, decode_receipt):
        sent=self.record('client_send',causes=[],resources=[],boundary='native client API dispatch')
        try:response=await existing_client_call(tool_name,arguments_json)
        except BaseException as exc:
            self.record('port_failed',causes=[sent['event_id']],resources=[],boundary='native client API raised',details=dict(error_type=type(exc).__name__));raise
        # Trusted host decoder binds actual protocol response to reply event, not cognition.
        receipt=decode_receipt(response)
        if type(receipt) is not dict or type(receipt.get('server_reply_event_id')) is not str or not receipt['server_reply_event_id']:raise ValueError('REPLY_CORRELATION_UNKNOWN')
        self.record('client_receipt',causes=[receipt['server_reply_event_id']],resources=[],boundary='native client protocol response returned',proof_ref=receipt.get('proof_ref'))
        return response
