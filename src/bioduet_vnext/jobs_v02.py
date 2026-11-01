"""Dispatch claim closes accepted->OS launch crash gap. Frozen v01 remains unchanged."""
import uuid
from copy import deepcopy
from .jobs_v01 import JobStore as ExistingStore
from .contracts_v01 import require,nonempty
class JobStore(ExistingStore):
    def __init__(self,root):
        super().__init__(root)
        try:
            changed=False
            for row in self.data["rows"]:
                if row["state"]=="dispatching":
                    row["state"]="unknown";row["events"].append({"kind":"dispatch_reopened_unknown"})
                    changed=True
            if changed:self._save()
        except BaseException:self.close();raise
    def claim_dispatch(self,scope,job_id):
        with self._mutex:
            row=self._row(scope,job_id)
            require(row["state"]=="accepted" and row.get("dispatch_claim") is None,"DISPATCH_NOT_CLAIMABLE")
            claim={"claim_id":uuid.uuid4().hex,"request_sha256":row["request_sha256"],"state":"issued"}
            row["dispatch_claim"]=claim;row["state"]="dispatching"
            row["events"].append({"kind":"dispatch_claimed","claim_id":claim["claim_id"]})
            self._save() # If uncertain, caller must not launch or retry in this supervisor.
            return deepcopy(claim)
    def mark_started(self,scope,job_id,launcher_receipt,*,claim_id):
        with self._mutex:
            row=self._row(scope,job_id);claim=row.get("dispatch_claim")
            require(row["state"] in ("dispatching","cancel_requested") and type(claim) is dict and
                    claim["claim_id"]==claim_id and claim["state"]=="issued","DISPATCH_CLAIM_JOIN")
            require(type(launcher_receipt) is dict and type(launcher_receipt.get("pid")) is int and
                    launcher_receipt["pid"]>0 and type(launcher_receipt.get("start_ticks")) is str and
                    launcher_receipt["start_ticks"].isdigit(),"LAUNCH_IDENTITY")
            claim["state"]="observed"
            if row["state"]=="dispatching":row["state"]="running"
            row["events"].append({"kind":"started","claim_id":claim_id,"launcher":deepcopy(launcher_receipt)})
            self._save()
    def cancel(self,scope,job_id):
        with self._mutex:
            row=self._row(scope,job_id)
            if row["state"]!="dispatching":return super().cancel(scope,job_id)
            row["state"]="cancel_requested";row["cancel_acknowledged"]=True
            row["events"].append({"kind":"cancel_acknowledged","state":row["state"]})
            self._save();return deepcopy(row)
class JobDispatcher:
    """Trusted host callbacks; creates no processes itself and grants no resources."""
    def __init__(self,*,jobs,workspace,authorize_launch,launch,verify_launch):
        require(all(callable(f) for f in (authorize_launch,launch,verify_launch)),"LAUNCH_HOST_CALLBACKS")
        self.jobs=jobs;self.workspace=workspace;self.authorize=authorize_launch
        self.launch=launch;self.verify=verify_launch;self.audit=[]
    def start(self,scope,job_id):
        row=self.jobs.status(scope,job_id)
        if row["state"]!="accepted":
            self.audit.append({"kind":"not_relaunched","job_id":job_id,"state":row["state"]})
            return row
        raw,ref=self.workspace.read_ref(scope,row["request"]["code_ref"])
        proof=self.authorize(scope,deepcopy(row["request"]),ref)
        require(type(proof) is dict and proof.get("allowed") is True and nonempty(proof.get("scope_id")),
                "LAUNCH_NOT_AUTHORIZED")
        claim=self.jobs.claim_dispatch(scope,job_id)
        # launch is a Root-bound entry which must recheck its actual finite admission.
        # Exception/lost receipt does not prove absence of an external execution.
        try:
            receipt=self.launch(scope,deepcopy(row["request"]),deepcopy(claim),dict(proof))
            require(self.verify(scope,deepcopy(claim),receipt) is True,"LAUNCH_PROOF_UNVERIFIED")
            self.jobs.mark_started(scope,job_id,receipt,claim_id=claim["claim_id"])
        except BaseException as exc:
            self.audit.append({"kind":"launch_unresolved","job_id":job_id,"claim_id":claim["claim_id"],
                               "error_type":type(exc).__name__,"external_side_effects":"unknown"})
            raise
        self.audit.append({"kind":"launch_observed","job_id":job_id,"claim_id":claim["claim_id"]})
        return self.jobs.status(scope,job_id)
