"""Explicit operator-only isolated R dependency setup; never called by an Agent."""
import argparse,hashlib,json,os,signal,subprocess,tarfile,time,urllib.request
from pathlib import Path,PurePosixPath

PACKAGES=(
 ('locfit','1.5-9.10','https://cran.r-project.org/src/contrib/Archive/locfit/locfit_1.5-9.10.tar.gz'),
 ('statmod','1.5.0','https://cran.r-project.org/src/contrib/Archive/statmod/statmod_1.5.0.tar.gz'),
 ('limma','3.62.2','https://bioconductor.posit.co/packages/3.20/bioc/src/contrib/limma_3.62.2.tar.gz'),
 ('edgeR','4.4.2','https://bioconductor.posit.co/packages/3.20/bioc/src/contrib/edgeR_4.4.2.tar.gz'))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()
def save(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2)
def inspect_archive(path,name,version):
    expanded=0;count=0;description=None;seen=set()
    with tarfile.open(path,'r:gz') as tar:
        for item in tar:
            parts=PurePosixPath(item.name)
            if (parts.is_absolute() or '..' in parts.parts or not parts.parts or parts.parts[0]!=name
                or not (item.isfile() or item.isdir()) or item.name in seen):
                raise ValueError('ARCHIVE_PATH_TYPE')
            seen.add(item.name);count+=1;expanded+=item.size
            if count>10000 or expanded>200*1024**2:raise ValueError('ARCHIVE_LIMIT')
            if item.name==name+'/DESCRIPTION':
                if item.size>128*1024:raise ValueError('DESCRIPTION_LIMIT')
                description=tar.extractfile(item).read().decode('utf-8')
    if description is None:raise ValueError('DESCRIPTION_MISSING')
    fields=dict(line.split(': ',1) for line in description.splitlines() if ': ' in line and not line.startswith((' ','\t')))
    if fields.get('Package')!=name or fields.get('Version')!=version:raise ValueError('PACKAGE_IDENTITY')
    return {'members':count,'expanded_bytes':expanded,'description_sha256':hashlib.sha256(description.encode()).hexdigest()}

