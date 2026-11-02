"""One shared durable budget and raw transcript for reference/native/H calls."""
import threading
import time
from pathlib import Path

from .bioduet_budget_v02 import EpisodeBudget
from .bioduet_journal_v02 import FreshJournal
from .bioduet_integrity_v01 import need, sha, save

NATIVE_TOOLS=('research_research_action','research_research_message','research_research_wait',
              'research_research_finish','research_action','research_message','research_wait','research_finish')


class ModelCoordinator:
    def __init__(self,window,transport,output,episode_id,*,validate_request,live,
                 clock=time.monotonic,max_attempts=None):
        self.window=window;self.transport=transport;self.root=Path(output)
        self.root.mkdir(mode=0o700)
        (self.root/'raw').mkdir(mode=0o700)
        self.journal=FreshJournal(self.root)
        self.clock=clock;self.lock=threading.RLock();self.cancel=threading.Event()
        self.validate=validate_request;self.live=live;self.records=[];self.gate_refusals=[]
        self._closed=False;self.maximum_deadline=40
        self.budget=EpisodeBudget(episode_id=episode_id,grant_id=window.document['grant_id'],
            clock=clock,journal=self.journal,trusted_wall_now=window.wall(),
            grant_expires_wall=window.document['expires_epoch'],
            episode_seconds=window.document['episode_seconds'],max_attempts=max_attempts,cleanup_seconds=15)

    def invoke(self,request,*,actor,purpose='primary',cancel=None,parent_deadline=None):
        with self.lock:
            if self.cancel.is_set() or cancel is not None and cancel.is_set():
                return {'status':'failed','code':'CANCELLED','knowledge':'not_sent'}
            token=None;dispatched=False;request_pin=None
            try:
                need(type(actor) is str and actor in ('A','H'),'ACTOR')
                need(type(purpose) is str and purpose in ('primary','auxiliary','retry'),'PURPOSE')
                need(type(request) is dict and request.get('model')=='deepseek-flash','MODEL')
                request_pin=sha(request)
                reservation=self.budget.reserve(actor=actor,purpose=purpose,
                    request_sha256=request_pin,stage_seconds=self.maximum_deadline,parent_deadline=parent_deadline)
                token=reservation['token']
                request_ref=save(self.root/'raw',token+'-request.json',request)
                normalized=self.validate(request,NATIVE_TOOLS if actor=='A' else ())
                self.window.model_slot()
                self.window.remaining(reserve=15)
                if self.live:self.window.require(self.window.phase,real=True)
                timing=self.budget.authorize_dispatch(token);dispatched=True
                self.transport.deadline=min(self.maximum_deadline,timing['timeout_seconds'],
                                            self.window.remaining(reserve=15))
                outcome=self.transport.invoke(normalized,cancel=self.cancel)
                outcome_ref=save(self.root/'raw',token+'-outcome.json',outcome)
                status=outcome.get('status')
                response=outcome.get('response') if status=='succeeded' else None
                usage=response.get('usage') if type(response) is dict else outcome.get('usage')
                state='succeeded' if status=='succeeded' else 'unknown' if outcome.get('knowledge')=='unknown' else 'failed'
                settled=self.budget.complete(token,status=state,response_sha256=outcome_ref['sha256'],usage=usage)
                row={'token':token,'actor':actor,'purpose':purpose,
                    'purpose_classification':'opaque_native_call_all_counted' if purpose=='auxiliary' else 'explicit_controller_call',
                    'request':request_ref,'normalized_request_sha256':sha(normalized),
                    'outcome':outcome_ref,'status':state,'late':settled['late'],
                    'dispatched':True,'usage':usage,
                    'provider_capture':{k:v for k,v in outcome.get('provider_capture',{}).items() if k!='body'}}
                self.records.append(row)
                save(self.root/'raw',token+'-link.json',row)
                if state!='succeeded' or settled['late']:
                    self.cancel.set()
                    return {'status':'failed','code':outcome.get('code','CALL_FAILED_OR_LATE'),
                            'knowledge':outcome.get('knowledge','unknown'),'bioduet_call_token':token}
                # Provider HTTP bytes stay in private raw storage, never in native input.
                return {'status':'succeeded','response':response,'bioduet_call_token':token}
            except Exception as exc:
                self.cancel.set()
                # No token means no model attempt or transport dispatch. Retain
                # the refusal separately without changing charged reservations.
                code=str(exc) if str(exc) in ('ATTEMPT_LIMIT','DEADLINE_EXHAUSTED','EXPIRED',
                    'ACTOR','PURPOSE','MODEL','CLOSED','CALL_KIND','REQUEST_HASH') else None
                if token is None:
                    refusal={'sequence':len(self.gate_refusals)+1,'actor':actor if actor in ('A','H') else None,
                        'purpose':purpose if purpose in ('primary','auxiliary','retry') else None,
                        'request_sha256':request_pin,'status':'gate_refused','dispatched':False,
                        'attempt_reserved':False,'failure_code':code,'error_type':type(exc).__name__}
                    refusal_ref=save(self.root/'raw','gate-refusal-%04d.json'%refusal['sequence'],refusal)
                    self.gate_refusals.append({'refusal':refusal_ref,**refusal})
                if token is not None:
                    failure={'status':'failed','code':'CALL_GATE_OR_PROTOCOL','error_type':type(exc).__name__,
                             'knowledge':'unknown' if dispatched else 'not_sent'}
                    try:
                        failed_ref=save(self.root/'raw',token+'-failure.json',failure)
                        self.records.append({'token':token,'actor':actor,'purpose':purpose,
                            'status':'unknown' if dispatched else 'failed','dispatched':dispatched,'failure':failed_ref})
                        self.budget.complete(token,status='unknown' if dispatched else 'failed',
                                             response_sha256=failed_ref['sha256'])
                    except Exception:pass
                return {'status':'failed','code':'CALL_GATE_OR_PROTOCOL','knowledge':'unknown' if dispatched else 'not_sent',
                        'bioduet_call_token':token,'error_type':type(exc).__name__,'failure_code':code}

    def endpoint(self,actor):
        coordinator=self
        class Endpoint:
            deadline=40
            def invoke(self,request,cancel=None):
                return coordinator.invoke(request,actor=actor,purpose='auxiliary' if actor=='A' else 'primary',cancel=cancel)
        return Endpoint()

    def close(self,reason):
        with self.lock:
            if self._closed:return self.closed
            self.cancel.set();cleanup=None
            try:cleanup=self.transport.reconcile_stop()
            except Exception as exc:cleanup={'status':'cleanup_unconfirmed','error_type':type(exc).__name__}
            budget=self.budget.close(reason);self.journal.close()
            self._closed=True
            self.closed={'schema':'bioduet-model-calls/1','records':self.records,
                'budget':budget,'provider_cleanup':cleanup,'gate_refusals':self.gate_refusals,
                'raw_provider_JSON_bodies':'exact safe bodies when provider_capture.available is true',
                'currency_cost':None,'unknown_usage_not_zero':True}
            save(self.root,'calls.json',self.closed)
            return self.closed
