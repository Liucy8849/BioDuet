"""Trusted engineering controller. No live claim without external transport receipts."""
import hashlib,json
from labweave_eval.bw01_logical_v01 import LogicalSession,Bw01EngineeringWorld
PROFILE='bw01-participant-engineering/0.1'
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def run_episode(condition,roles,invoke,max_turns=14,*,world=None):
    if set(roles)!={'A','H'}: raise ValueError('ROLES')
    world=Bw01EngineeringWorld(condition) if world is None else world
    session=LogicalSession(world,max_turns=max_turns)
    previous={'A':None,'H':None};transcript=[]
    while True:
        packet=session.next_turn()
        if packet is None: break
        actor=packet['actor'];entry={'actor':actor,'packet':packet,'packet_sha256':digest(packet)}
        transcript.append(entry)
        try:
            prepared=roles[actor].prepare(packet,previous[actor])
            if prepared['turn_token']!=packet['turn_token']: raise ValueError('TOKEN')
            entry['request_sha256']=digest(prepared['request'])
            result=invoke(prepared['request'])
            if result.get('status')!='succeeded':
                entry['provider_failure']={k:result[k] for k in ('status','code','knowledge','http_status') if k in result}
                session.terminal='provider_failure';session.pending=None;break
            response=result['response'];entry['response_sha256']=digest(response)
            entry['provider']={k:response[k] for k in ('id','model','usage') if k in response}
            accepted=roles[actor].accept(response)
            if accepted['turn_token']!=packet['turn_token']: raise ValueError('TOKEN')
            entry['parse_error']=accepted['parse_error']
            previous[actor]=session.submit(accepted['turn_token'],accepted['decision'])
            entry['submission']=previous[actor]
        except Exception as exc:
            entry['environment_error']=type(exc).__name__
            session.terminal='environment_error';session.pending=None;break
    proof,design,sample=world.public_evidence,world.design,world.sample
    views=[e['packet']['observation'] for e in transcript if e['actor']=='A' and 'submission' in e]
    observed=bool(views and views[-1].get('public_evidence')==proof and views[-1].get('sample')==sample)
    goal=bool(session.terminal=='participants_finished' and proof and design and observed
              and sample['condition']==proof['condition']==world.private_evidence['condition']
              and design['declared_condition']==sample['condition'] and design['sample_version']==sample['version']
              and any(e['actor']=='H' and e['action_id']=='A02' for e in world.history)
              and any(e['actor']=='A' and e['action_id']=='A06' for e in world.history))
    return {'profile':PROFILE,'condition':condition,'terminal':session.terminal,
            'engineering_metadata_design_goal':goal,'world_source':getattr(world,'dataset',{}).get('source_kind','synthetic'),
            'scientific_publication_present':bool(getattr(world,'publication',None)),
            'full_bw01_closed_loop':False,'scientific_validity':'not_assessed',
            'formal_benchmark_score':None,'strict_goal_completion':None,
            'transcript':transcript,'world_history':world.history,
            'final_state':world.observe('A'),'session_records':session.records}
