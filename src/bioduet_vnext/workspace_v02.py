"""Trusted file broker with immutable revisions. Requires an OS-isolated executor."""
import os,json,hashlib,uuid,threading
from pathlib import Path,PurePosixPath
from .contracts_v01 import require,ArtifactRef

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

class Workspace:
    def __init__(self, root, *, max_file_bytes=1048576, max_total_bytes=67108864):
        root=Path(root)
        require(root.is_absolute() and not root.exists(),"FRESH_WORKSPACE_ROOT")
        require(type(max_file_bytes) is int and max_file_bytes>0 and
                type(max_total_bytes) is int and max_total_bytes>=max_file_bytes,"STORAGE_LIMITS")
        root.mkdir(mode=0o700)
        self.root=root
        self.fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.max_file=max_file_bytes;self.max_total=max_total_bytes
        self._contexts={};self._grants={};self._heads={};self._refs={};self._bytes=0
        self._lock=threading.RLock();self.audit=[]
        os.mkdir("objects",mode=0o700,dir_fd=self.fd)
        self.objects=os.open("objects",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.fd)

    @staticmethod
    def _path(path):
        require(type(path) is str and bool(path) and len(path)<=256 and
                "\\" not in path and "\x00" not in path,"WORKSPACE_PATH")
        parts=path.split("/")
        require(all(x not in ("",".","..") for x in parts) and
                not PurePosixPath(path).is_absolute(),"WORKSPACE_PATH")
        return path

    def bind(self,scope):
        require(scope.role in ("A","H","W"),"WORKSPACE_ROLE")
        require(scope.principal_id not in self._contexts,"ALREADY_BOUND")
        self._contexts[scope.principal_id]=scope;self._grants[id(scope)]=True

    def revoke(self,scope):
        self._context(scope);self._grants[id(scope)]=False

    def _context(self,scope):
        require(self._contexts.get(scope.principal_id) is scope,"UNISSUED_CONTEXT")
        require(self._grants[id(scope)],"WORKSPACE_REVOKED")

    def write(self,scope,path,content,*,code_origin):
        with self._lock:
            self._context(scope);self._path(path)
            require(type(content) is bytes and len(content)<=self.max_file,"FILE_LIMIT")
            require(code_origin in ("agent","generated","template","upstream"),"CODE_ORIGIN")
            require(self._bytes+len(content)<=self.max_total,"STORAGE_LIMIT")
            key=(scope.episode_id,scope.attempt_id,scope.project_id,scope.principal_id,path)
            previous=self._heads.get(key)
            revision=1 if previous is None else previous["revision"]+1
            object_id=uuid.uuid4().hex
            raw_sha=hashlib.sha256(content).hexdigest()
            fd=os.open(object_id,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=self.objects)
            try:
                with os.fdopen(fd,"wb") as stream:
                    stream.write(content);stream.flush();os.fsync(stream.fileno())
            except BaseException:
                # Retain partial evidence; never publish its reference as a valid revision.
                raise
            row={"object_id":object_id,"revision":revision,"sha256":raw_sha,
                 "size_bytes":len(content),"logical_path":path,"code_origin":code_origin,
                 "previous_ref":None if previous is None else {k:previous[k] for k in
                    ("object_id","revision","sha256","size_bytes")}}
            self._heads[key]=row
            self._refs[(key[:4],object_id,revision)]=dict(row)
            self._bytes+=len(content)
            self.audit.append({"kind":"workspace_write","principal_id":scope.principal_id,
                               "episode_id":scope.episode_id,"attempt_id":scope.attempt_id,**row})
            return dict(row)

    def read(self,scope,path,*,expected_sha256=None):
        with self._lock:
            self._context(scope);self._path(path)
            key=(scope.episode_id,scope.attempt_id,scope.project_id,scope.principal_id,path)
            require(key in self._heads,"FILE_NOT_AUTHORIZED_OR_ABSENT")
            row=self._heads[key]
            if expected_sha256 is not None:require(row["sha256"]==expected_sha256,"FILE_VERSION")
            fd=os.open(row["object_id"],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.objects)
            try:
                with os.fdopen(fd,"rb") as stream:raw=stream.read(self.max_file+1)
            except BaseException:raise
            require(len(raw)==row["size_bytes"] and hashlib.sha256(raw).hexdigest()==row["sha256"],
                    "FILE_INTEGRITY")
            self.audit.append({"kind":"workspace_read","principal_id":scope.principal_id,
                               "object_id":row["object_id"],"sha256":row["sha256"]})
            return raw,dict(row)

    def read_ref(self,scope,ref):
        with self._lock:
            self._context(scope)
            require(type(ref) is dict,"CODE_REF")
            key=((scope.episode_id,scope.attempt_id,scope.project_id,scope.principal_id),
                 ref.get("object_id"),ref.get("revision"))
            known=self._refs.get(key)
            require(known is not None and ref==known,"REF_NOT_OWNED_OR_CHANGED")
            fd=os.open(known["object_id"],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.objects)
            with os.fdopen(fd,"rb") as stream:raw=stream.read(self.max_file+1)
            require(len(raw)==known["size_bytes"] and hashlib.sha256(raw).hexdigest()==known["sha256"],
                    "FILE_INTEGRITY")
            self.audit.append({"kind":"workspace_read_ref","principal_id":scope.principal_id,
                               "object_id":known["object_id"],"sha256":known["sha256"]})
            return raw,dict(known)

    def close(self):
        if self.objects is not None:os.close(self.objects);self.objects=None
        if self.fd is not None:os.close(self.fd);self.fd=None
