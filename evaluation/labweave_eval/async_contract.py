"""Engineering async profile, not the frozen cross-system machine schema."""
import re
from .contract import exact, ref, reject_if, text, uuid

FAILURE_CODES = ('SYNTHETIC_EXECUTION_ERROR', 'SYNTHETIC_INPUT_ERROR')

def validate_async_request(req, base):
    exact(req, base | {'target','operation_id','idempotency_key','expected_versions','input_refs','evidence_refs','provenance'})
    ref(req['target'])
    reject_if(req['target']['object_type'] != 'run')
    uuid(req['operation_id'])
    key=req['idempotency_key']
    reject_if(not isinstance(key,str) or not 1 <= len(key) <= 191 or key != key.strip() or any(ord(c)<32 or ord(c)>126 for c in key))
    for name in ('expected_versions','input_refs','evidence_refs'):
        reject_if(not isinstance(req[name],list))
        for item in req[name]:
            ref(item,True)
        reject_if(len({(x['object_type'],x['object_id']) for x in req[name]}) != len(req[name]))
    exact(req['provenance'],('source_kind','source_ref'))
    reject_if(req['provenance']['source_kind'] not in ('synthetic','simulated_replay'))
    text(req['provenance']['source_ref'])
    payload=req['payload']
    if req['action']['id']=='A11':
        reject_if(req['expected_versions'] != [] or req['evidence_refs'] != [] or not req['input_refs'])
        reject_if(any(r['object_type'] != 'artifact' for r in req['input_refs']))
        exact(payload,('template_ref','environment_ref','parameters','resources'))
        text(payload['template_ref'])
        text(payload['environment_ref'])
        exact(payload['parameters'],())
        exact(payload['resources'],('cpu_threads','memory_mib','timeout_seconds'))
        for name,limit in (('cpu_threads',4),('memory_mib',16384),('timeout_seconds',30)):
            value=payload['resources'][name]
            reject_if(type(value) is not int or not 1 <= value <= limit)
        return
    reject_if(req['input_refs'] != [] or req['evidence_refs'] != [] or len(req['expected_versions']) != 1)
    expected=req['expected_versions'][0]
    reject_if(expected['object_type'] != 'run' or expected['object_id'] != req['target']['object_id'])
    exact(payload,('run_operation_id','attempt_id','receipt_id','execution_status','output_artifacts','failure_code'))
    for name in ('run_operation_id','attempt_id','receipt_id'):
        uuid(payload[name])
    reject_if(payload['execution_status'] not in ('succeeded','failed'))
    reject_if(not isinstance(payload['output_artifacts'],list))
    for artifact in payload['output_artifacts']:
        exact(artifact,('object_type','object_id','revision','sha256','size_bytes'))
        ref({k:artifact[k] for k in ('object_type','object_id','revision')},True)
        reject_if(artifact['object_type'] != 'artifact')
        reject_if(not isinstance(artifact['sha256'],str) or re.fullmatch('[0-9a-f]{64}',artifact['sha256']) is None)
        reject_if(type(artifact['size_bytes']) is not int or artifact['size_bytes'] < 0)
    reject_if(len({(a['object_id'],a['revision']) for a in payload['output_artifacts']}) != len(payload['output_artifacts']))
    if payload['execution_status']=='succeeded':
        reject_if(not payload['output_artifacts'] or payload['failure_code'] is not None)
    else:
        reject_if(payload['output_artifacts'] != [] or payload['failure_code'] not in FAILURE_CODES)