def install(output,rscript,*,wall_seconds=900):
    if type(wall_seconds) is not int or not 30<=wall_seconds<=1200:raise ValueError('WALL')
    out=Path(output).absolute();out.mkdir(mode=0o700,exist_ok=False)
    for name in ['downloads','library','tmp','logs']: (out/name).mkdir(mode=0o700)
    compiler_bin=Path(rscript).absolute().parent
    rscript=Path(rscript).resolve(strict=True);rbin=compiler_bin/'R'
    env={'PATH':str(compiler_bin)+':'+str(rscript.parent)+':/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(out),'TMPDIR':str(out/'tmp'),
         'R_LIBS_USER':str(out/'library'),'MAKEFLAGS':'-j1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    started=time.monotonic();deadline=started+wall_seconds;downloaded=0;record={'schema':'bw01-isolated-r-install/1','status':'failed','failure':None,
        'rscript':str(rscript),'rscript_sha256':sha(rscript),'packages':[],'library':str(out/'library'),'external_resource_envelope_required':True}
    try:
        for name,version,url in PACKAGES:
            row={'package':name,'version':version,'source_url':url,'status':'started'}
            record['packages'].append(row);path=out/'downloads'/(name+'_'+version+'.tar.gz')
            if time.monotonic()>=deadline:raise TimeoutError('INSTALL_WALL')
            with urllib.request.urlopen(url,timeout=min(40,deadline-time.monotonic())) as response,path.open('xb') as f:
                if response.status!=200 or not response.url.startswith('https://'):raise ValueError('DOWNLOAD_RESPONSE')
                row['resolved_url']=response.url
                while True:
                    if time.monotonic()>=deadline:raise TimeoutError('INSTALL_WALL')
                    block=response.read(1024**2)
                    if not block:break
                    downloaded+=len(block)
                    if downloaded>100*1024**2:raise ValueError('DOWNLOAD_BUDGET')
                    f.write(block)
            row.update(bytes=path.stat().st_size,sha256=sha(path),archive=inspect_archive(path,name,version))
            process=None
            try:
                with (out/'logs'/(name+'.stdout')).open('xb') as stdout,(out/'logs'/(name+'.stderr')).open('xb') as stderr:
                    process=subprocess.Popen([str(rbin),'CMD','INSTALL','--no-multiarch','--no-docs',
                        '--library='+str(out/'library'),str(path)],cwd=out,env=env,stdin=subprocess.DEVNULL,
                        stdout=stdout,stderr=stderr,start_new_session=True)
                    row['exit_code']=process.wait(timeout=max(.1,min(300,deadline-time.monotonic())))
                if row['exit_code']!=0:raise RuntimeError('PACKAGE_INSTALL_FAILED')
                row['status']='installed'
                desc=out/'library'/name/'DESCRIPTION'
                row['installed_description_sha256']=sha(desc)
            finally:
                if process:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=5)
            size=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
            if size>500*1024**2:raise ValueError('STORAGE_BUDGET')
        # Use a fresh R process to check package resolution/version and numerical libraries.
        expression='pkgs<-c("locfit","statmod","limma","edgeR","Matrix","jsonlite"); expected<-c("1.5-9.10","1.5.0","3.62.2","4.4.2"); for(i in seq_along(expected)) stopifnot(packageVersion(pkgs[i])==package_version(expected[i])); write.table(data.frame(package=pkgs,version=vapply(pkgs,function(p) as.character(packageVersion(p)),""),path=vapply(pkgs,find.package,"")),file=commandArgs(TRUE)[1],sep="\\t",row.names=FALSE,quote=FALSE)'
        with (out/'logs/qualification.stdout').open('xb') as stdout,(out/'logs/qualification.stderr').open('xb') as stderr:
            process=subprocess.Popen([str(rscript),'--vanilla','-e',expression,str(out/'resolved-packages.tsv')],
                cwd=out,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
            try:record['qualification_exit_code']=process.wait(timeout=max(.1,min(60,deadline-time.monotonic())))
            finally:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=5)
        if record['qualification_exit_code']!=0:raise RuntimeError('PACKAGE_LOAD_FAILED')
        record['installed_files']=[{'path':str(p.relative_to(out/'library')),'bytes':p.stat().st_size,'sha256':sha(p)}
            for p in sorted((out/'library').rglob('*')) if p.is_file()]
        record['status']='succeeded';record['resolved_packages_sha256']=sha(out/'resolved-packages.tsv')
    except Exception as exc:
        record['failure']=type(exc).__name__
        # Operator-only failure code, not arbitrary network/process exception text.
        if isinstance(exc,(ValueError,RuntimeError,TimeoutError)) and str(exc).isupper():record['failure_code']=str(exc)
    finally:
        record['downloaded_bytes']=downloaded;record['elapsed_seconds']=time.monotonic()-started
        record['storage_bytes']=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
        save(out/'installation.json',record)
    return record
def verify_installation(directory,rscript):
    directory=Path(directory);record=json.loads((directory/'installation.json').read_text())
    expected=[(p,v) for p,v,_ in PACKAGES]
    if (record.get('status')!='succeeded' or record.get('rscript_sha256')!=sha(Path(rscript).resolve(strict=True))
        or [(r['package'],r['version']) for r in record['packages']]!=expected
        or record.get('resolved_packages_sha256')!=sha(directory/'resolved-packages.tsv')):
        raise ValueError('ENVIRONMENT_IDENTITY')
    actual={str(p.relative_to(directory/'library')) for p in (directory/'library').rglob('*') if p.is_file()}
    declared=record.get('installed_files',[])
    if not declared or actual!={r['path'] for r in declared}:raise ValueError('ENVIRONMENT_FILE_SET')
    for row in declared:
        relative=PurePosixPath(row['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('ENVIRONMENT_PATH')
        p=directory/'library'/relative
        if p.is_symlink() or p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:raise ValueError('ENVIRONMENT_BYTES')
    return record

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--rscript',required=True,type=Path)
    a=p.parse_args(argv);result=install(a.output,a.rscript)
    print(json.dumps({'status':result['status'],'receipt':str(a.output/'installation.json'),'failure':result['failure']}))
    return 0 if result['status']=='succeeded' else 2
if __name__=='__main__':raise SystemExit(main())
