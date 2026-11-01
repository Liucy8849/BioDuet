"""Trusted host tool router connecting versioned scope, files, jobs and retrieval."""
import hashlib,json,base64
from .contracts_v01 import require,nonempty
class ParticipantTools:
    def __init__(self,*,workspace,jobs,authorize,retrieval=None,datasets=None):
        require(callable(authorize),"AUTHORITY_REQUIRED")
        self.workspace=workspace;self.jobs=jobs;self.authorize=authorize;self.retrieval=retrieval
        self.datasets=datasets
        self._scopes={};self.audit=[]
    def bind(self,scope):
        require(scope.principal_id not in self._scopes,"TOOL_SCOPE_ALREADY_BOUND")
        self._scopes[scope.principal_id]=scope
        self.workspace.bind(scope)
        if self.datasets is not None:self.datasets.bind(scope)
    def invoke(self,scope,name,arguments):
        require(self._scopes.get(scope.principal_id) is scope,"TOOL_SCOPE")
        require(type(name) is str and type(arguments) is dict,"TOOL_REQUEST")
        # Snapshot inputs; caller mutation cannot change the authorized request.
        raw=json.dumps(arguments,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        require(len(raw)<=1048576,"TOOL_REQUEST_SIZE")
        args=json.loads(raw);entry={"principal_id":scope.principal_id,"episode_id":scope.episode_id,
            "attempt_id":scope.attempt_id,"tool":name,"request_sha256":hashlib.sha256(raw).hexdigest(),
            "state":"requested","authority_receipt":None}
        self.audit.append(entry)
        try:
            receipt=self.authorize(scope,name,args)
            require(type(receipt) is dict and receipt.get("allowed") is True and
                    type(receipt.get("authority_seq")) is int and receipt["authority_seq"]>=0,
                    "TOOL_NOT_AUTHORIZED")
            entry["authority_receipt"]=dict(receipt)
            if name=="dataset.list":
                require(self.datasets is not None and not args,"TOOL_FIELDS")
                result=self.datasets.list(scope)
            elif name=="dataset.read":
                require(self.datasets is not None and set(args)=={"object_id","offset","length"},"TOOL_FIELDS")
                chunk,receipt=self.datasets.read_chunk(scope,args["object_id"],offset=args["offset"],length=args["length"])
                result={"encoding":"base64","content":base64.b64encode(chunk).decode("ascii"),"receipt":receipt}
            elif name=="workspace.read":
                require(set(args)=={"path"},"TOOL_FIELDS")
                content,ref=self.workspace.read(scope,args["path"])
                result={"content":content.decode("utf-8"),"ref":ref}
            elif name=="workspace.write":
                require(set(args)=={"path","content"} and type(args["content"]) is str,"TOOL_FIELDS")
                # This is tool-submitted content, not proof of model authorship.
                result=self.workspace.write(scope,args["path"],args["content"].encode(),code_origin="generated")
            elif name=="job.submit":
                require(set(args)=={"operation_id","idempotency_key","request"},"TOOL_FIELDS")
                self.workspace.read_ref(scope,args["request"]["code_ref"])
                row,replayed=self.jobs.submit(scope,args["operation_id"],args["idempotency_key"],args["request"])
                result={"job":row,"replayed":replayed}
            elif name in ("job.status","job.cancel"):
                require(set(args)=={"job_id"},"TOOL_FIELDS")
                result=(self.jobs.status if name=="job.status" else self.jobs.cancel)(scope,args["job_id"])
            elif name=="web.search":
                require(self.retrieval is not None,"RETRIEVAL_UNAVAILABLE")
                require(set(args)=={"query","count","need_content"},"TOOL_FIELDS")
                result=self.retrieval.search(args["query"],count=args["count"],need_content=args["need_content"])
            elif name=="web.fetch":
                require(self.retrieval is not None and set(args)=={"url"},"TOOL_FIELDS")
                result=self.retrieval.fetch(args["url"])
            else:raise ValueError("UNKNOWN_TOOL")
            entry["state"]="returned"
            return result
        except BaseException as exc:
            entry["state"]="rejected_or_failed";entry["error_type"]=type(exc).__name__
            raise
