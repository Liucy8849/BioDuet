# Durable capture only. Not a JobStore/World, launcher or admission authority.
import os,json,hashlib,stat,time,uuid,threading,math,re
from copy import deepcopy

def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
class HostEvidenceJournal:
    def __init__(self,root,*,attempt_id,clock_domain,boot_id,source_sha256,max_record_bytes=1048576):
        if type(attempt_id) is not str or not attempt_id or type(max_record_bytes) is not int or max_record_bytes<=0:raise ValueError('JOURNAL_CONFIG')
        # Root supplies the fresh, private-view directory. Never follow symlinks.
        if not all(type(x) is str and x for x in (clock_domain,boot_id)) or type(source_sha256) is not str or re.fullmatch('[0-9a-f]{64}',source_sha256) is None:raise ValueError('JOURNAL_CLOCK_SOURCE')
        self.clock=clock_domain;self.boot=boot_id;self.source=source_sha256
        self.rootfd=os.open(os.fspath(root),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        self.fd=None;self.poisoned=False;self.closed=False;self.sequence=0;self.previous='0'*64
        self.attempt=attempt_id;self.limit=max_record_bytes;self.lock=threading.Lock()
        try:self.fd=os.open('events.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.rootfd);os.fsync(self.rootfd)
        except BaseException:os.close(self.rootfd);self.closed=True;raise
    def append(self,record):
        # A lock object does not spawn a thread. Fsync is host I/O, no world lock.
        with self.lock:
            if self.closed or self.poisoned:raise ValueError('JOURNAL_UNAVAILABLE')
            try:
                snapshot=deepcopy(record)
                if type(snapshot) is not dict:raise ValueError('JOURNAL_RECORD')
                if snapshot.get('kind')=='port_event' and (type(snapshot.get('event')) is not dict or snapshot['event'].get('attempt_id')!=self.attempt):raise ValueError('JOURNAL_EVENT_ATTEMPT')
                body=dict(schema='bioduet-host-capture-record/1',attempt_id=self.attempt,clock_domain=self.clock,boot_id=self.boot,collector_source_sha256=self.source,capture_time_ns=time.monotonic_ns(),capture_error_ns=max(1,math.ceil(time.get_clock_info('monotonic').resolution*1e9)),sequence=self.sequence,previous_sha256=self.previous,record=snapshot)
                raw=encoded(body)
                if len(raw)>self.limit:raise ValueError('JOURNAL_RECORD_SIZE')
                digest=hashlib.sha256(raw).hexdigest();line=encoded(dict(body,record_sha256=digest))+bytes([10]);view=memoryview(line)
                while view:
                    count=os.write(self.fd,view)
                    if count<=0:raise OSError('JOURNAL_SHORT_WRITE')
                    view=view[count:]
                os.fsync(self.fd)
                self.sequence+=1;self.previous=digest
                return dict(sequence=body['sequence'],record_sha256=digest)
            except BaseException:self.poisoned=True;raise
    def write_event(self,event):return self.append(dict(kind='port_event',event=deepcopy(event)))
    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True
            try:
                if self.fd is not None:os.close(self.fd)
            finally:os.close(self.rootfd)

class ExistingJobObserver:
    def __init__(self,existing_bound_mcp,scope,*,journal):
        if getattr(existing_bound_mcp,'_scope',None) is not scope:raise ValueError('JOB_CAPTURE_BOUND_SCOPE')
        self.bridge=existing_bound_mcp;self.scope=scope;self.journal=journal
        self.identity={k:getattr(scope,k) for k in ('episode_id','attempt_id','project_id','principal_id')}
        if self.identity['attempt_id']!=journal.attempt:raise ValueError('JOB_CAPTURE_ATTEMPT')
    def invoke(self,method,**arguments):
        # No submit/start/retry endpoint. BoundMCP keeps original per-call router authorization.
        fields={'lookup':{'operation_id','idempotency_key'},'status':{'job_id'},'result':{'job_id'},'cancel':{'job_id'}}
        if method not in fields or set(arguments)!=fields[method] or any(type(v) is not str or not v for v in arguments.values()):raise ValueError('JOB_CAPTURE_REQUEST')
        call_id=uuid.uuid4().hex
        self.journal.append(dict(kind='job_port_call',call_id=call_id,scope=self.identity,method=method,arguments=deepcopy(arguments),time_ns=time.monotonic_ns(),meaning='request, not completion or physical cancellation'))
        try:result=self.bridge.invoke('job.'+method,json.dumps(arguments,sort_keys=True,separators=(',',':'),allow_nan=False))
        except BaseException as exc:
            self.journal.append(dict(kind='job_port_failed',call_id=call_id,error_type=type(exc).__name__,business_effects='unknown',time_ns=time.monotonic_ns()));raise
        self.journal.append(dict(kind='job_port_returned',call_id=call_id,result=deepcopy(result),result_sha256=hashlib.sha256(encoded(result)).hexdigest(),business_effects='not_inferred',time_ns=time.monotonic_ns()))
        return result
