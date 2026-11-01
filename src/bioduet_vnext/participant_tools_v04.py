"""Add durable minimal notices to the existing scoped tool router."""
import json,hashlib
from .participant_tools_v03 import ParticipantTools as ExistingTools
from .contracts_v01 import require
class ParticipantTools(ExistingTools):
    def __init__(self,*,notices=None,**kwargs):
        super().__init__(**kwargs);self.notices=notices
    def bind(self,scope):
        super().bind(scope)
        if self.notices is not None:self.notices.bind(scope)
    def invoke(self,scope,name,arguments):
        if name not in ("notice.receive","notice.acknowledge"):
            return super().invoke(scope,name,arguments)
        require(self._scopes.get(scope.principal_id) is scope,"TOOL_SCOPE")
        require(type(arguments) is dict,"TOOL_REQUEST")
        raw=json.dumps(arguments,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        require(len(raw)<=1048576,"TOOL_REQUEST_SIZE");args=json.loads(raw)
        entry={"principal_id":scope.principal_id,"episode_id":scope.episode_id,"attempt_id":scope.attempt_id,
               "tool":name,"request_sha256":hashlib.sha256(raw).hexdigest(),"state":"requested",
               "authority_receipt":None}
        self.audit.append(entry)
        try:
            receipt=self.authorize(scope,name,args)
            require(type(receipt) is dict and receipt.get("allowed") is True and
                    type(receipt.get("authority_seq")) is int and receipt["authority_seq"]>=0,
                    "TOOL_NOT_AUTHORIZED")
            entry["authority_receipt"]=dict(receipt)
            require(self.notices is not None,"NOTICES_UNAVAILABLE")
            if name=="notice.receive":
                require(not args,"TOOL_FIELDS");result=self.notices.receive(scope)
            else:
                require(set(args)=={"delivery_id","event_id"} and
                        all(type(v) is str for v in args.values()),"TOOL_FIELDS")
                result={"acknowledged":self.notices.acknowledge(scope,args["delivery_id"],args["event_id"]),
                        "meaning":"protocol receipt, not evidence of cognitive discovery"}
            entry["state"]="returned";return result
        except BaseException as exc:
            entry["state"]="rejected_or_failed";entry["error_type"]=type(exc).__name__;raise
