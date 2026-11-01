"""Read-only operation lookup/result on the existing durable dispatcher store.
These methods never launch, retry, acknowledge termination, or grade an analysis.
"""
from copy import deepcopy
from .jobs_v02 import JobStore as ExistingStore
from .contracts_v01 import require,nonempty

class JobStore(ExistingStore):
    def lookup(self,scope,operation_id,idempotency_key):
        require(nonempty(operation_id) and nonempty(idempotency_key),"OPERATION_ID")
        identity=self._scope(scope)
        with self._mutex:
            for row in self.data["rows"]:
                if row["scope"]!=identity:continue
                if row["operation_id"]==operation_id or row["idempotency_key"]==idempotency_key:
                    require(row["operation_id"]==operation_id and row["idempotency_key"]==idempotency_key,
                            "IDEMPOTENCY_CONFLICT")
                    return deepcopy(row)
            return None

    def result(self,scope,job_id):
        with self._mutex:
            row=self._row(scope,job_id)
            return {"schema":"bioduet-job-result-view/1","job_id":row["job_id"],
                    "operation_id":row["operation_id"],"request_sha256":row["request_sha256"],
                    "state":row["state"],"result":deepcopy(row["result"]),
                    "result_available":row["result"] is not None,
                    "late_result":any(e.get("kind")=="result_retained" and e.get("late") is True
                                      for e in row["events"]),
                    "cancel_acknowledged":row["cancel_acknowledged"],
                    "process_terminated":row["process_terminated"],
                    "scientific_validity":None,
                    "meaning":"Execution evidence only; accepted is not completed, exit zero is not scientific validity."}
