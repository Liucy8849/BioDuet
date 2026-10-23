"""Actual old analysis and counts-only QC production under a fresh finite window."""
import csv
import hashlib
import io
import json
from pathlib import Path
import time

from .bioduet_integrity_v01 import need, pinned, strict, save, sha, digest_file
from .bw01_science_v01 import validate_design
from .bioduet_science_v02 import execute
from .bw01_environment_v01 import verify_installation

QC_METHOD = 'bioduet-library-size-detected-genes/0.1'


def count_metrics(raw, library_ids, gate=None):
    """Pure counts-only calculation. No condition, donor label or truth input."""
    need(type(raw) is bytes and len(raw)<=256*1024**2,'COUNTS_SIZE')
    need(type(library_ids) is list and library_ids and
         all(type(x) is str and x for x in library_ids) and len(set(library_ids))==len(library_ids),'LIBRARY_IDS')
    reader=csv.reader(io.StringIO(raw.decode('utf-8')),delimiter='\t')
    need(next(reader,None)==['gene_id']+library_ids,'COUNTS_HEADER')
    totals=[0]*len(library_ids);detected=[0]*len(library_ids);genes=set()
    for index,row in enumerate(reader):
        if gate is not None and index%1024==0:gate()
        need(len(row)==len(library_ids)+1 and row[0] and row[0] not in genes,'GENE_ROW')
        genes.add(row[0])
        for i,text in enumerate(row[1:]):
            need(text.isascii() and text.isdigit(),'COUNT_INTEGER')
            value=int(text);need(value<=2**53,'COUNT_RANGE')
            totals[i]+=value;detected[i]+=int(value>0)
    need(genes and all(x>0 for x in totals),'EMPTY_COUNTS')
    return {'method_id':QC_METHOD,'gene_count':len(genes),
            'library_ids':library_ids,'library_totals':totals,'detected_genes':detected}


def qc(public_directory, output, window, *, cancel=None, deadline=None):
    window.analysis_slot('counts-only-qc',real=True)
    started=time.monotonic();public=Path(public_directory);out=Path(output)
    dataset=strict((public/'dataset.json').read_bytes())
    raw=pinned(public/'counts.tsv',window.document['counts_sha256'],maximum=256*1024**2)
    ids=[r['library_id'] for r in dataset['samples']]
    def gate():
        window.remaining(reserve=15)
        need(cancel is None or not cancel.is_set(),'QC_CANCELLED')
        need(deadline is None or time.monotonic()<deadline,'QC_TOOL_DEADLINE')
    result=count_metrics(raw,ids,gate=gate)
    out.mkdir(mode=0o700)
    output_ref=save(out,'qc.json',result)
    receipt={'schema':'bioduet-counts-qc-execution/1','status':'succeeded',
        'execution_mode':'actual_compute','method_id':QC_METHOD,
        'counts_sha256':hashlib.sha256(raw).hexdigest(),
        'library_ids_sha256':sha({'library_ids':ids}),
        'method_source_sha256':digest_file(__file__),'parameters':{},
        'condition_label_dependency':False,'result':output_ref,
        'grant_id':window.document['grant_id'],'grant_sha256':window.pin,
        'producer':'trusted_benchmark_prehistory_or_scientific_tool',
        'elapsed_seconds':time.monotonic()-started,
        'scientific_validity':'not_assessed'}
    save(out,'qc-execution.json',receipt)
    return receipt


def local_ref(root, path):
    root=Path(root).resolve(strict=True);path=Path(path)
    need(path.resolve(strict=True)==path and root in path.parents and path.is_file(),'ARTIFACT_PATH')
    return {'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':digest_file(path)}


def load_artifact(root, ref, *, maximum=8*1024**2, decode=True):
    need(type(ref) is dict and set(ref)=={'path','bytes','sha256'},'ARTIFACT_REFERENCE')
    relative=Path(ref['path'])
    need(not relative.is_absolute() and relative.parts and all(x not in ('.','..') for x in relative.parts),'ARTIFACT_RELATIVE')
    need(type(ref['bytes']) is int and (1 if decode else 0)<=ref['bytes']<=maximum,'ARTIFACT_SIZE')
    raw=pinned(Path(root)/relative,ref['sha256'],maximum=maximum,allow_empty=not decode)
    need(len(raw)==ref['bytes'],'ARTIFACT_BYTES')
    return strict(raw) if decode else raw


def produce(spec_path, spec_pin, public_directory, output, window, *, rscript, environment_directory):
    window.require('prehistory',real=True)
    need(window._episode is not None,'CLAIM_WINDOW_BEFORE_PRODUCTION')
    public=Path(public_directory).resolve(strict=True)
    spec=strict(pinned(spec_path,spec_pin,maximum=65536))
    need(spec.get('schema')=='bioduet-bw01-recovery-preparation/1' and spec.get('runnable') is False,'PREPARATION_PROFILE')
    need(spec['counts_sha256']==window.document['counts_sha256'],'COUNTS_GRANT_BINDING')
    dataset=strict((public/'dataset.json').read_bytes())
    need(sha(dataset)==spec['dataset_sha256'],'DATASET_SPEC_BINDING')
    verify_installation(environment_directory,rscript)
    window.remaining(reserve=30)
    out=Path(output);out.mkdir(mode=0o700)
    manifest={'schema':'bioduet-recovery-prehistory/1','spec_sha256':spec_pin,
        'counts_sha256':spec['counts_sha256'],'dataset_sha256':spec['dataset_sha256'],
        'grant_id':window.document['grant_id'],'grant_sha256':window.pin,
        'producer':'trusted_prehistory_setup_not_evaluated_agent',
        'conditions':{},'scientific_validity':'not_assessed','formal_benchmark_score':None}
    save(out,'preparation-private.json',spec)
    manifest['preparation']=local_ref(out,out/'preparation-private.json')
    try:
        for condition in ('H0','H1'):
            directory=out/condition;directory.mkdir(mode=0o700)
            rows=validate_design(dataset,spec['initial_designs'][condition])
            window.analysis_slot('old-analysis-'+condition,real=True)
            wall=min(180,int(window.remaining(reserve=20)))
            need(wall>=1,'ANALYSIS_DEADLINE')
            receipt=execute(public,rows,directory/'analysis',rscript=rscript,edgeR_version='4.4.2',
                library_directory=Path(environment_directory)/'library',sample_version=1,design_version=1,wall_seconds=wall)
            need(receipt['status']=='succeeded' and receipt.get('exit_code')==0,'PREHISTORY_ANALYSIS_FAILED')
            qc_receipt=qc(public,directory/'qc',window)
            record={'analysis':{
                    'execution':local_ref(out,directory/'analysis/execution.json'),
                    'design':local_ref(out,directory/'analysis/design.tsv'),
                    'result':local_ref(out,directory/'analysis/de.tsv')},
                'counts_qc':{'execution':local_ref(out,directory/'qc/qc-execution.json'),
                             'result':local_ref(out,directory/'qc/qc.json')},
                'initial_design':rows,
                'producer':'trusted_prehistory_setup_not_evaluated_agent',
                'R_executions':1,'counts_qc_executions':1,'model_calls':0,
                'wall_seconds':receipt['elapsed_seconds']+qc_receipt['elapsed_seconds']}
            manifest['conditions'][condition]=record
        manifest['status']='succeeded'
    except Exception as exc:
        manifest['status']='failed';manifest['failure_type']=type(exc).__name__
        save(out,'prehistory-failed.json',manifest)
        raise
    save(out,'prehistory.json',manifest)
    return manifest
