# Capture adapter for M's first real scientific episode. No second Session/World.
from copy import deepcopy
from types import SimpleNamespace
import re
from bioduet_vnext.participant_observer_v04 import ObservedParticipantBridge,request_sha256
from host_evidence_journal_v04 import HostEvidenceJournal,ExistingJobObserver
from authorization_stage_recorder_v02 import AuthorizationStageRecorder
from port_witness_v01 import PortWitness

class EpisodeCapture:
    def __init__(self,journal_root,*,episode_id,attempt_id,project_id,clock_domain,boot_id,composition_sha256,transport_binding_factory):
        if not all(type(v) is str and v for v in (episode_id,attempt_id,project_id,clock_domain,boot_id)) or not callable(transport_binding_factory):raise ValueError('EPISODE_CAPTURE_CONFIG')
        self.identity=dict(episode_id=episode_id,attempt_id=attempt_id,project_id=project_id)
        self.clock=clock_domain;self.boot=boot_id;self.composition=composition_sha256
        self.transport=transport_binding_factory;self.session=None;self.scopes={};self.bridges={};self.authorize=None;self.closed=False
        self.journal=HostEvidenceJournal(journal_root,attempt_id=attempt_id,clock_domain=clock_domain,boot_id=boot_id,source_sha256=composition_sha256)
        self.recorder=AuthorizationStageRecorder(journal=self.journal,request_digest=request_sha256)
    def wrap_authorize_tool(self,existing_authorize):
        if self.closed or self.authorize is not None or self.session is not None:raise ValueError('CAPTURE_AUTH_ALREADY_BOUND')
        self.authorize=self.recorder.wrap_authorize(existing_authorize)
        return self.authorize
    def bind_existing_session(self,session):
        if self.closed or self.session is not None or self.authorize is None or getattr(session,'_authorize_tool',None) is not self.authorize or getattr(session,'_closed',True):raise ValueError('CAPTURE_SESSION_BINDING')
        scopes=getattr(session,'_scopes',None)
        if type(scopes) is not dict or not scopes:raise ValueError('CAPTURE_SCOPES')
        values=list(scopes.values())
        if not {'A','H'}.issubset({getattr(s,'role',None) for s in values}):raise ValueError('CAPTURE_DISTINCT_A_H_REQUIRED')
        if len({id(s) for s in values})!=len(values):raise ValueError('CAPTURE_SHARED_SCOPE_OBJECT')
        for principal,s in scopes.items():
            if principal!=s.principal_id or any(getattr(s,k)!=v for k,v in self.identity.items()):raise ValueError('CAPTURE_SCOPE_IDENTITY')
        self.session=session;self.scopes=dict(scopes)
    def _issued(self,scope):
        if self.closed or self.session is None or getattr(self.session,'_closed',True) or self.scopes.get(scope.principal_id) is not scope:raise ValueError('CAPTURE_SCOPE_NOT_LIVE')
    def bridge(self,scope):
        self._issued(scope)
        if scope.principal_id in self.bridges:return self.bridges[scope.principal_id]
        capture=self
        class CapturedBridge(ObservedParticipantBridge):
            def invoke(self,tool_name,arguments_json):
                capture._issued(scope)
                binding=capture.transport(scope,tool_name,arguments_json,request_sha256(tool_name,arguments_json))
                # Original FastMCP definition is inherited unchanged. No role/request
                # fields are inserted into participant tool arguments.
                original=SimpleNamespace(_scope=scope,invoke=super().invoke)
                return capture.recorder.invoke(original,scope,tool_name,arguments_json,transport_binding=binding)
        bridge=CapturedBridge(self.session.bridge(scope),scope,bind_transport_request=self.recorder.bind_transport,write_event=self.recorder.write_event,witness_class=PortWitness,collector_id='episode-server-'+scope.principal_id,collector_source_sha256=self.composition,clock_domain=self.clock,boot_id=self.boot)
        self.bridges[scope.principal_id]=bridge
        return bridge
    def jobs(self,scope):return ExistingJobObserver(self.bridge(scope),scope,journal=self.journal)
    def record_external_receipt(self,category,scope,request_ref,receipt_ref,*,verify_source):
        self._issued(scope)
        if category not in ('world','message','job_launch','job_result','job_cancel','job_retirement','participant_exit'):raise ValueError('CAPTURE_RECEIPT_CATEGORY')
        if type(request_ref) is not dict or request_ref.get('attempt_id')!=self.identity['attempt_id'] or type(receipt_ref) is not dict or set(receipt_ref)!={'artifact_id','bytes','sha256'}:raise ValueError('CAPTURE_RECEIPT_REFERENCE')
        if type(receipt_ref['artifact_id']) is not str or not receipt_ref['artifact_id'] or type(receipt_ref['bytes']) is not int or receipt_ref['bytes']<0 or type(receipt_ref['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',receipt_ref['sha256']) is None or not callable(verify_source):raise ValueError('CAPTURE_RECEIPT_SHAPE')
        if any(request_ref.get(k)!=v for k,v in self.identity.items()) or request_ref.get('principal_id')!=scope.principal_id or not any(type(request_ref.get(k)) is str and request_ref[k] for k in ('request_id','operation_id')):raise ValueError('CAPTURE_RECEIPT_SCOPE_JOIN')
        reference=deepcopy(receipt_ref);request=deepcopy(request_ref);scope_ref={k:getattr(scope,k) for k in ('episode_id','attempt_id','project_id','principal_id','role')};error=None
        try:verified=verify_source(category,scope,deepcopy(request),deepcopy(reference)) is True
        except Exception as exc:verified=False;error=type(exc).__name__
        # Receipt provenance is not scientific validity, a World commit, or physical
        # retirement. Actual authority semantics remain the existing owner's job.
        return self.journal.append(dict(kind='external_receipt_reference',category=category,scope=scope_ref,request_ref=request,receipt_ref=reference,source_binding='verified_by_supplied_host_callback' if verified else 'unknown',source_error_type=error,scientific_validity=None,meaning='reference only; does not fill commit/reply/receipt lifecycle phases or certify retirement'))
    def close(self):
        if not self.closed:
            self.closed=True;self.journal.close()
        # M closes the original session/participants; Root proves exact jobs/units
        # retired. Closing an evidence FD does not certify episode cleanup.
