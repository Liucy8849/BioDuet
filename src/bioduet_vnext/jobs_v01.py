"""Durable operation receipts. Execution is provided by a separately granted launcher."""
import os,json,hashlib,uuid,threading
from pathlib import Path
from copy import deepcopy
from .contracts_v01 import require,sha,nonempty

def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

class JobStore:
    def __init__(self,root):
        self.root=Path(root)
        require(self.root.is_absolute() and not self.root.is_symlink(),"JOB_ROOT")
        self.root.mkdir(mode=0o700,exist_ok=True)
        self.path=self.root/"operations.json";self.lock_path=self.root/"writer.lock"
        self._mutex=threading.RLock()
        # One supervisor owns the store; a second writer fails rather than racing state.
        import fcntl
        self._fd=os.open(self.lock_path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(self._fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:os.close(self._fd);raise
        self.data={"schema":"bioduet.job-store/1","rows":[]}
        if self.path.exists():
            require(not self.path.is_symlink() and self.path.stat().st_size<=8*1024*1024,"JOB_LEDGER_FILE")
            self.data=json.loads(self.path.read_bytes())
            require(self.data.get("schema")=="bioduet.job-store/1" and type(self.data.get("rows")) is list,"JOB_LEDGER_SCHEMA")
            # A supervisor restart cannot infer whether an external execution stopped.
            for row in self.data["rows"]:
                if row["state"] in ("running","cancel_requested"):
                    row["state"]="unknown";row["events"].append({"kind":"supervisor_reopened_unknown"})
            self._save()

    def _save(self):
        raw=encoded(self.data);require(len(raw)<=8*1024*1024,"JOB_LEDGER_LIMIT")
        temp=self.root/(uuid.uuid4().hex+".partial")
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,self.path)
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    @staticmethod
    def _scope(scope):
        return {key:getattr(scope,key) for key in ("episode_id","attempt_id","project_id","principal_id","role")}

    def submit(self,scope,operation_id,idempotency_key,request):
        with self._mutex:
            require(scope.role in ("A","H"),"JOB_ROLE")
            require(nonempty(operation_id) and nonempty(idempotency_key),"OPERATION_ID")
            require(type(request) is dict and set(request)=={"code_ref","input_refs","argv","environment_ref"},"JOB_REQUEST")
            require(type(request["code_ref"]) is dict and sha(request["code_ref"].get("sha256")),"CODE_REF")
            require(type(request["input_refs"]) is list,"JOB_INPUTS")
            require(type(request["argv"]) is list and bool(request["argv"]) and
                    all(type(x) is str and "\x00" not in x for x in request["argv"]),"JOB_ARGV")
            require(nonempty(request["environment_ref"]),"JOB_ENVIRONMENT")
            scope_ref=self._scope(scope);request_sha=hashlib.sha256(encoded(request)).hexdigest()
            for row in self.data["rows"]:
                if row["scope"]==scope_ref and (row["operation_id"]==operation_id or row["idempotency_key"]==idempotency_key):
                    require(row["operation_id"]==operation_id and row["idempotency_key"]==idempotency_key
                            and row["request_sha256"]==request_sha,"IDEMPOTENCY_CONFLICT")
                    return deepcopy(row),True
            row={"job_id":uuid.uuid4().hex,"scope":scope_ref,"operation_id":operation_id,
                 "idempotency_key":idempotency_key,"request":deepcopy(request),"request_sha256":request_sha,
                 "state":"accepted","events":[{"kind":"accepted"}],"result":None,
                 "cancel_acknowledged":False,"process_terminated":False}
            self.data["rows"].append(row);self._save();return deepcopy(row),False

    def _row(self,scope,job_id):
        for row in self.data["rows"]:
            if row["job_id"]==job_id:
                require(row["scope"]==self._scope(scope),"JOB_SCOPE")
                return row
        raise ValueError("JOB_NOT_FOUND")

    def status(self,scope,job_id):
        with self._mutex:return deepcopy(self._row(scope,job_id))

    def mark_started(self,scope,job_id,launcher_receipt):
        with self._mutex:
            row=self._row(scope,job_id);require(row["state"]=="accepted","JOB_NOT_STARTABLE")
            require(type(launcher_receipt) is dict and type(launcher_receipt.get("pid")) is int and
                    type(launcher_receipt.get("start_ticks")) is str,"LAUNCH_IDENTITY")
            row["state"]="running";row["events"].append({"kind":"started","launcher":deepcopy(launcher_receipt)})
            self._save()

    def cancel(self,scope,job_id):
        with self._mutex:
            row=self._row(scope,job_id)
            if row["state"]=="accepted":
                row["state"]="cancelled";row["process_terminated"]=True
            elif row["state"] in ("running","unknown"):
                row["state"]="cancel_requested"
            row["cancel_acknowledged"]=True
            row["events"].append({"kind":"cancel_acknowledged","state":row["state"]})
            self._save();return deepcopy(row)

    def mark_terminated(self,scope,job_id,proof):
        with self._mutex:
            row=self._row(scope,job_id)
            require(proof.get("launcher_reaped") is True and proof.get("cgroup_empty") is True,"TERMINATION_UNPROVEN")
            row["process_terminated"]=True
            if row["result"] is None:row["state"]="cancelled"
            row["events"].append({"kind":"terminated","proof":deepcopy(proof)})
            self._save()

    def complete(self,scope,job_id,result):
        with self._mutex:
            row=self._row(scope,job_id)
            require(row["state"] in ("running","cancel_requested","unknown"),"RESULT_STATE")
            require(type(result) is dict and set(result)=={"request_sha256","exit_code","artifacts"},"RESULT_SCHEMA")
            require(result["request_sha256"]==row["request_sha256"],"RESULT_INPUT_JOIN")
            require(type(result["exit_code"]) is int and type(result["artifacts"]) is list,"RESULT_VALUES")
            late=row["state"] in ("cancel_requested","unknown")
            row["result"]=deepcopy(result);row["state"]="completed" if result["exit_code"]==0 else "failed"
            row["events"].append({"kind":"result_retained","late":late,
                                  "input_refs":row["request"]["input_refs"]})
            self._save();return deepcopy(row)

    def close(self):
        if self._fd is not None:os.close(self._fd);self._fd=None
