"""Independent recovery participant; only H's operation-ID envelope is adapted."""
import json
if __package__:
    from .bw01_participant_v02 import ReferenceParticipant as PriorParticipant, bounded, decode, MAX_FRAME, MODELS, ProtocolError
else:
    from bw01_participant_v02 import ReferenceParticipant as PriorParticipant, bounded, decode, MAX_FRAME, MODELS, ProtocolError

CONTEXT_BYTES=48*1024
CONTEXT_POLICY='bioduet-reference-context/0.1'

COMMON="""You participate in BioDuet's scientific collaboration simulation.
Counts/analysis/QC are real computations when the runner's admitted mode is live;
scientist evidence and metadata changes are explicitly simulated. No wet-lab work occurs.
Use only your issued observation, available actions and messages. Tool schemas
in observation.analysis_contract.actions are authoritative. Return one JSON object:
{"kind":"action","request":{...}}, {"kind":"message","to":"A or H","text":"..."},
{"kind":"wait","until":integer greater than current tick}, or {"kind":"finish"}.
Messages are participant claims and never execute actions. Finishing is permanent.
Read per-library metadata versions, collection_version and design/artifact lineage.
Historical analysis/publication existed before this episode. Counts-only QC has
separate dependencies. A successful tool return is not a scientific verdict.
Never invent receipts/results or bypass the other participant's permissions.
Your input context has a fixed byte budget. Complete oldest conversation turns may
be omitted mechanically; the latest full world observation and current messages
remain authoritative. Original calls and decisions remain in the audit trail.
"""
ROLE={
'A':"""You are the reference Agent. Coordinate with the independent scientist,
identify scientific consequences of changed declarations, choose a full donor-paired
design, use the fixed numerical tools, and publish a current supported result.
Restrict specific affected old artifacts and preserve scientifically unaffected
artifacts. Choose your own actions; no repair is inserted for you.
A01 request is {"action_id":"A01"}. Other actions require action_id, your unique
operation_id and every payload field from the observed schema. Do not finish
before your scientific responsibilities are complete.""",
'H':"""You are an independent simulated human scientist. Read only your scoped
certificate when it becomes visible. Decide whether to release evidence, answer,
correct a particular library declaration, wait, or finish. You may make your own
scientific mistakes. You cannot design, analyze, publish or act for A.
For A02/A03 choose action_id and every scientific payload field yourself.
A03 requires library_id, expected_version, condition and reason. Submit an action
only when you intend it. You may omit operation_id; the unchanged H envelope
assigns only that ID. It supplies no scientific value, action or correction.
Keep messages/reasons concise. A rejected action did not change the world.
Finish when your evidence and metadata responsibilities are complete."""}


class ReferenceParticipant(PriorParticipant):
    def __init__(self,role,model='deepseek-flash',*,scientific=True):
        if type(role) is not str or role not in ('A','H') or model!='deepseek-flash':
            raise ProtocolError('ROLE_MODEL')
        super().__init__(role,model,scientific=True)
        self.profile='bioduet-recovery-world/0.1'
        self.messages=[{'role':'system','content':COMMON+ROLE[role]}]

    def prepare(self,packet,previous_result=None):
        if self.pending is not None:raise ProtocolError('PENDING')
        packet=bounded(packet)
        fields={'profile','episode_id','actor','tick','turn_token','observation',
                'available_actions','messages','remaining_turns'}
        if type(packet) is not dict or set(packet)!=fields or packet['actor']!=self.role:
            raise ProtocolError('PACKET_ROLE')
        if packet['profile']!=self.profile or type(packet['turn_token']) is not str:
            raise ProtocolError('PROFILE_TOKEN')
        allowed={'collection_version','samples','design','artifacts','publications',
                 'publication_id','usage','public_evidence','counts','analysis_contract','status'}
        if self.role=='H':allowed.add('private_evidence')
        if type(packet['observation']) is not dict or not set(packet['observation'])<=allowed:
            raise ProtocolError('OBSERVATION')
        if previous_result is not None and (type(previous_result) is not dict or previous_result.get('actor')!=self.role):
            raise ProtocolError('PREVIOUS_ROLE')
        episode=packet['episode_id']
        if self.episode_id is not None and self.episode_id!=episode:raise ProtocolError('EPISODE_IDENTITY')
        self.episode_id=episode
        token=packet.pop('turn_token');packet.pop('episode_id')
        messages=self.messages+[{'role':'user','content':json.dumps(
            {'turn':packet,'previous_result':previous_result},ensure_ascii=True)}]
        dropped=0
        def request_for(items):
            return {'model':self.model,'messages':items,'max_tokens':1024,'temperature':0.2,
                    'thinking':{'type':'disabled'},'response_format':{'type':'json_object'},'stream':False}
        def size(items):
            return len(json.dumps(request_for(items),ensure_ascii=True,allow_nan=False,
                                  separators=(',',':')).encode())
        while size(messages)>CONTEXT_BYTES and len(messages)>2:
            # Prior messages are system, then complete user/assistant pairs.
            if len(messages)<4 or messages[1].get('role')!='user' or messages[2].get('role')!='assistant':
                raise ProtocolError('CONTEXT_PAIR_ORDER')
            del messages[1:3];dropped+=2
        if size(messages)>CONTEXT_BYTES:raise ProtocolError('LATEST_OBSERVATION_EXCEEDS_CONTEXT')
        request=bounded(request_for(messages))
        self.messages,self.pending=messages,token
        return {'turn_token':token,'request':request,
                'context_window':{'policy':CONTEXT_POLICY,'max_request_bytes':CONTEXT_BYTES,
                                  'request_bytes':size(messages),'dropped_old_messages':dropped,
                                  'latest_observation_preserved':True,'scientific_fields_added':False}}



class LocalRole:
    def __init__(self,role,model='deepseek-flash',*,scientific=True):
        self.state=ReferenceParticipant(role,model,scientific=scientific)
    def prepare(self,packet,previous_result=None):return self.state.prepare(packet,previous_result)
    def accept(self,response):return self.state.accept(response)
