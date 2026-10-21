"""Independent raw-count qualification; never exposed as a participant tool."""
import argparse,csv,json,os,signal,subprocess,time
from pathlib import Path
from labweave_eval.bw01_reference_runner_v01 import digest

def verify_receipt(path,public_directory,truth_path):
    path=Path(path);record=json.loads(path.read_text())
    truth=json.loads(Path(truth_path).read_text())
    if (record.get('schema')!='bw01-independent-aggregation/1' or record.get('status')!='succeeded'
        or record.get('exit_code')!=0 or record.get('truth_sha256')!=digest(truth_path)
        or record.get('counts_sha256')!=digest(Path(public_directory)/'counts.tsv')
        or record.get('counts_sha256')!=truth['counts']['sha256']
        or record.get('dataset_sha256')!=digest(Path(public_directory)/'dataset.json')
        or record.get('script_sha256')!=digest(Path(__file__).with_name('bw01_reference_aggregate_v01.R'))
        or record.get('source_files')!=truth['source_files']
        or record.get('check_sha256')!=digest(path.parent/'check.tsv')):
        raise ValueError('AGGREGATION_EVIDENCE')
    with (path.parent/'check.tsv').open(newline='') as f:rows=list(csv.DictReader(f,delimiter='\t'))
    dataset=json.loads((Path(public_directory)/'dataset.json').read_text())
    if len(rows)!=1 or rows[0]!={'check':'all_raw_aggregate_entries_equal','passed':'TRUE',
             'genes':str(dataset['gene_count']),'libraries':str(len(dataset['samples']))}:
        raise ValueError('AGGREGATION_CHECK')
    return {'sha256':digest(path),'status':'succeeded','counts_sha256':record['counts_sha256']}

def run_check(raw_directory,public_directory,truth_path,output,*,rscript,library_directory=None,wall_seconds=300):
    if type(wall_seconds) is not int or not 1<=wall_seconds<=600:raise ValueError('WALL')
    truth=json.loads(Path(truth_path).read_text());public=Path(public_directory);raw=Path(raw_directory)
    # Independently verify immutable inputs; no candidate reducer/validator is imported.
    for item in truth['source_files'].values():
        if Path(item['name']).name!=item['name']:raise ValueError('RAW_NAME')
        p=raw/item['name']
        if p.is_symlink() or p.stat().st_size!=item['bytes'] or digest(p)!=item['sha256']:
            raise ValueError('RAW_IDENTITY')
    if digest(public/'counts.tsv')!=truth['counts']['sha256']:raise ValueError('COUNTS_IDENTITY')
    out=Path(output);out.mkdir(mode=0o700,exist_ok=False)
    script=Path(__file__).with_name('bw01_reference_aggregate_v01.R')
    record={'schema':'bw01-independent-aggregation/1','status':'failed','failure':None,
        'truth_sha256':digest(truth_path),'counts_sha256':digest(public/'counts.tsv'),
        'dataset_sha256':digest(public/'dataset.json'),'source_files':truth['source_files'],
        'script_sha256':digest(script)}
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(out),'OMP_NUM_THREADS':'1',
         'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    if library_directory:env['R_LIBS_USER']=str(Path(library_directory).resolve(strict=True))
    process=None;started=time.monotonic()
    try:
        with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
            process=subprocess.Popen([str(rscript),'--vanilla',str(script),str(raw),str(public),
                str(truth_path),str(out/'check.tsv')],env=env,stdin=subprocess.DEVNULL,
                stdout=stdout,stderr=stderr,start_new_session=True)
            try:record['exit_code']=process.wait(timeout=wall_seconds)
            except subprocess.TimeoutExpired:record['failure']='TIMEOUT'
        if record.get('exit_code')==0:
            record['check_sha256']=digest(out/'check.tsv');record['status']='succeeded'
        elif record['failure'] is None:record['failure']='AGGREGATE_PROCESS_FAILED'
    except Exception as exc:record['failure']=type(exc).__name__
    finally:
        if process:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:record['status']='failed';record['failure']='CLEANUP_UNCONFIRMED'
        record['elapsed_seconds']=time.monotonic()-started
        fd=os.open(out/'aggregation.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(record,f,indent=2)
    if record['status']=='succeeded':verify_receipt(out/'aggregation.json',public,truth_path)
    return record

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['raw-directory','public-directory','truth','output','rscript']:
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--r-library',type=Path)
    a=p.parse_args(argv)
    r=run_check(a.raw_directory,a.public_directory,a.truth,a.output,rscript=a.rscript,library_directory=a.r_library)
    print(json.dumps({'status':r['status'],'receipt':str(a.output/'aggregation.json')}))
    return 0 if r['status']=='succeeded' else 2
if __name__=='__main__':raise SystemExit(main())
