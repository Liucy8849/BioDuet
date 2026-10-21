"""Trusted private reference runner. Independent from candidate Python adapter."""
import csv,hashlib,json,os,signal,subprocess,time
from .bioduet_process_cleanup_v01 import close_group
from pathlib import Path

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()

def run_reference(public_directory,truth_path,output,*,rscript,edgeR_version,
                  library_directory=None,wall_seconds=180,cancel=None):
    if type(wall_seconds) is not int or not 1<=wall_seconds<=600:raise ValueError('WALL')
    truth=json.loads(Path(truth_path).read_text());counts=Path(public_directory)/'counts.tsv';out=Path(output)
    if digest(counts)!=truth['counts']['sha256']:raise ValueError('REFERENCE_INPUT_HASH')
    out.mkdir(mode=0o700,exist_ok=False)
    with (out/'truth-design.tsv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['library_id','donor_id','condition'],delimiter='\t',lineterminator='\n')
        writer.writeheader();writer.writerows({k:s[k] for k in writer.fieldnames} for s in truth['samples'])
    script=Path(__file__).with_name('bw01_reference_v01.R')
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(out),'OMP_NUM_THREADS':'1',
         'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    if library_directory:env['R_LIBS_USER']=str(Path(library_directory).resolve(strict=True))
    result={'schema':'bw01-independent-reference/1','status':'failed','edgeR_version':edgeR_version,
            'counts_sha256':truth['counts']['sha256'],'truth_sha256':digest(truth_path),
            'reference_script_sha256':digest(script),'failure':None}
    process=None;started=time.monotonic()
    try:
        with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
            if cancel is not None and cancel.is_set():raise RuntimeError('CANCELLED_BEFORE_LAUNCH')
            process=subprocess.Popen([str(rscript),'--vanilla',str(script),str(counts),str(out/'truth-design.tsv'),
                str(out),edgeR_version],env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
            result['launcher']={'pid':process.pid,'start_ticks':
                Path('/proc/%s/stat'%process.pid).read_text().rsplit(')',1)[1].split()[19]}
            end=time.monotonic()+wall_seconds
            while process.poll() is None:
                if cancel is not None and cancel.is_set():result['failure']='CANCELLED';break
                if time.monotonic()>=end:result['failure']='TIMEOUT';break
                time.sleep(min(0.05,max(0,end-time.monotonic())))
            if result['failure'] is None:result['exit_code']=process.wait(timeout=1)
        if result.get('exit_code')==0:
            p=out/'reference-de.tsv';result['result']={'sha256':digest(p),'bytes':p.stat().st_size};result['status']='succeeded'
        elif result['failure'] is None:result['failure']='REFERENCE_PROCESS_FAILED'
    except Exception as exc:result['failure']=type(exc).__name__
    finally:
        result['cleanup']=close_group(process)
        if not result['cleanup']['confirmed']:
            result['status']='failed';result['failure']='CLEANUP_UNCONFIRMED'
        result['elapsed_seconds']=time.monotonic()-started
        fd=os.open(out/'reference.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(result,f,indent=2)
    return result
