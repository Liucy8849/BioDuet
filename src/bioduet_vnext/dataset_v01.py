"""Role-bound immutable dataset bytes, loaded only from operator-pinned public views."""
import hashlib
from .contracts_v01 import require,nonempty
from .score_bridge_v01 import read_pinned
class DatasetBank:
    def __init__(self,*,max_total_bytes=64*1024*1024):
        require(type(max_total_bytes) is int and max_total_bytes>0,"DATASET_QUOTA")
        self.limit=max_total_bytes;self.total=0;self.contexts={};self.data={};self.audit=[]
    def bind(self,scope):
        require(scope.principal_id not in self.contexts,"DATASET_BOUND")
        self.contexts[scope.principal_id]=scope
    def _scope(self,scope):
        require(self.contexts.get(scope.principal_id) is scope,"DATASET_SCOPE")
    def register(self,scope,object_id,*,root,relative,expected_sha256):
        self._scope(scope);require(nonempty(object_id),"DATASET_ID")
        key=(id(scope),object_id);require(key not in self.data,"DATASET_DUPLICATE")
        raw=read_pinned(root,relative,expected_sha256,max_bytes=min(self.limit,32*1024*1024))
        require(self.total+len(raw)<=self.limit,"DATASET_QUOTA")
        self.data[key]=(raw,{"object_id":object_id,"sha256":expected_sha256,"size_bytes":len(raw),
                            "access":"read_only","revision":1})
        self.total+=len(raw)
    def list(self,scope):
        self._scope(scope)
        return [dict(meta) for (identity,_),(raw,meta) in self.data.items() if identity==id(scope)]
    def read_chunk(self,scope,object_id,*,offset=0,length=65536):
        self._scope(scope)
        require(type(offset) is int and offset>=0 and type(length) is int and 1<=length<=65536,"DATASET_RANGE")
        key=(id(scope),object_id);require(key in self.data,"DATASET_NOT_AUTHORIZED")
        raw,meta=self.data[key];require(offset<=len(raw),"DATASET_RANGE")
        chunk=raw[offset:offset+length]
        receipt={"object_id":object_id,"source_sha256":meta["sha256"],"offset":offset,
                 "length":len(chunk),"chunk_sha256":hashlib.sha256(chunk).hexdigest(),
                 "eof":offset+len(chunk)==len(raw)}
        self.audit.append({"principal_id":scope.principal_id,**receipt})
        return chunk,receipt
