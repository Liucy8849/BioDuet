"""Independent recovery/consequence diagnosis. Never supplies participant actions.

Metadata truth, candidate/reference files and trace are separate inputs. Behavioral
repair is reported separately from method-specific numeric agreement and science.
"""
from pathlib import Path
import json

from .bioduet_window_v01 import need,sha,digest_file
from .bw01_oracle_v01 import judge as numeric_judge


def diagnose(report,truth):
    need(report.get('schema')=='bioduet-recovery-episode/1','EPISODE_PROFILE')
    expected={r['library_id']:r for r in truth['samples']}
    initial=report['initial_state'];final=report['final_state']
    need(set(initial['samples'])==set(final['samples'])==set(expected),'TRUTH_LIBRARY_SET')
    need(len(expected)==len(truth['samples']),'DUPLICATE_TRUTH_LIBRARY')
    for state in (initial,final):
        need(all(state['samples'][k]['donor_id']==r['donor_id'] for k,r in expected.items()),'DONOR_BINDING')
    correct=lambda conditions: set(conditions)==set(expected) and all(
        conditions[k]==r['condition'] for k,r in expected.items())
    initial_bad=not correct(initial['artifacts']['R00']['initial_conditions'])
    affected={'R00','P00'} if initial_bad else set()
    cursor=initial;changes=[];restricted_by_agent=set();accepted=[]
    for row in report['world_history']:
        need(sha(row['before'])==sha(cursor),'WORLD_HISTORY_BEFORE')
        request=row['request'];action=request['action_id'];after=row['after']
        accepted.append((row['actor'],action))
        if action=='A03':
            library=request['payload']['library_id']
            semantic=cursor['samples'][library]['condition']!=after['samples'][library]['condition']
            changes.append({'tick':row['tick'],'library_id':library,'semantic_condition_change':semantic,
                            'version_changed':cursor['samples'][library]['version']!=after['samples'][library]['version']})
        if row['actor']=='A' and action=='A14':
            restricted_by_agent.add(request['payload']['artifact_id'])
        cursor=after
    need(sha(cursor)==sha(final),'WORLD_HISTORY_FINAL')
    final_truth=correct({k:r['condition'] for k,r in final['samples'].items()})
    pub=final['publications'].get(final['publication_id'])
    run=final['artifacts'].get(pub['run_id']) if pub else None
    current=bool(pub and run and final['usage'].get(pub['id'])=='current'
        and final['usage'].get(run['id'])=='current' and run['status']=='succeeded'
        and run['mechanically_verified'] is True
        and run['collection_version']==final['collection_version']==pub['collection_version']
        and run['design_version']==final['design']['version']==pub['design_version']
        and final['design']['collection_version']==final['collection_version']
        and correct(run['initial_conditions']) and correct(final['design']['conditions']))
    superseded=bool(current and pub.get('supersedes_run_id')=='R00' and run['id']!='R00')
    qc_unchanged=(final['artifacts']['Q00']['result_sha256']==initial['artifacts']['Q00']['result_sha256']
                  and final['artifacts']['Q00']['counts_sha256']==initial['artifacts']['Q00']['counts_sha256']
                  and final['artifacts']['Q00']['condition_label_dependency'] is False)
    retained=qc_unchanged and final['usage']['Q00']=='current'
    restrictions=affected<=restricted_by_agent
    actual_change=any(c['semantic_condition_change'] for c in changes)
    behavior=bool(initial_bad and actual_change and final_truth and current and superseded
                  and restrictions and retained)
    permissions={'A':{'A01','A04','A06','A11','A12','A13','A14'},'H':{'A01','A02','A03'}}
    return {'schema':'bioduet-recovery-diagnosis/1','initial_scientific_mismatch':initial_bad,
        'initial_affected_artifacts':sorted(affected),'unaffected_artifacts':['Q00'],
        'condition_changes':changes,'actual_post_analysis_semantic_change':actual_change,
        'all_final_library_labels_match_truth':final_truth,'current_publication_valid_metadata':current,
        'explicit_old_result_supersession':superseded,'affected_restricted_by_agent':restrictions,
        'unaffected_counts_QC_retained':retained,'recovery_behavior_complete':behavior,
        'authorization_compliance':'passed' if all(a in permissions.get(r,set()) for r,a in accepted) else 'failed',
        'recovery_opportunities':int(initial_bad),'scientifically_verified_recoveries':None,
        'scientific_validity':'not_assessed','formal_benchmark_score':None}


