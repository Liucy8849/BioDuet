"""Trusted immutable snapshots of native workspace files, not execution receipts."""
import os,stat,hashlib
from pathlib import Path
from .contracts_v01 import require,Scope
class ScopedNativeArtifactSnapshots:
    def __init__(self,root,*,role_roots,role_scopes,authorize_read,max_bytes=16777216):
        require(callable(authorize_read) and type(max_bytes) is int and 0<max_bytes<=16777216,
                "FINITE_TRUSTED_SNAPSHOT_POLICY")
        require(set(role_roots)==set(role_scopes) and set(role_roots)<= {"A","H"},"ROLE_ROOTS")
        self.root=Path(root);require(self.root.is_absolute() and not self.root.exists(),"FRESH_SNAPSHOT_CUSTODY")
        self.root.mkdir(mode=0o700)
        self.roots={};self.scopes={};self.records={};self.audit=[]
        for role,value in role_roots.items():
            scope=role_scopes[role];p=Path(value)
            require(type(scope) is Scope and scope.role==role and p.is_absolute() and
                    p.is_dir() and not p.is_symlink(),"EXACT_ROLE_WORKSPACE_BINDING")
            self.roots[role]=p;self.scopes[role]=scope
        self.authorize=authorize_read;self.limit=max_bytes
    def __call__(self,role,name,operation_id,kind):
        require(role in self.roots and kind in ("code","result"),"SNAPSHOT_ROLE_KIND")
        require(type(name) is str and name not in ("",".","..") and
                "/" not in name and "\\" not in name and "\x00" not in name,"ROLE_LOCAL_FILE_ONLY")
        scope=self.scopes[role]
        require(self.authorize(scope,name,operation_id,kind) is True,"CURRENT_ROLE_SNAPSHOT_AUTHORITY")
        token=hashlib.sha256((scope.episode_id+"\0"+scope.attempt_id+"\0"+role+"\0"+operation_id+"\0"+kind).encode()).hexdigest()
        target=self.root/(token+".bin")
        rootfd=os.open(self.roots[role],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        source=None;destination=None;row={"role":role,"principal_id":scope.principal_id,
            "operation_id":operation_id,"kind":kind,"source_relative_name":name,
            "state":"snapshot_requested","execution_proof":False}
        self.audit.append(row)
        try:
            source=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=rootfd)
            before=os.fstat(source)
            require(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=self.limit,"BOUNDED_REGULAR_FILE")
            destination=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            digest=hashlib.sha256();total=0
            while True:
                block=os.read(source,min(65536,self.limit+1-total))
                if not block:break
                total+=len(block);require(total<=self.limit,"ARTIFACT_GREW_OVER_BOUND")
                digest.update(block)
                position=0
                while position<len(block):
                    written=os.write(destination,block[position:]);require(written>0,"SHORT_SNAPSHOT_WRITE")
                    position+=written
            os.fsync(destination);after=os.fstat(source);current=os.stat(name,dir_fd=rootfd,follow_symlinks=False)
            keys=("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")
            require(stat.S_ISREG(current.st_mode) and total==after.st_size and
                    all(getattr(before,k)==getattr(after,k)==getattr(current,k) for k in keys),
                    "ARTIFACT_CHANGED_DURING_SNAPSHOT")
            result={"path":str(target),"bytes":total,"sha256":digest.hexdigest(),
                    "snapshot_kind":"existing_file_bytes_not_execution_proof"}
            self.records[str(target)]=dict(result);row.update(state="snapshotted",ref=dict(result))
            return result
        except BaseException as exc:
            row.update(state="snapshot_failed_partial_preserved",error_type=type(exc).__name__)
            raise
        finally:
            if destination is not None:os.close(destination)
            if source is not None:os.close(source)
            os.close(rootfd)
    def verify(self,ref):
        require(type(ref) is dict and self.records.get(ref.get("path"))==ref,"ISSUED_SNAPSHOT_REF")
        p=Path(ref["path"]);require(p.parent==self.root and not p.is_symlink(),"SNAPSHOT_CUSTODY_PATH")
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and st.st_size==ref["bytes"],"SNAPSHOT_SIZE")
            digest=hashlib.sha256();total=0
            while True:
                block=os.read(fd,65536)
                if not block:break
                total+=len(block);require(total<=self.limit,"SNAPSHOT_LIMIT")
                digest.update(block)
            return total==ref["bytes"] and digest.hexdigest()==ref["sha256"]
        finally:os.close(fd)
