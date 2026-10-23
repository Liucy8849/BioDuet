"""Logical shared world with explicit scientific tools; no hidden oracle calls."""
from copy import deepcopy
import json
from pathlib import Path
from labweave_eval.bw01_logical_v01 import Bw01EngineeringWorld,safe_copy
from labweave_eval.bw01_science_v01 import execute
from labweave_eval.bw01_data_v01 import METHOD

PROFILE='bw01-interaction-science-development/0.1'
ACTION_GUIDE={
 'A06':'Create/revise design: payload sample_version:int, declared_condition:control|stim, analysis_unit:donor|cell, paired:bool. This fixed method supports paired donor pseudobulks.',
 'A11':'Run current design: payload sample_version:int, design_version:int. No automatic label correction. Returns an actual execution receipt or a failed analysis.',
 'A12':'Request mechanical verification: payload run_id:string. Checks output bytes and execution status, not biological truth.',
 'A13':'Publish candidate: payload run_id:string, expected_sample_version:int, expected_design_version:int, interpretation:nonempty string. Success is not a science verdict.',
 'A14':'Restrict use of a prior candidate: payload run_id:string, reason:nonempty string.'
}
class Bw01ScienceWorld(Bw01EngineeringWorld):
    profile=PROFILE
    def __init__(self,condition,public_directory,run_directory,executor,*,expires_at=80):
        super().__init__(condition,expires_at=expires_at)
        self.public_directory=Path(public_directory);self.run_directory=Path(run_directory)
        self.dataset=json.loads((self.public_directory/'dataset.json').read_text())
        self.counts={'id':'L01','version':1,'identity':self.dataset['counts']['sha256'],
                     'source_kind':self.dataset['source_kind']}
        self.executor=executor;self.runs={};self.verifications={};self.publication=None
        self.science_operations={}
    def available_actions(self,actor):
        actions=super().available_actions(actor)
        return actions+(['A11','A12','A13','A14'] if actor=='A' and actions else [])
    def observe(self,actor):
        view=super().observe(actor)
        if view.get('status')=='access_expired':return view
        libraries=deepcopy(self.dataset['samples'])
        for item in libraries:
            if item['sample_id']=='S01':item['condition']=self.sample['condition']
        view.update(libraries=libraries,analysis_contract={'method_id':METHOD,'analysis_unit':'donor',
            'cell_type':self.dataset['cell_type'],'donor_count':self.dataset['donor_count'],
            'source_kind':self.dataset['source_kind'],'actions':ACTION_GUIDE,
            'publication_requirement':'Interpret actual analysis_result: donor replication, contrast, tested/significant genes, representative effects and method limits. Never invent biology from file hashes.'},
            analysis_runs=[{k:v for k,v in run.items() if k!='directory'} for run in self.runs.values()],
            publication=self.publication)
        return view
    def execute(self,actor,request):
        request=safe_copy(request)
        action=request.get('action_id');payload=request.get('payload')
        if action=='A06':
            required={'sample_version','declared_condition','analysis_unit','paired'}
            if type(payload) is not dict or set(payload)!=required or payload['analysis_unit'] not in ('donor','cell') or type(payload['paired']) is not bool:
                return {'status':'rejected','reason':'SCIENCE_DESIGN_SCHEMA'}
            # Retain the full request identity including scientific decisions.
        if action not in ('A06','A11','A12','A13','A14'):return super().execute(actor,request)
        if action not in self.available_actions(actor):return {'status':'rejected','reason':'CAPABILITY_UNAVAILABLE'}
        if set(request)!={'action_id','operation_id','payload'} or type(payload) is not dict or type(request['operation_id']) is not str or not 1<=len(request['operation_id'])<=128:
            return {'status':'rejected','reason':'ACTION_SCHEMA'}
        key=(actor,request['operation_id']);signature=json.dumps(request,sort_keys=True)
        if key in self.science_operations:
            old,result=self.science_operations[key]
            return deepcopy(result) if old==signature else {'status':'rejected','reason':'IDEMPOTENCY_CONFLICT'}
        if key in self.operations:return {'status':'rejected','reason':'IDEMPOTENCY_CONFLICT'}
        before=deepcopy({'sample':self.sample,'design':self.design,'publication':self.publication})
        if action=='A06':
            base=deepcopy(request);base['payload']={k:payload[k] for k in ('sample_version','declared_condition')}
            result=super().execute(actor,base)
            if result.get('status')=='succeeded':
                self.design.update(analysis_unit=payload['analysis_unit'],paired=payload['paired'],method_id=METHOD)
                self.history[-1]['after']['design']=deepcopy(self.design)
                self.science_operations[key]=(signature,deepcopy(result))
            return result
        if action=='A11':
            if set(payload)!={'sample_version','design_version'} or any(type(payload[k]) is not int for k in payload):
                return {'status':'rejected','reason':'ACTION_SCHEMA'}
            if not self.design or payload!={'sample_version':self.sample['version'],'design_version':self.design['version']}:
                return {'status':'rejected','reason':'VERSION_CONFLICT'}
            if self.design.get('analysis_unit')!='donor' or self.design.get('paired') is not True:
                return {'status':'rejected','reason':'METHOD_REQUIRES_PAIRED_DONORS'}
            rows=[{k:s[k] for k in ('library_id','donor_id','condition')} for s in self.dataset['samples']]
            for s,row in zip(self.dataset['samples'],rows):
                if s['sample_id']=='S01':row['condition']=self.design['declared_condition']
            run_id='R%02d'%(len(self.runs)+1)
            try:
                receipt=self.executor(self.public_directory,rows,self.run_directory/run_id,
                    sample_version=self.design['sample_version'],design_version=self.design['version'])
            except ValueError:
                result={'status':'rejected','reason':'ANALYSIS_INPUT_INVALID'}
                self.science_operations[key]=(signature,result);return deepcopy(result)
            run={'run_id':run_id,'sample_version':self.design['sample_version'],'design_version':self.design['version'],
                 'status':receipt['status'],'restricted':False,'result':receipt.get('result'),'analysis_result':receipt.get('preview'),
                 'directory':str(self.run_directory/run_id),'scientific_validity':'not_assessed'}
            self.runs[run_id]=run
            result={k:v for k,v in run.items() if k!='directory'}
        else:
            required={'A12':{'run_id'},'A13':{'run_id','expected_sample_version','expected_design_version','interpretation'},
                      'A14':{'run_id','reason'}}[action]
            if set(payload)!=required or type(payload.get('run_id')) is not str or payload['run_id'] not in self.runs:
                return {'status':'rejected','reason':'ACTION_SCHEMA'}
            run=self.runs[payload['run_id']]
            if action=='A12':
                # Explicitly mechanical. Oracle is never reachable from this tool.
                from labweave_eval.bw01_data_v01 import sha256
                path=Path(run['directory'])/'de.tsv'
                valid=bool(run['status']=='succeeded' and path.is_file() and sha256(path)==run['result']['sha256'])
                self.verifications[run['run_id']]={'bytes_valid':valid,'scientific_validity':'not_assessed'}
                run['mechanically_verified']=valid
                result={'status':'succeeded',**self.verifications[run['run_id']]}
            elif action=='A14':
                if type(payload['reason']) is not str or not 1<=len(payload['reason'])<=1024:return {'status':'rejected','reason':'ACTION_SCHEMA'}
                run['restricted']=True
                if self.publication and self.publication['run_id']==run['run_id']:self.publication['restricted']=True
                result={'status':'succeeded','run_id':run['run_id'],'restricted':True}
            else:
                if type(payload['expected_sample_version']) is not int or type(payload['expected_design_version']) is not int:
                    return {'status':'rejected','reason':'ACTION_SCHEMA'}
                if not self.design or payload['expected_sample_version']!=self.sample['version'] or payload['expected_design_version']!=self.design['version']:
                    return {'status':'rejected','reason':'VERSION_CONFLICT'}
                if type(payload['interpretation']) is not str or not 1<=len(payload['interpretation'])<=4096:
                    return {'status':'rejected','reason':'ACTION_SCHEMA'}
                if run['restricted'] or not self.verifications.get(run['run_id'],{}).get('bytes_valid'):
                    return {'status':'rejected','reason':'VERIFICATION_REQUIRED'}
                self.publication={'run_id':run['run_id'],'sample_version':self.sample['version'],
                    'design_version':self.design['version'],'interpretation':payload['interpretation'],'restricted':False,
                    'scientific_validity':'not_assessed'}
                result={'status':'succeeded','publication':deepcopy(self.publication)}
        self.science_operations[key]=(signature,deepcopy(result))
        self.history.append({'tick':self.tick,'actor':actor,'action_id':action,'operation_id':request['operation_id'],
            'before':before,'after':deepcopy({'sample':self.sample,'design':self.design,'publication':self.publication}),
            'result':deepcopy(result)})
        return result
