# Trusted host context -> actual existing authorization callback witnesses.
# No World/transport/launcher, no fabricated commit/reply/client receipt.
from contextvars import ContextVar
from copy import deepcopy
import json,hashlib,time,math,uuid
class AuthorizationStageRecorder:
    def __init__(self,*,journal,request_digest):
        if not callable(request_digest):raise ValueError('AUTH_STAGE_CONFIG')
        self.journal=journal;self.digest=request_digest;self.active=ContextVar('C-authority-'+uuid.uuid4().hex,default=None)
    def invoke(self,observer,scope,tool_name,arguments_json,*,transport_binding):
        if self.active.get() is not None:raise ValueError('AUTH_STAGE_NESTED_CONTEXT')
        if getattr(observer,'_scope',None) is not scope:raise ValueError('AUTH_STAGE_SCOPE')
        expected={k:getattr(scope,k) for k in ('episode_id','attempt_id','project_id','principal_id')}
        binding=deepcopy(transport_binding)
        if type(binding) is not dict or binding.get('scope')!=expected or binding.get('request_sha256')!=self.digest(tool_name,arguments_json):raise ValueError('AUTH_STAGE_BINDING')
        token=self.active.set(dict(scope=scope,binding=binding,last=None,server_base=None))
        try:return observer.invoke(tool_name,arguments_json)
        finally:self.active.reset(token)
    def bind_transport(self,scope,tool_name,arguments_json,digest):
        row=self.active.get()
        if row is None or row['scope'] is not scope or row['binding']['request_sha256']!=digest or digest!=self.digest(tool_name,arguments_json):raise ValueError('AUTH_STAGE_NO_CONTEXT')
        return deepcopy(row['binding'])
    def write_event(self,event):
        row=self.active.get()
        if row is None or any(event.get(k)!=row['binding'].get(k) for k in ('request_id','request_sha256')) or any(event.get(k)!=v for k,v in row['binding']['scope'].items()):raise ValueError('AUTH_STAGE_EVENT_CONTEXT')
        receipt=self.journal.write_event(event)
        row['last']=event['event_id']
        if event['kind']=='server_receive':row['server_base']=deepcopy(event)
        return receipt
    def stage(self,kind,details):
        row=self.active.get()
        if row is None or row['server_base'] is None:raise ValueError('AUTH_STAGE_SERVER_BOUNDARY_MISSING')
        event=deepcopy(row['server_base'])
        event.update(event_id=uuid.uuid4().hex,kind=kind,causes=[row['last']],resources=[],boundary='actual ParticipantTools.authorize_tool callback',details=deepcopy(details),time_ns=time.monotonic_ns(),error_ns=max(1,math.ceil(time.get_clock_info('monotonic').resolution*1e9)))
        return self.write_event(event)
    def wrap_authorize(self,existing_authorize):
        if not callable(existing_authorize):raise ValueError('AUTH_CALLBACK')
        def authorize(scope,name,args):
            row=self.active.get()
            if row is None or row['scope'] is not scope:raise ValueError('AUTH_STAGE_UNBOUND_CALLBACK')
            self.stage('validation_begin',dict(validation_scope='tool_authorization',tool=name))
            try:proof=existing_authorize(scope,name,args)
            except BaseException as exc:
                self.stage('validation_end',dict(validation_scope='tool_authorization',tool=name,allowed=None,error_type=type(exc).__name__,business_effects='unknown'));raise
            snapshot=deepcopy(proof)
            allowed=snapshot.get('allowed') if type(snapshot) is dict and type(snapshot.get('allowed')) is bool else None
            digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            self.stage('validation_end',dict(validation_scope='tool_authorization',tool=name,allowed=allowed,proof_sha256=digest,authority_seq=snapshot.get('authority_seq') if type(snapshot) is dict else None))
            return proof
        return authorize
