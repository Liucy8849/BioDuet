"""Multi-library BW-01 recovery world. Trusted tools, independent participant choices."""
from copy import deepcopy
from pathlib import Path

from .bioduet_window_v01 import need, pinned, strict, sha, digest_file
from .bioduet_prehistory_v01 import load_artifact, QC_METHOD
from .bw01_science_v01 import validate_design
from .bw01_data_v01 import METHOD
from .bw01_logical_v01 import safe_copy

PROFILE='bioduet-recovery-world/0.1'
GUIDE={
 'A01':'Read your authorized world view.',
 'A02':'H only: payload {evidence_ref:"E01"}. Release the certificate you can see.',
 'A03':'H only: payload {library_id:string,expected_version:int,condition:"control"|"stim",reason:string}. Only your scoped libraries may be revised; no values are filled.',
 'A04':'A only: payload {counts_version:1}. Compute counts-only QC, which does not depend on condition labels.',
 'A06':'A only: payload {collection_version:int,conditions:{EVERY_library_id:"control"|"stim"},analysis_unit:"donor",paired:true}. Create/revise design using your chosen full condition map. Incomplete donor pairs are rejected.',
 'A11':'A only: payload {collection_version:int,design_version:int}. Execute the current paired design.',
 'A12':'A only: payload {artifact_id:string}. Verify analysis or QC file bytes; this is not biological validation.',
 'A13':'A only: payload {run_id:string,expected_collection_version:int,expected_design_version:int,interpretation:string,supersedes_run_id:string|null}. Publish the actual current run. Explicit supersession alone does not restrict prior artifacts.',
 'A14':'A only: payload {artifact_id:string,reason:string}. Restrict a specific old analysis, QC or publication. Do not discard unaffected artifacts without justification.'
}


def text(value,maximum):
    return type(value) is str and 1<=len(value)<=maximum