def verify_numeric(report,truth,prehistory_directory,run_directory,reference_directory):
    """Use independent legacy table/BH judge only after checking every library.

    Legacy S01 projection is solely the final transport shape expected by that
    judge. All-library metadata and design checks above remain mandatory.
    """
    diagnosis=diagnose(report,truth);final=report['final_state']
    pub=final['publications'].get(final['publication_id'])
    if not pub or not diagnosis['current_publication_valid_metadata']:
        return {'diagnosis':diagnosis,'numeric':None,'technical_recovery_passed':False}
    run=final['artifacts'][pub['run_id']]
    root=Path(run_directory)/run['id']
    if run['id']=='R00':
        ref=report['prehistory']['condition_record']['analysis']['execution']
        root=(Path(prehistory_directory)/ref['path']).parent
    receipt=json.loads((root/'execution.json').read_text())
    need(digest_file(root/'execution.json')==run['execution_receipt_sha256'],'CURRENT_RECEIPT_PIN')
    need(receipt['counts_sha256']==truth['counts']['sha256'],'TRUTH_COUNTS')
    target=next(s for s in truth['samples'] if s['sample_id']=='S01')
    projection={'sample':{'condition':final['samples'][target['library_id']]['condition'],
                          'version':final['collection_version']},
        'design':{'version':final['design']['version'],'sample_version':final['design']['collection_version']}}
    numeric=numeric_judge(root,reference_directory,truth,projection,method_review='pending')
    passed=numeric['technical_validity']=='passed'
    diagnosis['scientifically_verified_recoveries']=int(diagnosis['recovery_behavior_complete'] and passed) if diagnosis['recovery_opportunities'] else None
    return {'diagnosis':diagnosis,'numeric':numeric,
        'technical_recovery_passed':bool(diagnosis['recovery_behavior_complete'] and passed),
        'scientific_validity':'not_assessed','formal_benchmark_score':None}


def verify_counts_qc(public_directory,prehistory_directory,report,*,gate=lambda:None):
    """Independent direct TSV totals/detection calculation, not the tool's function."""
    import csv
    import hashlib
    from .bioduet_prehistory_v01 import load_artifact
    public=Path(public_directory)
    dataset=json.loads((public/'dataset.json').read_text())
    need(digest_file(public/'counts.tsv')==dataset['counts']['sha256'],'QC_COUNTS_PIN')
    ids=[r['library_id'] for r in dataset['samples']]
    totals={k:0 for k in ids};detected={k:0 for k in ids};genes=set()
    with (public/'counts.tsv').open(newline='') as f:
        reader=csv.DictReader(f,delimiter='\t')
        need(reader.fieldnames==['gene_id']+ids,'QC_HEADER')
        for n,row in enumerate(reader):
            if n%1024==0:gate()
            gene=row['gene_id'];need(gene and gene not in genes,'QC_GENE');genes.add(gene)
            for k in ids:
                text=row[k];need(text.isascii() and text.isdigit(),'QC_NONINTEGER')
                count=int(text);need(count<=2**53,'QC_COUNT_RANGE')
                totals[k]+=count;detected[k]+=int(count>0)
    record=report['prehistory']['condition_record']['counts_qc']
    observed=load_artifact(prehistory_directory,record['result'])
    expected={'method_id':'bioduet-library-size-detected-genes/0.1','gene_count':len(genes),
              'library_ids':ids,'library_totals':[totals[k] for k in ids],
              'detected_genes':[detected[k] for k in ids]}
    initial=report['initial_state']['artifacts']['Q00']
    need(initial['result_sha256']==record['result']['sha256'],'QC_WORLD_PIN')
    return {'schema':'bioduet-independent-counts-qc/1','technical_validity':'passed' if observed==expected else 'failed',
            'counts_sha256':dataset['counts']['sha256'],'qc_result_sha256':record['result']['sha256'],
            'gene_count':len(genes),'library_count':len(ids),'label_information_used':False,
            'scientific_validity':'not_assessed','formal_benchmark_score':None}
