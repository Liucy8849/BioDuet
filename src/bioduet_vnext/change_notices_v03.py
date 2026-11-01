"""Durable controller-owned minimal notices; at-least-once delivery, explicit ack.
Held private directory and single-writer lock. Actual world/participant transport
and independent collector trust remain host responsibilities. No scientific claims.
"""
import os,json,uuid,time,stat,fcntl,threading
from copy import deepcopy
from pathlib import Path
from dataclasses import asdict
from .contracts_v01 import require,nonempty,sha

def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

class DurableChangeNotices:
    LIMIT=1024*1024
    def __init__(self,root,*,information_mode,episode_id,attempt_id,project_id,verify_commit,authorize_read):
        require(information_mode in ("change_notice","analysis_anomaly"),"INFORMATION_MODE")
        require(all(nonempty(x) for x in (episode_id,attempt_id,project_id)),"NOTICE_IDENTITY")
        require(callable(verify_commit) and callable(authorize_read),"TRUSTED_NOTICE_CALLBACKS")
        self.identity=dict(episode_id=episode_id,attempt_id=attempt_id,project_id=project_id)
        self.mode=information_mode;self.verify=verify_commit;self.authorize=authorize_read
        self._scopes={};self._mutex=threading.RLock();self._dir=None;self._lock=None;self._poisoned=False
        root=Path(root);require(root.is_absolute(),"NOTICE_ROOT")
        root.mkdir(mode=0o700,exist_ok=True)
        try:
            self._dir=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            self._private(os.fstat(self._dir),directory=True)
            self._lock=os.open("writer.lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=self._dir)
            self._private(os.fstat(self._lock))
            fcntl.flock(self._lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:
                fd=os.open("notices.json",os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self._dir)
            except FileNotFoundError:
                self.data={"schema":"bioduet-durable-notices/1","identity":self.identity,
                           "mode":self.mode,"events":{},"deliveries":[],"audit":[]}
                self._commit(deepcopy(self.data))
            else:
                with os.fdopen(fd,"rb") as stream:
                    self._private(os.fstat(stream.fileno()))
                    raw=stream.read(self.LIMIT+1);require(len(raw)<=self.LIMIT,"NOTICE_LEDGER_LIMIT")
                data=json.loads(raw);self._validate(data);self.data=data
        except BaseException:
            self.close();raise
    @staticmethod
    def _private(st,*,directory=False):
        require(st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)&0o077==0,"NOTICE_PRIVATE")
        require((stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode) and st.st_nlink==1),
                "NOTICE_FILE_TYPE")
    @staticmethod
    def _event(event):
        require(type(event) is dict and set(event)=={"event_id","object_id","revision","event_kind","source_sha256"},
                "NOTICE_FIELDS")
        require(all(nonempty(event[k]) for k in ("event_id","object_id","event_kind")) and
                type(event["revision"]) is int and event["revision"]>=1 and sha(event["source_sha256"]),"NOTICE_VALUES")
    def _validate(self,data):
        require(type(data) is dict and set(data)=={"schema","identity","mode","events","deliveries","audit"} and
                data["schema"]=="bioduet-durable-notices/1" and data["identity"]==self.identity and
                data["mode"]==self.mode,"NOTICE_LEDGER_IDENTITY")
        require(type(data["events"]) is dict and type(data["deliveries"]) is list and
                type(data["audit"]) is list and all(type(x) is dict for x in data["audit"]),"NOTICE_LEDGER")
        for key,event in data["events"].items():
            self._event(event);require(key==event["event_id"],"NOTICE_EVENT_KEY")
        keys=set();ids=set()
        for row in data["deliveries"]:
            require(type(row) is dict and set(row)=={"delivery_id","event_id","recipient","state","attempts"},
                    "NOTICE_DELIVERY")
            rec=row["recipient"]
            require(type(rec) is dict and set(rec)==set(self.identity)|{"principal_id","role"} and
                    all(rec[k]==v for k,v in self.identity.items()) and nonempty(rec["principal_id"]) and
                    rec["role"] in ("A","H"),"NOTICE_RECIPIENT")
            key=(row["event_id"],rec["principal_id"])
            require(row["event_id"] in data["events"] and nonempty(row["delivery_id"]) and
                    row["delivery_id"] not in ids and key not in keys and row["state"] in ("pending","acked","suppressed")
                    and type(row["attempts"]) is int and row["attempts"]>=0,"NOTICE_DELIVERY")
            require((self.mode=="analysis_anomaly")== (row["state"]=="suppressed"),"NOTICE_MODE_STATE")
            keys.add(key);ids.add(row["delivery_id"])
    def _commit(self,draft):
        require(not self._poisoned and self._dir is not None,"NOTICE_STORE_UNAVAILABLE")
        self._validate(draft);raw=encoded(draft);require(len(raw)<=self.LIMIT,"NOTICE_LEDGER_LIMIT")
        temp=uuid.uuid4().hex+".partial"
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self._dir)
        renamed=False
        try:
            with os.fdopen(fd,"wb") as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,"notices.json",src_dir_fd=self._dir,dst_dir_fd=self._dir);renamed=True
            os.fsync(self._dir)
        except BaseException:
            if renamed:self._poisoned=True
            else:
                try:os.unlink(temp,dir_fd=self._dir)
                except FileNotFoundError:pass
            raise
        self.data=draft
    def bind(self,scope):
        with self._mutex:
            require(all(getattr(scope,k)==v for k,v in self.identity.items()) and scope.role in ("A","H")
                    and scope.principal_id not in self._scopes,"NOTICE_SCOPE")
            self._scopes[scope.principal_id]=scope
    def _scope(self,scope):
        require(not self._poisoned and self._dir is not None,"NOTICE_STORE_UNAVAILABLE")
        require(self._scopes.get(scope.principal_id) is scope,"NOTICE_SCOPE")
    def committed_change(self,scope,event,receipt):
        with self._mutex:
            self._scope(scope);self._event(event);event=deepcopy(event)
            require(self.verify(scope,deepcopy(event),receipt) is True,"NOTICE_COMMIT_UNVERIFIED")
            data=deepcopy(self.data);prior=data["events"].get(event["event_id"])
            require(prior is None or prior==event,"NOTICE_EVENT_CONFLICT")
            if any(x["event_id"]==event["event_id"] and x["recipient"]["principal_id"]==scope.principal_id
                   for x in data["deliveries"]):return False
            data["events"][event["event_id"]]=event
            row={"delivery_id":uuid.uuid4().hex,"event_id":event["event_id"],"recipient":asdict(scope),
                 "state":"pending" if self.mode=="change_notice" else "suppressed","attempts":0}
            data["deliveries"].append(row)
            data["audit"].append({"kind":"notice_queued" if self.mode=="change_notice" else "automatic_notice_suppressed",
                                  "delivery_id":row["delivery_id"]})
            self._commit(data);return self.mode=="change_notice"
    def receive(self,scope):
        with self._mutex:
            self._scope(scope)
            for index,row in enumerate(self.data["deliveries"]):
                if row["state"]!="pending" or row["recipient"]!=asdict(scope):continue
                event=self.data["events"][row["event_id"]]
                if self.authorize(scope,event["object_id"],event["revision"]) is not True:continue
                data=deepcopy(self.data);current=data["deliveries"][index];current["attempts"]+=1
                now=time.monotonic_ns()
                data["audit"].append({"kind":"notice_reply","delivery_id":row["delivery_id"],
                                      "monotonic_ns":now,"meaning":"server reply; receipt not yet acknowledged"})
                self._commit(data)
                return {"schema":"bioduet-change-notice/1","delivery_id":row["delivery_id"],
                        **self.identity,"event":deepcopy(event),"delivery_attempt":current["attempts"],
                        "server_reply_monotonic_ns":now,
                        "meaning":"an object changed; query the authorized object for details"}
            return None
    def acknowledge(self,scope,delivery_id,event_id):
        with self._mutex:
            self._scope(scope)
            for index,row in enumerate(self.data["deliveries"]):
                if row["delivery_id"]!=delivery_id:continue
                require(row["recipient"]==asdict(scope) and row["event_id"]==event_id and
                        row["state"]!="suppressed" and row["attempts"]>0,"NOTICE_ACK_JOIN")
                if row["state"]=="acked":return False
                data=deepcopy(self.data);data["deliveries"][index]["state"]="acked"
                data["audit"].append({"kind":"consumer_acknowledged","delivery_id":delivery_id,
                     "monotonic_ns":time.monotonic_ns(),
                     "meaning":"protocol receipt, not evidence of cognitive discovery"})
                self._commit(data);return True
            raise ValueError("NOTICE_ACK_JOIN")
    def close(self):
        for name in ("_lock","_dir"):
            fd=getattr(self,name,None)
            if fd is not None:os.close(fd);setattr(self,name,None)
