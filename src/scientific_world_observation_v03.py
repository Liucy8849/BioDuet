# Read-only observation of M's existing BrokeredScienceWorld/LogicalSession.
# No World, action, H decision, token, execution result or scientific choice created.
from copy import deepcopy
import hashlib,json,uuid

def digest(value):return evidence_copy(value)[1]
def evidence_copy(value):
    try:
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        return json.loads(raw),hashlib.sha256(raw).hexdigest()
    except Exception:
        return dict(capture_serialization='unavailable',input_type=type(value).__name__),None

class ObservedScienceWorld:
    def __init__(self,existing_world,*,capture,role_scopes,instance_binding_ref):
        port=getattr(existing_world,'_port',None)
        contexts=getattr(existing_world,'_contexts',None)
        if port is None or type(contexts) is not dict or set(role_scopes)!={'A','H'} or type(instance_binding_ref) is not dict:raise ValueError('SCIENCE_CAPTURE_BINDINGS')
        for actor,scope in role_scopes.items():
            capture._issued(scope)
            if scope.role!=actor or actor not in contexts or port._contexts.get(actor) is not contexts[actor]:raise ValueError('SCIENCE_CAPTURE_CONTEXT')
        self._world=existing_world;self._capture=capture;self._roles=dict(role_scopes);self._binding=deepcopy(instance_binding_ref)
        self._aliases=dict(capture_identity=deepcopy(capture.identity),world_project_id=port.project_id,world_episode_id=port.episode_id,role_map={a:dict(capture_principal_id=s.principal_id,world_principal_id=contexts[a].principal_id) for a,s in role_scopes.items()},instance_binding_ref=self._binding)
        capture.journal.append(dict(kind='scientific_identity_namespace_binding',binding=self._aliases,meaning='explicit mapping; original World UUIDs are never overwritten'))
    def __getattr__(self,name):return getattr(self._world,name)
    def execute(self,actor,request):
        if actor not in self._roles:raise ValueError('SCIENCE_CAPTURE_ACTOR')
        scope=self._roles[actor];self._capture._issued(scope);world=self._world
        req,request_digest=evidence_copy(request);call_id=uuid.uuid4().hex;op=req.get('operation_id') if type(req) is dict else None
        key=(actor,op) if type(op) is str else None
        history_start=len(world.history);broker_start=len(world.broker_audit);port_start=len(world.port_audit)
        previous=deepcopy(world.operations.get(key)) if key is not None else None
        self._capture.journal.append(dict(kind='science_world_call',call_id=call_id,actor=actor,request=req,request_sha256=request_digest,identity_binding=self._aliases,history_start=history_start,broker_start=broker_start,port_start=port_start))
        try:result=world.execute(actor,request)
        except BaseException as exc:
            self._capture.journal.append(dict(kind='science_world_call_raised',call_id=call_id,error_type=type(exc).__name__,business_effects='unknown',world_result='not_received',execution_result='not_inferred'));raise
        added=deepcopy(world.history[history_start:]);broker=deepcopy(world.broker_audit[broker_start:]);ports=deepcopy(world.port_audit[port_start:]);current=deepcopy(world.operations.get(key)) if key is not None else None
        matches=[(i,r) for i,r in enumerate(added,history_start) if r.get('actor')==actor and r.get('request')==req and r.get('result')==result]
        state='not_observed'
        if len(matches)==1 and current is not None and current[1]==result:state='existing_history_and_operation_recorded'
        elif not added and previous is not None and current==previous and previous[1]==result:state='original_operation_replayed_no_new_transition'
        elif type(result) is dict and result.get('status')=='rejected':state='rejected_return_no_transition_claim'
        elif type(req) is dict and req.get('action_id')=='A01' and not added:state='observation_return_no_transition_claim'
        result_copy,result_digest=evidence_copy(result)
        self._capture.journal.append(dict(kind='science_world_return',call_id=call_id,actor=actor,operation_id=op,tool_return_sha256=result_digest,tool_return_status=result.get('status') if type(result) is dict and type(result.get('status')) is str else None,broker_forwarded=[r.get('forwarded') for r in broker],broker_receipts=broker,port_receipt_count=len(ports),port_receipts_sha256=digest(ports),logical_world_transition=state,history_refs=[dict(index=i,sha256=digest(r)) for i,r in matches],operation_request_signature=current[0] if current is not None else None,operation_record_sha256=digest(current) if current is not None else None,physical_durability='not_asserted',scientific_validity=None,launcher_result_retirement='not_inferred'))
        return result

