"""Offline immutable runtime staging into a fresh P-owned tree; no install/exec.
Root admits this finite copy stage and separately qualifies R/loader before use.
Historical public R paths are SOURCE ONLY. Original source bytes stay unchanged.
"""
import argparse,json,os,stat,hashlib
from pathlib import Path
P=Path(__file__).resolve().parents[2]
def load_pin(row):
    p=Path(row["path"]);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or not 0<=st.st_size<=64*1024*1024:raise ValueError("FINITE_SOURCE")
        raw=bytearray()
        while True:
            b=os.read(fd,65536)
            if not b:break
            raw.extend(b)
            if len(raw)>64*1024*1024:raise ValueError("SOURCE_LIMIT")
        z=os.fstat(fd);now=os.lstat(p)
        if any(getattr(st,k)!=getattr(z,k) or getattr(z,k)!=getattr(now,k)
               for k in ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")):raise ValueError("SOURCE_CHANGED")
        if len(raw)!=row["bytes"] or hashlib.sha256(raw).hexdigest()!=row["sha256"]:raise ValueError("SOURCE_PIN")
        return bytes(raw)
    finally:os.close(fd)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--manifest",required=True);ap.add_argument("--manifest-sha256",required=True)
    ap.add_argument("--destination",required=True);args=ap.parse_args()
    m=Path(args.manifest);raw=m.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.manifest_sha256:raise ValueError("ROOT_FROZEN_COPY_INPUT")
    manifest=json.loads(raw);dest=Path(args.destination)
    if not dest.is_absolute() or not dest.parent.resolve().is_relative_to(P) or dest.exists():
        raise ValueError("FRESH_P_OWNED_RUNTIME_ONLY")
    if manifest["schema"]!="bioduet-R-runtime-copy-inputs/1":raise ValueError("COPY_SCHEMA")
    rows=manifest["files"]
    if len(rows)>1600 or sum(x["bytes"] for x in rows)>384*1024*1024:raise ValueError("FINITE_COPY_BUDGET")
    dest.mkdir(mode=0o700);fs=dest/"fs";fs.mkdir(mode=0o700);index=[]
    for row in rows:
        rel=Path(row["target_absolute_path"])
        if not rel.is_absolute() or ".." in rel.parts:raise ValueError("NORMALIZED_NAMESPACE_TARGET")
        target=fs/str(rel).lstrip("/")
        if target.exists() or target.is_symlink():raise ValueError("DUPLICATE_TARGET")
        source=load_pin(row["source"]);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        mode=row["staged_mode"]
        if mode not in (0o444,0o555):raise ValueError("EXPLICIT_STAGED_READONLY_MODE")
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
        os.fchmod(fd,mode)
        if stat.S_IMODE(os.fstat(fd).st_mode)!=mode:raise ValueError("EXACT_STAGED_MODE_NOT_UMASK_INFERENCE")
        with os.fdopen(fd,"wb") as f:f.write(source);f.flush();os.fsync(f.fileno())
        if target.read_bytes()!=source:raise ValueError("STAGED_READBACK")
        index.append({"physical_P_path":str(target),"namespace_absolute_path":str(rel),
            "bytes":len(source),"sha256":row["source"]["sha256"],"staged_mode":mode,
            "source_ref":row["source"]})
    # Source and staged inputs are rechecked by Root before/after actual qualifier.
    report={"schema":"bioduet-R-runtime-staged-bytes/1","source_manifest_sha256":args.manifest_sha256,
        "staged_files":index,"installed_or_built_packages":False,"R_executed":False,
        "actual_loader_or_Rbase_qualified":False,"original_paths_are_source_not_execution":True,
        "existing131_library_reinstalled":False}
    out=(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+"\n").encode()
    fd=os.open(dest/"staged-index.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:f.write(out);f.flush();os.fsync(f.fileno())
    print(json.dumps({"files":len(index),"bytes":sum(r["bytes"] for r in index),
        "staged_index_sha256":hashlib.sha256(out).hexdigest(),"R_executed":False}))
if __name__=="__main__":main()
