"""Route operation recovery/result reads through the existing per-scope authority.
Notice, dataset, file, job submission and retrieval paths remain in v04.
"""
import json,hashlib
from .participant_tools_v04 import ParticipantTools as ExistingTools
from .contracts_v01 import require

class ParticipantTools(ExistingTools):
    def invoke(self,scope,name,arguments):
        if name not in ("job.lookup","job.result"):
            return super().invoke(scope,name,arguments)
        require(self._scopes.get(scope.principal_id) is scope,"TOOL_SCOPE")
        require(type(arguments) is dict,"TOOL_REQUEST")
        raw=json.dumps(arguments,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        require(len(raw)<=1048576,"TOOL_REQUEST_SIZE");args=json.loads(raw)
        entry={"principal_id":scope.principal_id,"episode_id":scope.episode_id,
               "attempt_id":scope.attempt_id,"tool":name,"request_sha256":hashlib.sha256(raw).hexdigest(),
               "state":"requested","authority_receipt":None}
        self.audit.append(entry)
        try:
            proof=self.authorize(scope,name,args)
            require(type(proof) is dict and proof.get("allowed") is True and
                    type(proof.get("authority_seq")) is int and proof["authority_seq"]>=0,
                    "TOOL_NOT_AUTHORIZED")
            entry["authority_receipt"]=dict(proof)
            if name=="job.lookup":
                require(set(args)=={"operation_id","idempotency_key"},"TOOL_FIELDS")
                result=self.jobs.lookup(scope,args["operation_id"],args["idempotency_key"])
            else:
                require(set(args)=={"job_id"},"TOOL_FIELDS")
                result=self.jobs.result(scope,args["job_id"])
            entry["state"]="returned";return result
        except BaseException as exc:
            entry["state"]="rejected_or_failed";entry["error_type"]=type(exc).__name__;raise