class ObservedLogicalSession:
    def __init__(self,existing_session,*,capture,observed_world):
        if existing_session.world is not observed_world:raise ValueError('LOGICAL_CAPTURE_WORLD')
        object.__setattr__(self,'_session',existing_session);object.__setattr__(self,'_capture',capture)
        capture.journal.append(dict(kind='logical_session_namespace_binding',logical_episode_id=existing_session.episode_id,capture_identity=deepcopy(capture.identity),world_binding=deepcopy(observed_world._aliases),max_turns=getattr(existing_session,'max_turns','unknown'),logical_deadline=getattr(existing_session,'deadline','unknown'),meaning='no limit conversion or ID overwrite'))
    def __getattr__(self,name):return getattr(self._session,name)
    def __setattr__(self,name,value):
        if name in ('_session','_capture'):object.__setattr__(self,name,value)
        else:setattr(self._session,name,value)
    def next_turn(self):
        packet=self._session.next_turn()
        if packet is None:
            self._capture.journal.append(dict(kind='logical_next_turn_none',logical_episode_id=self._session.episode_id,terminal=self._session.terminal,seq=self._session.seq,tick=self._session.tick));return None
        messages=deepcopy(packet.get('messages',[]))
        self._capture.journal.append(dict(kind='logical_packet_issued',logical_episode_id=self._session.episode_id,actor=packet.get('actor'),seq=self._session.seq,tick=packet.get('tick'),message_refs=[dict(index=i,sha256=digest(m),sender=m.get('from'),sent_tick=m.get('sent_tick')) for i,m in enumerate(messages)],message_delivery_level='kernel_packet_issued_not_model_receipt',actual_turn_token_exported=False))
        return packet
    def submit(self,token,decision):
        # Never serialize token or pending packet; pass the original through unchanged.
        session=self._session;pending=session.pending;actor=pending.get('actor') if type(pending) is dict else None;seq=session.seq;tick=session.tick;count=len(session.records);call_id=uuid.uuid4().hex
        decision_copy,decision_digest=evidence_copy(decision)
        self._capture.journal.append(dict(kind='logical_submit_call',call_id=call_id,logical_episode_id=session.episode_id,actor=actor,seq=seq,tick=tick,decision_sha256=decision_digest,decision_serialization=decision_copy.get('capture_serialization') if type(decision_copy) is dict else None,actual_turn_token_exported=False))
        try:result=session.submit(token,decision)
        except BaseException as exc:
            self._capture.journal.append(dict(kind='logical_submit_raised',call_id=call_id,error_type=type(exc).__name__,effects='unknown'));raise
        appended=deepcopy(session.records[count:]);recorded=len(appended)==1 and appended[0]==result
        queued=False
        if recorded and type(result.get('decision')) is dict and result['decision'].get('kind')=='message' and result.get('result',{}).get('status')=='message_queued':
            d=result['decision']
            queued=any(m.get('from')==actor and m.get('sent_tick')==tick and m.get('text')==d['text'] for m in session.inbox[d['to']])
        self._capture.journal.append(dict(kind='logical_submit_return',call_id=call_id,logical_episode_id=session.episode_id,seq=seq,record_index=count if recorded else None,logical_record_appended=recorded,record_sha256=digest(result),decision_kind=result.get('decision',{}).get('kind'),result_status=result.get('result',{}).get('status'),message_queued_in_existing_inbox=queued,message_received_or_understood='not_inferred',world_commit='not_inferred_from_logical_record',participant_finish_is_not_job_retirement=True))
        return result
