"""Protected-entry business driver for the ONE real scientific host.
No Root authority is implemented here. A Root-owned, hash-frozen adapter supplies
only current admission verification and safe resource-authority observations.
The existing Root authority must be passively READY before its controller grants
this fresh host stage; model/R/Actor stages remain separately controlled.
"""
import argparse,os,stat,time,math,json,hashlib,importlib.util,sys
from pathlib import Path

def protected(path,expected_sha=None,max_bytes=1048576):
    p=Path(path);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        if not(stat.S_ISREG(a.st_mode) and stat.S_IMODE(a.st_mode)==0o444 and
               a.st_uid!=os.getuid() and a.st_nlink==1 and a.st_size<=max_bytes):
            raise ValueError("ROOT_READONLY_FOREIGN_OWNER_INPUT_REQUIRED")
        raw=bytearray()
        while True:
            b=os.read(fd,65536)
            if not b:break
            raw.extend(b)
            if len(raw)>max_bytes:raise ValueError("PROTECTED_INPUT_LIMIT")
        z=os.fstat(fd);current=os.lstat(p)
        if any(getattr(a,k)!=getattr(z,k) or getattr(z,k)!=getattr(current,k)
               for k in ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")):
            raise ValueError("PROTECTED_INPUT_CHANGED")
        if expected_sha is not None and hashlib.sha256(raw).hexdigest()!=expected_sha:
            raise ValueError("PROTECTED_INPUT_SHA")
        return bytes(raw)
    finally:os.close(fd)
def ordinary_pin(row):
    p=Path(row["path"]);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        if not stat.S_ISREG(a.st_mode) or not 0<=a.st_size<=33554432:raise ValueError("FINITE_INPUT")
        out=bytearray()
        while True:
            b=os.read(fd,65536)
            if not b:break
            out.extend(b)
            if len(out)>33554432:raise ValueError("INPUT_LIMIT")
        z=os.fstat(fd);current=os.lstat(p)
        if any(getattr(a,k)!=getattr(z,k) or getattr(z,k)!=getattr(current,k)
               for k in ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")):
            raise ValueError("INPUT_CHANGED")
        if len(out)!=row["bytes"] or hashlib.sha256(out).hexdigest()!=row["sha256"]:
            raise ValueError("INPUT_IDENTITY")
        return bytes(out)
    finally:os.close(fd)
def emit_new(path,value):
    raw=(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,indent=2)+"\n").encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--proof",required=True)
    ap.add_argument("--proof-sha256",required=True);args=ap.parse_args()
    if os.getuid()!=1008 or os.getgroups()!=[]:raise ValueError("ROOT_DROPPED_ROLE_PROCESS_REQUIRED")
    proof=json.loads(protected(args.proof,args.proof_sha256))
    if proof["schema"]!="bioduet-root-native-science-host/1":raise ValueError("ROOT_HOST_SCHEMA")
    deadline=proof["unit_deadline_monotonic"]
    if type(deadline) not in (int,float) or not math.isfinite(deadline) or not time.monotonic()<deadline:
        raise ValueError("CURRENT_FINITE_UNIT_WINDOW")
    if proof["source_kind"]!="real_public_data_with_declared_simulated_researcher":
        raise ValueError("REAL_SCIENCE_HOST_PROFILE")
    source_manifest=json.loads(ordinary_pin(proof["host_source_manifest"]))
    for row in source_manifest["source_refs"]:ordinary_pin(row)
    for root in proof["readonly_source_roots"]:
        p=Path(root)
        if not p.is_absolute() or p.is_symlink():raise ValueError("ROOT_READONLY_SOURCE_LAYOUT")
        sys.path.insert(0,str(p))
    # The adapter is not a key loader, science planner, World or process launcher.
    adapter_ref=proof["Root_authority_adapter"]
    protected(adapter_ref["path"],adapter_ref["sha256"])
    spec=importlib.util.spec_from_file_location("frozen_root_science_host_authority",adapter_ref["path"])
    authority=importlib.util.module_from_spec(spec);spec.loader.exec_module(authority)
    if authority.CONTRACT!="bioduet-root-current-host-authority/1":raise ValueError("ROOT_AUTHORITY_CONTRACT")
    if not callable(authority.verify_current_admission) or not callable(authority.authorize_resource):
        raise ValueError("ROOT_CURRENT_AUTHORITY_REQUIRED")
    from bioduet_vnext.science_http_transport_v01 import CurrentHTTPTransport
    from bioduet_vnext.scoped_study_http_v03 import ScopedStudyHTTPService
    from bioduet_vnext.native_science_host_composition_v08 import NativeScienceHostComposition
    out=Path(proof["host_output_root"])
    if not out.is_absolute() or out.exists():raise ValueError("FRESH_PROTECTED_HOST_OUTPUT")
    out.mkdir(mode=0o700)
    transport=CurrentHTTPTransport(out/"transport-contexts",
        role_proxy_journal_roots=proof["role_proxy_journal_roots"])
    holder={}
    def build_endpoint(admission):
        binding=json.loads(ordinary_pin(proof["science_bindings"]))
        composition=NativeScienceHostComposition(root=out/"composition",bindings=binding,
            actual_admission=admission,authorize_resource=authority.authorize_resource,
            transport_binding_factory=transport.bind)
        holder["composition"]=composition
        return composition.endpoint
    service=ScopedStudyHTTPService(role_capability_digests=proof["role_capability_digests"],
        verify_actual_admission=authority.verify_current_admission,endpoint_factory=build_endpoint,
        final_deadline_monotonic=deadline,transport_recorder=transport,max_handlers=proof["max_handlers"])
    passive=service.bind_passive(port=0)
    emit_new(out/"passive-ready.json",{"schema":"bioduet-science-host-passive-ready/1",
        **passive,"scope_id":proof["proposed_host_scope_id"],"models":0,"science_business_started":False})
    try:
        go_path=Path(proof["controller_GO_path"])
        while time.monotonic()<deadline and not go_path.exists():
            service.server.handle_request()
        if not go_path.exists():raise TimeoutError("NO_ACTUAL_HOST_CONTROLLER_GO")
        # GO is Root protected and actual; its grant hash is never predicted in READY.
        go=json.loads(protected(go_path))
        if go["nonce"]!=proof["controller_nonce"]:raise ValueError("EXACT_CURRENT_CONTROLLER_GO")
        admission=go["actual_admission"]
        if admission["scope_id"]!=proof["proposed_host_scope_id"]:
            raise ValueError("EXACT_CURRENT_HOST_SCOPE")
        service.activate(admission)
        composition=holder["composition"]
        emit_new(out/"business-ready.json",{"schema":"bioduet-science-host-business-ready/1",
            "world_binding_ref":composition.binding_ref,"role_tasks":composition.role_tasks,
            "role_native_roots":{r:str(p) for r,p in composition.native_roots.items()},
            "role_input_materialization":composition.public_input_refs,
            "actual_host_scope_id":admission["scope_id"],"actual_deadline_monotonic":composition.deadline,
            "Root_must_readonly_bind_role_data_and_freeze_actual_actor_proofs":True,
            "native_A_H_model_R_started_by_this_host":False,"models":0})
        service.serve_until(lambda:Path(proof["controller_STOP_path"]).exists())
        composition.export_private_state()
    finally:
        service.active=False
        service.server.server_close()
        composition=holder.get("composition")
        if composition is not None:
            try:
                if not (composition.root/"host-state.json").exists():composition.export_private_state()
            except Exception as exc:
                emit_new(out/"partial-host-state-capture-error.json",{"error_type":type(exc).__name__,
                    "state":"partial_evidence_preserved_current_mutation_outcomes_require_independent_inspection"})
            finally:composition.close()
        # Root independently captures every process birth/cgroup/namespace/tmpfs;
        # neither server_close nor FD close is a retirement attestation.
if __name__=="__main__":main()
