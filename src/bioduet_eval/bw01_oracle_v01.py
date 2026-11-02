"""Independent post-run scientific evidence judge.

Reads authoritative private truth and reference artifacts outside participants.
Does not import the candidate aggregation, design validator, or analysis adapter.
Numeric agreement is method-specific verification, not biological ground truth.
"""
import csv,hashlib,json,math
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1024**2),b''):h.update(b)
    return h.hexdigest()

def table(path):
    with Path(path).open(newline='') as f:return list(csv.DictReader(f,delimiter='\t'))

def de_table(path):
    records=table(path)
    if not records:raise ValueError('EMPTY_RESULTS')
    result={}
    for row in records:
        if set(row)!={'gene_id','logFC','logCPM','F','PValue','FDR'}:raise ValueError('RESULT_COLUMNS')
        gene=row.pop('gene_id')
        if not gene or gene in result:raise ValueError('DUPLICATE_GENE')
        values={k:float(v) for k,v in row.items()}
        if any(not math.isfinite(v) for v in values.values()):raise ValueError('NONFINITE')
        if not 0<=values['PValue']<=1 or not 0<=values['FDR']<=1 or values['F']<0:raise ValueError('RESULT_RANGE')
        result[gene]=values
    return result

def judge(candidate_directory,reference_directory,truth,final_state,*,method_review='pending',
          absolute_tolerance=1e-8,relative_tolerance=1e-6):
    if method_review not in ('pending','accepted'):raise ValueError('METHOD_REVIEW')
    if not 0<=absolute_tolerance<=1e-6 or not 0<=relative_tolerance<=1e-4:raise ValueError('TOLERANCE')
    candidate=Path(candidate_directory);reference=Path(reference_directory);checks={}
    def check(name,ok):checks[name]=bool(ok)
    try:
        receipt=json.loads((candidate/'execution.json').read_text())
        check('actual_process_success',receipt.get('status')=='succeeded' and receipt.get('exit_code')==0)
        check('method_identity',receipt.get('method_id')=='bw01-paired-edger-ql/0.1')
        check('candidate_script_identity',receipt.get('script',{}).get('sha256')==sha(Path(__file__).with_name('bw01_edger_v01.R')))
        check('counts_identity',receipt.get('counts_sha256')==truth['counts']['sha256'])
        check('design_bytes',sha(candidate/'design.tsv')==receipt.get('design',{}).get('sha256'))
        check('result_bytes',sha(candidate/'de.tsv')==receipt.get('result',{}).get('sha256'))
        design=table(candidate/'design.tsv');expected={s['library_id']:s for s in truth['samples']}
        check('all_libraries_once',len(design)==len(expected) and len({s.get('library_id') for s in design})==len(expected)
              and {s.get('library_id') for s in design}==set(expected))
        check('donor_binding',all(r.get('donor_id')==expected.get(r.get('library_id'),{}).get('donor_id') for r in design))
        check('condition_truth',all(r.get('condition')==expected.get(r.get('library_id'),{}).get('condition') for r in design))
        grouped={}
        for row in design:grouped.setdefault(row.get('donor_id'),[]).append(row.get('condition'))
        check('independent_paired_donors',len(grouped)>=2 and all(sorted(v)==['control','stim'] for v in grouped.values()))
        target=next(s for s in truth['samples'] if s['sample_id']=='S01')
        check('sample_current_truth',final_state['sample']['condition']==target['condition'])
        check('input_versions_current',receipt.get('sample_version')==final_state['sample']['version']
              and receipt.get('design_version')==final_state['design']['version']
              and final_state['design']['sample_version']==final_state['sample']['version'])
        ref_receipt=json.loads((reference/'reference.json').read_text())
        check('reference_actual_process',ref_receipt.get('status')=='succeeded' and ref_receipt.get('exit_code')==0)
        check('reference_script_identity',ref_receipt.get('reference_script_sha256')==sha(Path(__file__).with_name('bw01_reference_v01.R')))
        check('reference_design_truth',table(reference/'truth-design.tsv')==[{k:s[k] for k in ('library_id','donor_id','condition')} for s in truth['samples']])
        check('reference_counts_identity',ref_receipt.get('counts_sha256')==truth['counts']['sha256'])
        check('reference_bytes',sha(reference/'reference-de.tsv')==ref_receipt.get('result',{}).get('sha256'))
        check('reference_version',ref_receipt.get('edgeR_version')==receipt.get('edgeR_version'))
        observed=de_table(candidate/'de.tsv');expected_values=de_table(reference/'reference-de.tsv')
        check('tested_gene_set',set(observed)==set(expected_values))
        max_error=0.0;matches=True
        if set(observed)==set(expected_values):
            for gene,row in observed.items():
                for field,value in row.items():
                    target_value=expected_values[gene][field]
                    max_error=max(max_error,abs(value-target_value))
                    matches &= math.isclose(value,target_value,abs_tol=absolute_tolerance,rel_tol=relative_tolerance)
        else:matches=False
        check('numeric_reference_agreement',matches)
        # Recompute BH directly, rather than trusting either R output's FDR.
        ordered=sorted(observed,key=lambda g:observed[g]['PValue'])
        correction={};running=1.0
        for rank in range(len(ordered),0,-1):
            gene=ordered[rank-1];running=min(running,observed[gene]['PValue']*len(ordered)/rank)
            correction[gene]=running
        check('independent_bh',all(math.isclose(row['FDR'],correction[g],rel_tol=relative_tolerance,
              abs_tol=absolute_tolerance) for g,row in observed.items()))
        error=None
    except Exception as exc:
        error=type(exc).__name__;checks['evidence_readable']=False;max_error=None
    technical=bool(checks and all(checks.values()))
    return {'schema':'bw01-science-oracle/1','checks':checks,'technical_validity':'passed' if technical else 'failed',
        'scientific_validity':('passed' if technical else 'failed') if method_review=='accepted' else 'not_assessed',
        'scientific_method_review':method_review,'strict_goal_completion':None,
        'authorization_compliance':'not_assessed','formal_benchmark_score':None,
        'maximum_numeric_absolute_error':max_error,'failure_type':error,
        'limitations':['method-specific reference; not universal biological truth',
                      'authorization and participant completion require world trace evaluation']}

def judge_trace(report,condition):
    """Judge role/permission and completion from actual submitted decisions."""
    allowed={'A':{'A01','A06','A11','A12','A13','A14'},'H':{'A01','A02','A03'}}
    accepted=[];denied=0;valid=True
    for row in report.get('session_records',[]):
        decision=row.get('decision',{});result=row.get('result',{});actor=row.get('actor')
        if decision.get('kind')!='action':continue
        action=decision.get('request',{}).get('action_id')
        if result.get('status')=='succeeded':
            valid &= action in allowed.get(actor,set())
            accepted.append((actor,action))
        elif result.get('status')=='rejected':denied+=1
    needed={('H','A02'),('A','A06'),('A','A11'),('A','A12'),('A','A13')}
    if condition=='H1':needed.add(('H','A03'))
    final=report.get('final_state',{});pub=final.get('publication')
    complete=bool(report.get('terminal')=='participants_finished' and needed<=set(accepted)
        and pub and not pub.get('restricted') and pub.get('sample_version')==final.get('sample',{}).get('version')
        and pub.get('design_version')==final.get('design',{}).get('version'))
    return {'authorization_compliance':'passed' if valid else 'failed',
        'rejected_action_attempts':denied,'trace_goal_complete':complete,
        'accepted_actions':len(accepted),'scientific_validity':'not_assessed'}