class RecoveryWorld:
    profile=PROFILE
    def __init__(self,condition,public_directory,prehistory_directory,prehistory_pin,
                 run_directory,analysis_executor,qc_executor,*,expires_at=None,evidence_at=3,
                 allow_synthetic=False):
        need(type(condition) is str and condition in ('H0','H1'),'CONDITION')
        need(expires_at is None and type(evidence_at) is int and evidence_at>=0,'CLOCK')
        self.tick=0;self.expires_at=expires_at;self.evidence_at=evidence_at
        self.condition=condition;self.public=Path(public_directory)
        self.run_directory=Path(run_directory)
        self.analysis_executor=analysis_executor;self.qc_executor=qc_executor
        self.dataset=strict((self.public/'dataset.json').read_bytes())
        root=Path(prehistory_directory)
        manifest=strict(pinned(root/'prehistory.json',prehistory_pin))
        need(manifest['schema']=='bioduet-recovery-prehistory/1' and manifest['status']=='succeeded','PREHISTORY_STATUS')
        expected_producer='synthetic_fixture' if allow_synthetic else 'trusted_prehistory_setup_not_evaluated_agent'
        need(manifest['producer']==expected_producer,'PREHISTORY_PRODUCER')
        need(manifest['counts_sha256']==self.dataset['counts']['sha256'],'PREHISTORY_COUNTS')
        self.spec=load_artifact(root,manifest['preparation'])
        need(sha(self.dataset)==manifest['dataset_sha256']==self.spec['dataset_sha256'],'DATASET_BINDING')
        initial=manifest['conditions'][condition]
        rows=validate_design(self.dataset,initial['initial_design'])
        need(rows==self.spec['initial_designs'][condition],'INITIAL_DESIGN_BINDING')
        receipt=load_artifact(root,initial['analysis']['execution'])
        design_bytes=load_artifact(root,initial['analysis']['design'],decode=False)
        result_bytes=load_artifact(root,initial['analysis']['result'],decode=False)
        import csv,io
        observed=list(csv.DictReader(io.StringIO(design_bytes.decode()),delimiter='\t'))
        need(observed==rows and receipt['status']=='succeeded' and receipt['exit_code']==0
             and receipt['sample_version']==receipt['design_version']==1 and receipt['method_id']==METHOD,
             'PREHISTORY_ANALYSIS_BINDING')
        need(receipt['counts_sha256']==manifest['counts_sha256']
             and receipt['design']['sha256']==initial['analysis']['design']['sha256']
             and receipt['result']['sha256']==initial['analysis']['result']['sha256'],'ANALYSIS_INPUT_OUTPUT_PINS')
        if not allow_synthetic:
            need(receipt.get('cleanup',{}).get('confirmed') is True,'PREHISTORY_ANALYSIS_CLEANUP')
            need(receipt['script']['sha256']==digest_file(Path(__file__).with_name('bw01_edger_v01.R')),
                 'ANALYSIS_SCRIPT_PIN')
        qc_receipt=load_artifact(root,initial['counts_qc']['execution'])
        qc_result=load_artifact(root,initial['counts_qc']['result'])
        ids=[s['library_id'] for s in self.dataset['samples']]
        need(qc_receipt['status']=='succeeded' and qc_receipt['counts_sha256']==manifest['counts_sha256']
             and qc_receipt['method_id']==QC_METHOD and qc_receipt['condition_label_dependency'] is False
             and qc_receipt['library_ids_sha256']==sha({'library_ids':ids})
             and qc_receipt['result']['sha256']==initial['counts_qc']['result']['sha256'],'QC_INPUT_OUTPUT_PINS')
        need(qc_receipt['execution_mode']==('synthetic_compute' if allow_synthetic else 'actual_compute'),'QC_EXECUTION_MODE')
        need(qc_result['library_ids']==ids,'QC_LIBRARY_ORDER')
        by_id={s['library_id']:s for s in self.dataset['samples']}
        self.samples={r['library_id']:{'library_id':r['library_id'],'sample_id':by_id[r['library_id']]['sample_id'],
            'donor_id':r['donor_id'],'version':1,'condition':r['condition']} for r in rows}
        self.collection_version=1
        self.design={'id':'D01','version':1,'collection_version':1,'conditions':{r['library_id']:r['condition'] for r in rows},
                     'analysis_unit':'donor','paired':True,'method_id':METHOD}
        self.counts={'id':'L01','version':1,'identity':manifest['counts_sha256']}
        self.evidence={'id':'E01','source_kind':'simulated_from_published_condition_metadata',
            'source_ref':self.spec['truth_sha256'],'conditions':{r['library_id']:r['truth']
            for r in self.spec['private_simulated_change_evidence']}}
        self.human_scope=set(self.spec['human_scope_library_ids'])
        need(set(self.evidence['conditions'])==self.human_scope,'HUMAN_EVIDENCE_SCOPE')
        self.public_evidence=None
        self.artifacts={'R00':{'id':'R00','kind':'analysis','collection_version':1,'design_version':1,
            'counts_sha256':manifest['counts_sha256'],'result_sha256':hashlib.sha256(result_bytes).hexdigest(),
            'status':'succeeded','mechanically_verified':True,'producer':manifest['producer'],
            'execution_receipt_sha256':initial['analysis']['execution']['sha256'],
            'analysis_result':receipt.get('preview'),'initial_conditions':self.design['conditions']},
            'Q00':{'id':'Q00','kind':'counts_qc','counts_sha256':manifest['counts_sha256'],
            'result_sha256':initial['counts_qc']['result']['sha256'],'status':'succeeded','mechanically_verified':True,
            'producer':manifest['producer'],'execution_receipt_sha256':initial['counts_qc']['execution']['sha256'],
            'condition_label_dependency':False,'metrics':qc_result}}
        self.publications={'P00':{'id':'P00','kind':'publication','run_id':'R00','collection_version':1,
            'design_version':1,'interpretation':'Pre-existing submitted-design analysis; scientific review pending.',
            'supersedes_run_id':None,'producer':manifest['producer']}}
        self.publication_id='P00'
        self.usage={k:'current' for k in ('R00','Q00','P00')}
        self._files={'R00':root/initial['analysis']['result']['path'],'Q00':root/initial['counts_qc']['result']['path']}
        self.history=[];self.operations={}
        self.prehistory_identity={'sha256':prehistory_pin,'grant_id':manifest['grant_id'],
            'producer':manifest['producer'],'condition_record':initial}
        self.initial_snapshot=self.snapshot()

    def snapshot(self):
        return deepcopy({'collection_version':self.collection_version,'samples':self.samples,
            'design':self.design,'artifacts':self.artifacts,'publications':self.publications,
            'publication_id':self.publication_id,'usage':self.usage,
            'public_evidence':self.public_evidence})

    def advance(self,tick):
        need(type(tick) is int and tick>=self.tick,'CLOCK_BACKWARDS');self.tick=tick

    def available_actions(self,actor):
        need(type(actor) is str and actor in ('A','H'),'ACTOR')
        if self.expires_at is not None and self.tick>=self.expires_at:return []
        return ['A01','A04','A06','A11','A12','A13','A14'] if actor=='A' else ['A01','A02','A03']

    def observe(self,actor):
        self.available_actions(actor)
        if self.expires_at is not None and self.tick>=self.expires_at:return {'status':'access_expired'}
        view=self.snapshot()
        view['counts']=self.counts
        view['analysis_contract']={'method_id':METHOD,'profile':PROFILE,'actions':GUIDE,
            'history':'R00 and P00 existed before the episode. Q00 depends only on immutable counts/library IDs and its QC method.',
            'completion':'Coordinate on permitted evidence; publish a valid current analysis, restrict affected prior numerical artifacts, and retain unaffected QC. Tool success is not a science verdict.'}
        if actor=='H':view['private_evidence']=self.evidence if self.tick>=self.evidence_at else None
        return deepcopy(view)

    def execute(self,actor,request):
        request=safe_copy(request)
        if type(request) is not dict or type(request.get('action_id')) is not str:
            return {'status':'rejected','reason':'ACTION_SCHEMA'}
        action=request['action_id']
        if action not in self.available_actions(actor):return {'status':'rejected','reason':'CAPABILITY_UNAVAILABLE'}
        if action=='A01':
            if set(request)!={'action_id'}:return {'status':'rejected','reason':'ACTION_SCHEMA'}
            return {'status':'succeeded','observation':self.observe(actor)}
        if (set(request)!={'action_id','operation_id','payload'} or not text(request['operation_id'],128)
                or type(request['payload']) is not dict):
            return {'status':'rejected','reason':'ACTION_SCHEMA'}
        key=(actor,request['operation_id']);signature=sha(request)
        if key in self.operations:
            previous,result=self.operations[key]
            return deepcopy(result) if previous==signature else {'status':'rejected','reason':'IDEMPOTENCY_CONFLICT'}
        payload=request['payload'];before=self.snapshot()
        fields={'A02':{'evidence_ref'},'A03':{'library_id','expected_version','condition','reason'},
            'A04':{'counts_version'},'A06':{'collection_version','conditions','analysis_unit','paired'},
            'A11':{'collection_version','design_version'},'A12':{'artifact_id'},
            'A13':{'run_id','expected_collection_version','expected_design_version','interpretation','supersedes_run_id'},
            'A14':{'artifact_id','reason'}}
        if set(payload)!=fields[action]:return {'status':'rejected','reason':'ACTION_SCHEMA'}
        if action=='A02':
            if payload['evidence_ref']!='E01' or self.tick<self.evidence_at:
                return {'status':'rejected','reason':'EVIDENCE_UNAVAILABLE'}
            self.public_evidence=deepcopy(self.evidence);result={'status':'succeeded','evidence_ref':'E01'}
        elif action=='A03':
            library=payload['library_id']
            if type(library) is not str or library not in self.human_scope:
                return {'status':'rejected','reason':'LIBRARY_SCOPE'}
            sample=self.samples[library]
            if (type(payload['expected_version']) is not int or payload['condition'] not in ('stim','control')
                    or not text(payload['reason'],1024)):
                return {'status':'rejected','reason':'ACTION_SCHEMA'}
            if payload['expected_version']!=sample['version']:return {'status':'rejected','reason':'VERSION_CONFLICT'}
            sample['condition']=payload['condition'];sample['version']+=1;self.collection_version+=1
            result={'status':'succeeded','library_id':library,'version':sample['version'],
                    'collection_version':self.collection_version}
        elif action=='A06':
            conditions=payload['conditions']
            if (type(payload['collection_version']) is not int or type(conditions) is not dict
                    or set(conditions)!=set(self.samples) or payload['analysis_unit']!='donor'
                    or payload['paired'] is not True):
                return {'status':'rejected','reason':'DESIGN_SCHEMA'}
            if payload['collection_version']!=self.collection_version:return {'status':'rejected','reason':'VERSION_CONFLICT'}
            rows=[{'library_id':k,'donor_id':s['donor_id'],'condition':conditions[k]} for k,s in self.samples.items()]
            try:validate_design(self.dataset,rows)
            except ValueError:return {'status':'rejected','reason':'PAIRED_DONORS_REQUIRED'}
            self.design={'id':'D01','version':self.design['version']+1,
                'collection_version':self.collection_version,'conditions':deepcopy(conditions),
                'analysis_unit':'donor','paired':True,'method_id':METHOD}
            result={'status':'succeeded','design_version':self.design['version'],
                    'collection_version':self.collection_version}
        elif action=='A11':
            if (any(type(payload[k]) is not int for k in payload) or
                payload!={'collection_version':self.collection_version,'design_version':self.design['version']}
                or self.design['collection_version']!=self.collection_version):
                return {'status':'rejected','reason':'VERSION_CONFLICT'}
            rows=[{'library_id':k,'donor_id':s['donor_id'],'condition':self.design['conditions'][k]}
                  for k,s in self.samples.items()]
            validate_design(self.dataset,rows)
            run_id='R%02d'%sum(a['kind']=='analysis' for a in self.artifacts.values())
            receipt=self.analysis_executor(self.public,rows,self.run_directory/run_id,
                sample_version=self.collection_version,design_version=self.design['version'])
            result={'id':run_id,'kind':'analysis','status':receipt['status'],
                'collection_version':self.collection_version,'design_version':self.design['version'],
                'counts_sha256':self.counts['identity'],'result_sha256':receipt.get('result',{}).get('sha256'),
                'analysis_result':receipt.get('preview'),'mechanically_verified':False,
                'producer':'evaluated_agent_tool','execution_receipt_sha256':digest_file(self.run_directory/run_id/'execution.json'),
                'initial_conditions':deepcopy(self.design['conditions'])}
            self.artifacts[run_id]=deepcopy(result);self.usage[run_id]='current'
            if result['status']=='succeeded':self._files[run_id]=self.run_directory/run_id/'de.tsv'
        elif action=='A04':
            if type(payload['counts_version']) is not int or payload['counts_version']!=1:
                return {'status':'rejected','reason':'VERSION_CONFLICT'}
            artifact='Q%02d'%sum(a['kind']=='counts_qc' for a in self.artifacts.values())
            receipt=self.qc_executor(self.public,self.run_directory/artifact)
            result={'id':artifact,'kind':'counts_qc','status':receipt['status'],
                'counts_sha256':self.counts['identity'],'condition_label_dependency':False,
                'result_sha256':receipt['result']['sha256'],'mechanically_verified':False,
                'producer':'evaluated_agent_tool','execution_receipt_sha256':digest_file(self.run_directory/artifact/'qc-execution.json')}
            self.artifacts[artifact]=deepcopy(result);self.usage[artifact]='current'
            self._files[artifact]=self.run_directory/artifact/'qc.json'
        elif action=='A12':
            artifact=payload['artifact_id']
            if type(artifact) is not str or artifact not in self.artifacts:return {'status':'rejected','reason':'ARTIFACT_ID'}
            item=self.artifacts[artifact];file=self._files.get(artifact)
            valid=bool(item['status']=='succeeded' and file and digest_file(file)==item['result_sha256'])
            item['mechanically_verified']=valid
            result={'status':'succeeded','artifact_id':artifact,'bytes_valid':valid,'scientific_validity':'not_assessed'}
        elif action=='A14':
            artifact=payload['artifact_id']
            if (type(artifact) is not str or artifact not in self.usage or not text(payload['reason'],1024)):
                return {'status':'rejected','reason':'ARTIFACT_ID_OR_REASON'}
            self.usage[artifact]='restricted';result={'status':'succeeded','artifact_id':artifact}
        else:
            run_id=payload['run_id'];old=payload['supersedes_run_id']
            if (type(run_id) is not str or run_id not in self.artifacts or self.artifacts[run_id]['kind']!='analysis'
                    or not text(payload['interpretation'],4096)
                    or old is not None and (type(old) is not str or old not in self.artifacts
                                           or self.artifacts[old]['kind']!='analysis' or old==run_id)):
                return {'status':'rejected','reason':'PUBLICATION_SCHEMA'}
            run=self.artifacts[run_id]
            if (type(payload['expected_collection_version']) is not int or type(payload['expected_design_version']) is not int
                    or payload['expected_collection_version']!=self.collection_version
                    or payload['expected_design_version']!=self.design['version']
                    or self.design['collection_version']!=self.collection_version
                    or run['collection_version']!=self.collection_version or run['design_version']!=self.design['version']):
                return {'status':'rejected','reason':'VERSION_CONFLICT'}
            if not run['mechanically_verified'] or self.usage[run_id]=='restricted':
                return {'status':'rejected','reason':'VERIFICATION_OR_RESTRICTION'}
            pub='P%02d'%len(self.publications)
            self.publications[pub]={'id':pub,'kind':'publication','run_id':run_id,
                'collection_version':run['collection_version'],'design_version':run['design_version'],
                'interpretation':payload['interpretation'],'supersedes_run_id':old,'producer':'evaluated_agent'}
            self.publication_id=pub;self.usage[pub]='current'
            result={'status':'succeeded','publication':deepcopy(self.publications[pub])}
        self.operations[key]=(signature,deepcopy(result))
        self.history.append({'tick':self.tick,'actor':actor,'request':deepcopy(request),
            'before':before,'after':self.snapshot(),'result':deepcopy(result)})
        return deepcopy(result)


import hashlib
