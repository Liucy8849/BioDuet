"""Deterministic regression participant. Never a model or scientist result."""
import json

def scripted_response(request):
    turn=json.loads(request['messages'][-1]['content'])['turn']
    actor,view=turn['actor'],turn['observation']
    sample,design,proof=view['sample'],view['design'],view['public_evidence']
    decision={'kind':'wait','until':turn['tick']+1}
    def action(identifier,payload):
        return {'kind':'action','request':{'action_id':identifier,
            'operation_id':actor+str(turn['tick']),'payload':payload}}
    if actor=='A':
        if not design or design['sample_version']!=sample['version']:
            decision=action('A06',{'sample_version':sample['version'],
                                   'declared_condition':sample['condition']})
        elif proof and proof['condition']==sample['condition']:
            decision={'kind':'finish'}
    else:
        evidence=view.get('private_evidence')
        if evidence and not proof:decision=action('A02',{'evidence_ref':evidence['id']})
        elif proof and sample['condition']!=proof['condition']:
            decision=action('A03',{'expected_version':sample['version'],
                'condition':proof['condition'],'reason':'per released evidence'})
        elif proof:decision={'kind':'finish'}
    response={'model':request['model'],'id':'scripted-regression',
        'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},
        'choices':[{'message':{'content':json.dumps(decision)}}]}
    return {'status':'succeeded','response':response}
