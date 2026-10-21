"""Pinned bundle inventory and conservative complete/partial evidence readers."""
import base64
from copy import deepcopy
from pathlib import Path
import hashlib

from .bioduet_window_v01 import need,pinned,strict,save,sha,digest_file
from .bioduet_prehistory_v01 import local_ref,load_artifact
from .bioduet_evidence_v01 import load_bundle as load_v02,check_envelope,validate_trace
from .bioduet_recovery_episode_v01 import SCHEMA


def finalize(directory,report):
    root=Path(directory)
    refs=[]
    for f in sorted(root.rglob('*')):
        need(not f.is_symlink(),'BUNDLE_SYMLINK')
        if f.is_file():refs.append(local_ref(root,f))
    need(len(refs)<=1024 and not any(r['path']=='summary.json' for r in refs),'FRESH_BUNDLE')
    report=deepcopy(report);report['bundle_inventory']=refs
    return save(root,'summary.json',report)


def check_model_records(root,report):
    models=report.get('model_calls')
    if models is None:return {'evidence_status':'model_setup_incomplete','attempts':None}
    records=models['records'];budget=models['budget']
    need(type(records) is list,'MODEL_RECORDS')
    tokens=set();known=0;usage_count=0
    for row in records:
        token=row['token'];need(type(token) is str and token not in tokens,'DUPLICATE_MODEL_TOKEN');tokens.add(token)
        need(row['actor'] in ('A','H') and row['status'] in ('succeeded','failed','unknown'),'MODEL_RECORD_SCHEMA')
        need(type(row['dispatched']) is bool,'DISPATCH_FLAG')
        def artifact(ref):
            need(set(ref)=={'name','bytes','sha256'} and '/' not in ref['name'],'MODEL_REFERENCE')
            return load_artifact(Path(root)/'models/raw',
                {'path':ref['name'],'bytes':ref['bytes'],'sha256':ref['sha256']},maximum=4*1024**2)
        if 'outcome' in row:
            request=artifact(row['request']);outcome=artifact(row['outcome'])
            need(request['model']=='deepseek-flash','MODEL_IDENTITY')
            response=outcome.get('response')
            capture=outcome.get('provider_capture',{})
            if capture.get('available') is True:
                need(capture.get('encoding')=='base64' and type(capture.get('body')) is str,'RAW_CAPTURE')
                raw=base64.b64decode(capture['body'],validate=True)
                need(len(raw)==capture['bytes'] and hashlib.sha256(raw).hexdigest()==capture['sha256'],'RAW_CAPTURE_PIN')
                strict(raw)
            if row['status']=='succeeded':
                need(outcome.get('status')=='succeeded' and type(response) is dict,'SUCCESS_RESPONSE')
            usage=row.get('usage')
            if usage is not None:
                need(type(usage) is dict and set(usage)=={'prompt_tokens','completion_tokens','total_tokens'}
                    and all(type(v) is int and v>=0 for v in usage.values())
                    and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'],'TOKEN_USAGE')
                known+=usage['total_tokens'];usage_count+=1
        else:
            need('failure' in row and row['status']!='succeeded','FAILED_CALL_RECORD');artifact(row['failure'])
    need(budget['attempts_consumed']>=len(records) and budget['attempts_consumed']<=budget['attempt_limit']<=30,'BUDGET_ATTEMPTS')
    need(budget['known_total_tokens']==known and budget['usage_reported_attempts']==usage_count,'BUDGET_USAGE_JOIN')
    need(budget['usage_complete']==(usage_count==budget['attempts_consumed']),'USAGE_COMPLETENESS')
    journal=Path(root)/'models/budget.jsonl'
    previous='0'*64;attempts={};dispatched=set();settled=set();rows=journal.read_bytes().splitlines()
    for n,raw in enumerate(rows):
        entry=strict(raw);body={k:v for k,v in entry.items() if k!='sha256'}
        need(entry['sequence']==n and entry['previous_sha256']==previous and entry['sha256']==sha(body),'BUDGET_JOURNAL_CHAIN')
        previous=entry['sha256'];fields=entry['fields']
        if entry['kind']=='reserved':
            token=fields['token'];need(token not in attempts,'BUDGET_RESERVE_DUPLICATE');attempts[token]=fields
        if entry['kind']=='dispatch_authorized':
            token=fields['token'];need(token in attempts and token not in dispatched,'BUDGET_DISPATCH_JOIN');dispatched.add(token)
        if entry['kind']=='completed':
            token=fields['token'];need(token in attempts and token not in settled,'BUDGET_SETTLEMENT_JOIN');settled.add(token)
    need(previous==budget['journal_tail_sha256'] and len(attempts)==budget['attempts_consumed'],'JOURNAL_BUDGET_JOIN')
    for row in records:
        token=row['token'];need(token in attempts and row['actor']==attempts[token]['actor']
            and row['dispatched']==(token in dispatched),'CALL_JOURNAL_JOIN')
    need(rows and strict(rows[-1])['kind']=='closed' and budget['closed'] is True,'BUDGET_NOT_CLOSED')
    return {'evidence_status':'complete' if len(records)==len(attempts) else 'partial_retained',
            'attempts':len(attempts),'known_total_tokens':known,'usage_complete':budget['usage_complete']}


def recovery_check(directory,report):
    need(report.get('scientific_validity')=='not_assessed' and report.get('formal_benchmark_score') is None,'CLAIM_BOUNDARY')
    need(report['condition'] in ('H0','H1'),'CONDITION')
    cursor=report['initial_state'];last=-1
    records=report['session_records'];transcript=report['transcript']
    for n,row in enumerate(records):
        need(type(row['seq']) is int and row['seq']==n and row['actor'] in ('A','H'),'RECORD_SEQUENCE')
        need(type(row['tick']) is int and row['tick']>last,'RECORD_CLOCK');last=row['tick']
    submissions={}
    for entry in transcript:
        packet=entry['packet']
        need(sha(packet)==entry['packet_sha256'] and packet['actor']==entry['actor']
             and packet['episode_id']==report['episode_id'],'PACKET_BINDING')
        if 'submission' in entry:
            row=entry['submission'];index=row['seq']
            need(type(index) is int and 0<=index<len(records) and index not in submissions
                 and sha(row)==sha(records[index]),'SUBMISSION_JOIN')
            need(packet['turn_token']==report['episode_id']+':'+row['actor']+':'+str(index),'TURN_TOKEN')
            if 'accepted_decision' in entry and 'decision' in row:
                need(sha(entry['accepted_decision'])==sha(row['decision']),'DECISION_PRESERVATION')
            submissions[index]=entry
        else:need('failure_type' in entry or report['failure'] or report['pending_turn'] is not None,'UNEXPLAINED_UNSUBMITTED_TURN')
    seen=set()
    for event in report['world_history']:
        need(sha(event['before'])==sha(cursor),'WORLD_STATE_CHAIN')
        matches=[r for r in records if r['tick']==event['tick'] and r['actor']==event['actor']
            and r.get('decision',{}).get('kind')=='action'
            and sha(r['decision']['request'])==sha(event['request']) and sha(r['result'])==sha(event['result'])]
        need(len(matches)==1 and event['tick'] not in seen,'WORLD_RECORD_JOIN')
        seen.add(event['tick']);cursor=event['after']
    need(sha(cursor)==sha(report['final_state']),'WORLD_FINAL')
    for r in records:
        d=r.get('decision',{});result=r['result']
        if (d.get('kind')=='action' and d['request'].get('action_id')!='A01'
            and result.get('status') in ('succeeded','failed')):
            # Repeated operation IDs may return the original result without a second mutation.
            if r['tick'] not in seen:
                need(any(h['tick']<r['tick'] and h['actor']==r['actor']
                    and sha(h['request'])==sha(d['request']) and sha(h['result'])==sha(result)
                    for h in report['world_history']),'MISSING_WORLD_MUTATION')
    model_rows={r['token']:r for r in (report.get('model_calls') or {}).get('records',[])}
    for entry in transcript:
        if 'accepted_decision' not in entry:continue
        call=model_rows.get(entry.get('model_call_token'))
        need(call is not None and 'outcome' in call and call['actor']==entry['actor'],'ROLE_MODEL_LINK')
        ref=call['outcome']
        outcome=load_artifact(Path(directory)/'models/raw',
            {'path':ref['name'],'bytes':ref['bytes'],'sha256':ref['sha256']},maximum=4*1024**2)
        response=outcome['response'];need(sha(response)==entry['response_sha256'],'ROLE_RESPONSE_LINK')
        if 'submission' in entry:
            envelope=deepcopy(entry);envelope['raw_model_response']=response
            check_envelope(envelope)
    models=check_model_records(directory,report)
    return {'schema':'bioduet-recovery-bundle-check/1','turns':len(records),'world_events':len(seen),
        'evidence_status':'partial_retained' if report['failure'] or report['pending_turn'] else 'complete_recorded',
        'model_evidence':models,'numeric_execution_verified':False,'scientific_validity':'not_assessed','formal_score':None}


def legacy_development(directory,summary):
    """Read v03/v04 and explicit failed bundles without inventing missing artifacts."""
    root=Path(directory);objects={'summary':summary};missing=[];refs={}
    for key,name in (('episode','episode-private.json'),('oracle','oracle.json'),('provider_ledger','provider-ledger.json')):
        ref=summary.get(key)
        if ref is None:missing.append(key);continue
        need(type(ref) is dict and set(ref)=={'name','bytes','sha256'} and ref['name']==name,'LEGACY_REFERENCE')
        refs[key]=ref
        objects[key]=load_artifact(root,{'path':name,'bytes':ref['bytes'],'sha256':ref['sha256']},maximum=16*1024**2)
    episode=objects.get('episode');faults=[]
    if episode:
        need(episode['condition']==summary['condition'],'LEGACY_CONDITION')
        records=episode['session_records'];submitted=[]
        for n,row in enumerate(records):need(type(row['seq']) is int and row['seq']==n,'LEGACY_SEQUENCE')
        for entry in episode['transcript']:
            need(sha(entry['packet'])==entry['packet_sha256'],'LEGACY_PACKET_PIN')
            if 'submission' not in entry:
                need('provider_failure' in entry or 'environment_error' in entry,'LEGACY_PARTIAL_REASON');continue
            index=entry['submission']['seq']
            need(type(index) is int and 0<=index<len(records) and index not in submitted
                 and sha(entry['submission'])==sha(records[index]),'LEGACY_SUBMISSION')
            submitted.append(index)
            if 'raw_model_response' in entry:
                fault=check_envelope(entry)
                if fault:faults.append(fault)
        terminal=episode.get('terminal')
    else:terminal=None
    consistency=None
    if episode and not summary.get('failure'):
        # Schema alias exists only in the validation view. Original pinned bytes
        # and source profile are retained in objects, never rewritten or relabeled.
        view=deepcopy(summary);view['schema']='bw01-scientific-development-run/2'
        consistency=validate_trace(view,episode)
    return {'private_bundle':objects,'check':{'schema':'bioduet-development-bundle-check/1',
        'complete_trace_consistency':consistency,
        'summary_profile':summary['schema'],'missing_artifacts_retained':missing,'terminal':terminal,
        'evidence_status':'partial_retained' if missing or summary.get('failure') else 'recorded',
        'retained_protocol_faults':faults,'pinned_files':refs,
        'numeric_execution_verified':False,'scientific_validity':'not_assessed','formal_score':None}}


def load_bundle(directory,summary_pin,condition):
    root=Path(directory);summary=strict(pinned(root/'summary.json',summary_pin,maximum=16*1024**2))
    need(type(condition) is str and condition in ('H0','H1') and summary.get('condition')==condition,'CONDITION')
    profile=summary.get('schema')
    if profile=='bw01-scientific-development-run/2' and not summary.get('failure'):
        return load_v02(directory,summary_pin,condition)
    if profile in ('bw01-scientific-development-run/2','bw01-scientific-development-run/3','bw01-scientific-development-run/4'):
        need(summary.get('scientific_validity')=='not_assessed' and summary.get('formal_benchmark_score') is None,'CLAIM_BOUNDARY')
        return legacy_development(directory,summary)
    need(profile==SCHEMA,'BUNDLE_PROFILE')
    refs=summary['bundle_inventory'];need(type(refs) is list and len(refs)<=1024,'BUNDLE_INVENTORY')
    paths=set()
    for ref in refs:
        need(ref['path'] not in paths and ref['path']!='summary.json','BUNDLE_DUPLICATE_PATH');paths.add(ref['path'])
        load_artifact(root,ref,maximum=16*1024**2,decode=False)
    actual={str(f.relative_to(root)) for f in root.rglob('*') if f.is_file() and f!=root/'summary.json'}
    need(paths==actual,'BUNDLE_UNDECLARED_OR_MISSING_FILE')
    return {'private_bundle':{'summary':summary},'check':recovery_check(root,summary)}
