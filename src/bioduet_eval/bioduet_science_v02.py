"""Trusted bounded scientific tool adapter; no automatic environment install."""
import csv,json,os,signal,subprocess,time
from pathlib import Path
from bioduet_eval.bw01_artifacts_v01 import save_new,file_ref
from bioduet_eval.bw01_data_v01 import sha256,METHOD
from .bioduet_process_cleanup_v01 import close_group

def validate_design(dataset,rows):
    if type(rows) is not list or len(rows)!=len(dataset['samples']):raise ValueError('DESIGN_SIZE')
    expected={s['library_id']:s['donor_id'] for s in dataset['samples']}
    actual={}
    for row in rows:
        if type(row) is not dict or set(row)!={'library_id','donor_id','condition'}:raise ValueError('DESIGN_SCHEMA')
        lib=row['library_id']
        if lib in actual or lib not in expected or row['donor_id']!=expected[lib]:raise ValueError('DESIGN_DONOR')
        if row['condition'] not in ('control','stim'):raise ValueError('DESIGN_CONDITION')
        actual[lib]=row
    groups={}
    for row in rows:groups.setdefault(row['donor_id'],[]).append(row['condition'])
    if len(groups)<2 or any(sorted(v)!=['control','stim'] for v in groups.values()):
        raise ValueError('PAIRED_DONORS_REQUIRED')
    return [actual[s['library_id']] for s in dataset['samples']]

def write_design(path,rows):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['library_id','donor_id','condition'],delimiter='\t',lineterminator='\n')
        writer.writeheader();writer.writerows(rows)

def execute(public_directory,rows,output,*,rscript,edgeR_version,sample_version,
            design_version,wall_seconds=180,library_directory=None,cancel=None):
    if type(wall_seconds) is not int or not 1<=wall_seconds<=600:raise ValueError('WALL')
    if type(sample_version) is not int or sample_version<1 or type(design_version) is not int or design_version<1:
        raise ValueError('VERSIONS')
    public_directory=Path(public_directory);output=Path(output)
    dataset=json.loads((public_directory/'dataset.json').read_text())
    counts=public_directory/'counts.tsv'
    if sha256(counts)!=dataset['counts']['sha256']:raise ValueError('COUNTS_IDENTITY')
    rows=validate_design(dataset,rows)
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    write_design(output/'design.tsv',rows)
    script=Path(__file__).with_name('bw01_edger_v01.R')
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(output),
         'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    if library_directory:env['R_LIBS_USER']=str(Path(library_directory).resolve(strict=True))
    record={'schema':'bw01-analysis-execution/1','method_id':METHOD,
        'source_kind':dataset['source_kind'],'sample_version':sample_version,'design_version':design_version,
        'counts_sha256':dataset['counts']['sha256'],'design':file_ref(output/'design.tsv'),
        'script':file_ref(script),'edgeR_version':edgeR_version,'scientific_validity':'not_assessed',
        'status':'failed','failure':None}
    started=time.monotonic();process=None
    try:
        with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
            if cancel is not None and cancel.is_set():raise RuntimeError('CANCELLED_BEFORE_LAUNCH')
            process=subprocess.Popen([str(rscript),'--vanilla',str(script),str(counts),
                str(output/'design.tsv'),str(output),edgeR_version],env=env,stdin=subprocess.DEVNULL,
                stdout=stdout,stderr=stderr,start_new_session=True)
            record['launcher']={'pid':process.pid,'start_ticks':
                Path('/proc/%s/stat'%process.pid).read_text().rsplit(')',1)[1].split()[19]}
            end=time.monotonic()+wall_seconds
            while process.poll() is None:
                if cancel is not None and cancel.is_set():
                    record['failure']='CANCELLED';break
                if time.monotonic()>=end:
                    record['failure']='TIMEOUT';break
                time.sleep(min(0.05,max(0,end-time.monotonic())))
            if record['failure'] is None:record['exit_code']=process.wait(timeout=1)
        if record.get('exit_code')==0:
            record['result']=file_ref(output/'de.tsv');record['environment']=file_ref(output/'execution.tsv')
            from bioduet_eval.bw01_result_view_v01 import summarize
            record['preview']=summarize(output,dataset,public_directory)
            record['status']='succeeded'
        elif record['failure'] is None:record['failure']='ANALYSIS_PROCESS_FAILED'
    except Exception as exc:record['failure']=type(exc).__name__
    finally:
        record['cleanup']=close_group(process)
        if not record['cleanup']['confirmed']:
            record['status']='failed';record['failure']='CLEANUP_UNCONFIRMED'
        record['elapsed_seconds']=time.monotonic()-started
        save_new(output/'execution.json',record)
    return record
