"""Recovery episode controller. Independent role decisions; partial failures survive."""
from copy import deepcopy
from pathlib import Path
import time

from .bw01_logical_v01 import LogicalSession
from .bioduet_native_bridge_v01 import NativeTurnBridge
from .bioduet_integrity_v01 import need, sha, save

SCHEMA='bioduet-recovery-episode/1'


class ToolClock:
    """Single logical tool transaction; nested H/model/science share its deadline."""
    def __init__(self,window,cancel,clock=time.monotonic):
        self.window=window;self.cancel=cancel;self.clock=clock;self.deadline=None
    def begin(self):
        need(self.deadline is None,'TOOL_ALREADY_ACTIVE')
        self.deadline=self.clock()+min(270,self.window.remaining(reserve=15))
    def end(self):self.deadline=None
    def remaining(self,cap=180):
        need(not self.cancel.is_set(),'CANCELLED')
        left=min(cap,self.window.remaining(reserve=15))
        if self.deadline is not None:left=min(left,self.deadline-self.clock())
        need(left>0,'TOOL_DEADLINE')
        return left


class RoleStep:
    def __init__(self,roles,models,transcript,tool_clock):
        self.roles=roles;self.models=models;self.transcript=transcript
        self.previous={'A':None,'H':None};self.clock=tool_clock
    def __call__(self,packet):
        actor=packet['actor'];self.clock.remaining()
        row={'actor':actor,'packet':deepcopy(packet),'packet_sha256':sha(packet)}
        self.transcript.append(row)
        try:
            prepared=self.roles[actor].prepare(packet,self.previous[actor])
            need(prepared['turn_token']==packet['turn_token'],'PREPARE_TOKEN')
            row['participant_context']=deepcopy(prepared.get('context_window'))
            result=self.models.invoke(prepared['request'],actor=actor,
                parent_deadline=self.clock.deadline)
            row['model_call_token']=result.get('bioduet_call_token')
            if result.get('status')!='succeeded':
                row['provider_failure']=deepcopy(result)
                raise RuntimeError('PROVIDER_FAILURE')
            response=result['response'];row['response_sha256']=sha(response)
            accepted=self.roles[actor].accept(response)
            need(accepted['turn_token']==packet['turn_token'],'ACCEPT_TOKEN')
            row['parse_error']=accepted['parse_error']
            row['protocol_adapter']=accepted.get('protocol_adapter')
            row['accepted_decision']=deepcopy(accepted['decision'])
            return accepted['decision']
        except Exception as exc:
            row['failure_type']=type(exc).__name__
            raise
    def submitted(self,record):
        self.previous[record['actor']]=deepcopy(record)
        for row in reversed(self.transcript):
            if row['actor']==record['actor'] and 'submission' not in row:
                row['submission']=deepcopy(record);break


class RecordedBridge(NativeTurnBridge):
    def __init__(self,session,step,transcript):
        super().__init__(session,step);self.step=step;self.transcript=transcript
    def _advance(self):
        # Keep the frozen parent's scheduling/error semantics. Record each H
        # submission immediately, before another H prepare can use previous.
        while True:
            packet=self.session.next_turn()
            if packet is None:
                self.packet=None;self.closed=True;return None
            if packet['actor']=='A':
                self.packet=packet
                public=deepcopy(packet);del public['turn_token'];return public
            if packet['actor']!='H':raise ValueError('UNSUPPORTED_PARTICIPANT')
            try:
                decision=self.human_step(deepcopy(packet))
            except Exception as exc:
                self.environment_failure={'code':'HUMAN_STEP_FAILED','actor':'H'}
                self.native_events.append({'kind':'human_step_failed',
                    'error_type':type(exc).__name__,'seq':self.session.seq})
                self.session.records.append({'seq':self.session.seq,'tick':self.session.tick,
                    'actor':'H','stage':'human_step',
                    'result':{'status':'environment_error','reason':'HUMAN_STEP_FAILED'}})
                self.session.seq+=1;self.session.pending=None
                self.session.terminal='environment_error'
                self.packet=None;self.closed=True;return None
            record=self.session.submit(packet['turn_token'],decision)
            self.step.submitted(record)
    def exchange(self,decision):
        if not self.started or self.closed or self.packet is None:raise ValueError('NO_AGENT_TURN')
        packet=deepcopy(self.packet)
        row={'actor':'A','packet':packet,'packet_sha256':sha(packet),
             'native_tool_decision':deepcopy(decision)}
        self.transcript.append(row)
        before=len(self.session.records)
        result=super().exchange(decision)
        records=self.session.records[before:]
        if records and records[0].get('actor')=='A':row['submission']=deepcopy(records[0])
        return result


def run_reference_session(session,step,tool_clock):
    while True:
        packet=session.next_turn()
        if packet is None:break
        try:
            tool_clock.begin()
            decision=step(packet)
            record=session.submit(packet['turn_token'],decision)
            step.submitted(record)
        except Exception:
            # Preserve the issued, unsubmitted packet. No invented participant action.
            session.terminal='provider_failure' if step.models.cancel.is_set() else 'environment_error'
            break
        finally:tool_clock.end()


def episode_document(session,world,transcript,*,condition,mode,models,cleanup,failure,native=None):
    faults={a:sum(bool(r.get('parse_error')) for r in transcript if r['actor']==a) for a in ('A','H')}
    return {'schema':SCHEMA,'condition':condition,'mode':mode,
        'behavior_source':'interactive_model' if mode in ('reference','native-live') and world.prehistory_identity['producer']!='synthetic_fixture' else 'synthetic_qualification',
        'time_model':'logical_time','terminal':session.terminal,'failure':failure,
        'episode_id':session.episode_id,'transcript':deepcopy(transcript),
        'session_records':deepcopy(session.records),'pending_turn':deepcopy(session.pending),
        'initial_state':deepcopy(world.initial_snapshot),'world_history':deepcopy(world.history),
        'final_state':world.snapshot(),'prehistory':deepcopy(world.prehistory_identity),
        'world_port_audit':{'broker':world.broker_audit,'forwarded':world.port_audit},
        'model_calls':models,'cleanup':cleanup,'native':native,
        'simulator_protocol_faults':faults,'protocol_policy':'simulator_protocol_faults_separate',
        'scientific_validity':'not_assessed','formal_benchmark_score':None,
        'strict_goal_completion':None}
