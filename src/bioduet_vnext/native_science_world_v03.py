"""Single existing recovery World with an explicit native-artifact profile.
This is an initializer/receipt extension of the canonical World, not another
authority or a science executor. No R00/Q00/P00 is invented. New-code execution
and method claims stay unverified until independent evidence actually joins.
"""
from copy import deepcopy
from pathlib import Path
import json
from bioduet_eval.bioduet_recovery_world_v02 import RecoveryWorld as ExistingRecoveryWorld
from bioduet_eval.bw01_logical_v01 import safe_copy
from bioduet_eval.bioduet_window_v01 import sha
from .contracts_v01 import require

PROFILE="bioduet-native-artifact-recovery-world/1"
GUIDE={
 "A01":"Read your currently authorized research records, artifact and publication metadata.",
 "A02":"H: release a source certificate available in your own research view; payload evidence_ref.",
 "A03":"H: revise one authorized record using library_id, expected_version, condition and a source-based reason.",
 "A04":"A: register an actual counts-QC candidate you generated; this call snapshots files, it does not run analysis.",
 "A06":"A: record the design and method specification you chose; no analysis is run by this metadata action.",
 "A11":"A: register an actual analysis candidate you generated; this call snapshots files, it does not run analysis.",
 "A12":"A: verify stored artifact bytes; this does not prove execution or scientific validity.",
 "A13":"A: record an internal candidate publication of a current artifact with your interpretation and optional supersession.",
 "A14":"H: restrict a specific prior artifact/publication, giving your reason; no impact closure is supplied."
}
REGISTER_FIELDS={"collection_version","design_version","code_path","result_path",
                 "declared_read_set","method_spec_json","execution_ref"}
class NativeArtifactRecoveryWorld(ExistingRecoveryWorld):
    profile=PROFILE
    def __init__(self,*,dataset,declared_records,H_source_records,H_source_sha256,
                 human_scope_library_ids,artifact_snapshot,verify_artifact_snapshot,
                 evidence_at=0):
        require(callable(artifact_snapshot) and callable(verify_artifact_snapshot),"TRUSTED_SNAPSHOT_CALLBACKS")
        require(type(evidence_at) is int and evidence_at>=0,"SOURCE_AVAILABILITY_TIME")
        require(type(dataset) is dict and type(dataset.get("samples")) is list,"REAL_DATASET")
        self.dataset=deepcopy(dataset);self.samples={}
        for r in declared_records:
            require(set(r)=={"library_id","donor_id","condition"} and
                    all(type(r[x]) is str and r[x] for x in r) and
                    r["condition"] in ("control","stim") and r["library_id"] not in self.samples,
                    "DECLARED_LIBRARY_RECORD")
            self.samples[r["library_id"]]=dict(r,version=1)
        require(set(self.samples)=={r["library_id"] for r in dataset["samples"]},"DATASET_LIBRARY_SET")
        require(all(type(r.get("library_id")) is str and r.get("condition") in ("control","stim") for r in H_source_records),"H_SOURCE_CONDITION")
        source={r["library_id"]:r["condition"] for r in H_source_records}
        require(len(source)==len(H_source_records) and set(source)<=set(self.samples),"H_SOURCE_RECORDS")
        require(type(H_source_sha256) is str and len(H_source_sha256)==64,"H_SOURCE_IDENTITY")
        self.human_scope=set(human_scope_library_ids)
        require(self.human_scope<=set(source),"HUMAN_SOURCE_SCOPE")
        self.evidence={"id":"E01","source_kind":"simulated_researcher_using_published_record_metadata",
                       "source_ref":H_source_sha256,
                       "conditions":{k:source[k] for k in sorted(self.human_scope)}}
        self.tick=0;self.expires_at=None;self.evidence_at=evidence_at
        self.collection_version=1
        self.counts={"id":"L01","version":1,"identity":dataset["counts"]["sha256"]}
        # No inference unit, statistical formula, pairing or method is chosen here.
        self.design={"id":"D01","version":0,"collection_version":1,"conditions":{},
                     "analysis_unit":None,"paired":None,"method_spec_json":None}
        self.public_evidence=None;self.artifacts={};self.publications={};self.publication_id=None
        self.usage={};self._files={};self.history=[];self.operations={}
        self.native_operation_failures=[];self._pending_native={}
        self.prehistory_identity={"producer":"no_preexisting_artifacts_imported",
                                  "R00_Q00_P00_created":False}
        self._artifact_snapshot=artifact_snapshot
        self._verify_artifact_snapshot=verify_artifact_snapshot
        self.initial_snapshot=self.snapshot()

    def observe(self,actor):
        self.available_actions(actor)
        view=self.snapshot();view["counts"]=deepcopy(self.counts)
        view["action_profile"]=PROFILE
        view["analysis_contract"]={"profile":PROFILE,"actions":deepcopy(GUIDE),
            "execution":"Native file/terminal tools execute participant-authored code; registration records candidates only.",
            "validation":"File identity, actual execution, scientific method and interpretation are separate evidence layers.",
            "publication":"Publications here are internal research records, not external publication receipts."}
        if actor=="H":view["private_evidence"]=deepcopy(self.evidence) if self.tick>=self.evidence_at else None
        return view

    def _commit_native(self,actor,request,before,result):
        key=(actor,request["operation_id"])
        self.operations[key]=(sha(request),deepcopy(result))
        self.history.append({"tick":self.tick,"actor":actor,"request":deepcopy(request),
                             "before":before,"after":self.snapshot(),"result":deepcopy(result)})
        self._pending_native.pop(key,None)
        return deepcopy(result)

    def execute(self,actor,request):
        request=safe_copy(request)
        if type(request) is not dict or request.get("action_id") not in ("A04","A06","A11","A12","A13"):
            return super().execute(actor,request)
        action=request["action_id"]
        if action not in self.available_actions(actor):
            return {"status":"rejected","reason":"CAPABILITY_UNAVAILABLE"}
        if set(request)!={"action_id","operation_id","payload"} or type(request["operation_id"]) is not str or not 0<len(request["operation_id"])<=128 or type(request["payload"]) is not dict:
            return {"status":"rejected","reason":"ACTION_SCHEMA"}
        key=(actor,request["operation_id"]);signature=sha(request);payload=request["payload"]
        if key in self.operations:
            previous,result=self.operations[key]
            return deepcopy(result) if previous==signature else {"status":"rejected","reason":"IDEMPOTENCY_CONFLICT"}
        if key in self._pending_native:
            return {"status":"outcome_unknown","reason":"NATIVE_SNAPSHOT_PARTIAL_REQUIRES_HOST_INSPECTION",
                    "operation_id":request["operation_id"],"same_operation_resubmission_allowed":False}
        before=self.snapshot()
        if action=="A06":
            fields={"collection_version","conditions","analysis_unit","paired","method_spec_json"}
            if set(payload)!=fields or payload["collection_version"]!=self.collection_version or type(payload["collection_version"]) is not int:
                return {"status":"rejected","reason":"VERSION_OR_DESIGN_SCHEMA"}
            if type(payload["conditions"]) is not dict or set(payload["conditions"])!=set(self.samples) or any(v not in ("control","stim") for v in payload["conditions"].values()):
                return {"status":"rejected","reason":"DESIGN_LIBRARY_SET"}
            if type(payload["analysis_unit"]) is not str or not 0<len(payload["analysis_unit"])<=128 or type(payload["paired"]) is not bool or type(payload["method_spec_json"]) is not str:
                return {"status":"rejected","reason":"DESIGN_SCHEMA"}
            try:json.loads(payload["method_spec_json"])
            except (ValueError,TypeError):return {"status":"rejected","reason":"METHOD_SPEC_JSON"}
            self.design=dict(payload,id="D01",version=self.design["version"]+1)
            result={"status":"succeeded","design_version":self.design["version"],
                    "collection_version":self.collection_version,"scientific_method_approved":None}
        elif action in ("A04","A11"):
            if set(payload)!=REGISTER_FIELDS or any(type(payload[k]) is not int for k in ("collection_version","design_version")) or payload["collection_version"]!=self.collection_version:
                return {"status":"rejected","reason":"ARTIFACT_SCHEMA_OR_VERSION"}
            if type(payload["declared_read_set"]) is not dict or type(payload["method_spec_json"]) is not str or type(payload["execution_ref"]) not in (dict,str):
                return {"status":"rejected","reason":"ARTIFACT_PROVENANCE_SCHEMA"}
            if action=="A11" and (payload["design_version"]!=self.design["version"] or self.design["version"]==0 or self.design["collection_version"]!=self.collection_version):
                return {"status":"rejected","reason":"DESIGN_VERSION"}
            try:json.loads(payload["method_spec_json"])
            except (ValueError,TypeError):return {"status":"rejected","reason":"METHOD_SPEC_JSON"}
            self._pending_native[key]=signature
            try:
                # The trusted host snapshots existing participant files; it must never run code.
                code=self._artifact_snapshot(actor,payload["code_path"],request["operation_id"],"code")
                output=self._artifact_snapshot(actor,payload["result_path"],request["operation_id"],"result")
                for item in (code,output):
                    require(type(item) is dict and set(item)=={"path","bytes","sha256","snapshot_kind"} and
                            type(item["path"]) is str and type(item["bytes"]) is int and item["bytes"]>=0 and
                            type(item["sha256"]) is str and len(item["sha256"])==64 and
                            item["snapshot_kind"]=="existing_file_bytes_not_execution_proof",
                            "TRUSTED_FILE_SNAPSHOT_NOT_FAKE_JOB_RECEIPT")
                aid=("Q" if action=="A04" else "R")+str(sum(x["kind"]==("counts_qc" if action=="A04" else "analysis") for x in self.artifacts.values())+1).zfill(2)
                item={"id":aid,"kind":"counts_qc" if action=="A04" else "analysis",
                      "status":"candidate","collection_version":payload["collection_version"],
                      "design_version":payload["design_version"],"counts_sha256":self.counts["identity"],
                      "result_sha256":output["sha256"],"code_sha256":code["sha256"],
                      "code_bytes":code["bytes"],"result_bytes":output["bytes"],
                      "declared_read_set":deepcopy(payload["declared_read_set"]),
                      "method_spec_json":payload["method_spec_json"],
                      "participant_declared_execution_ref":deepcopy(payload["execution_ref"]),
                      "actual_execution_verified":None,"verified_method_equivalence":None,
                      "scientific_validity":None,"mechanically_verified":False,
                      "producer":"evaluated_participant_submitted_native_artifact",
                      "source_kind":"actual_file_snapshot_with_unverified_execution_claim"}
                self.artifacts[aid]=item;self._files[aid]=output;self.usage[aid]="current"
                result={"status":"succeeded","artifact":deepcopy(item),
                        "metadata_committed":True,"actual_analysis_executed_by_this_action":False}
            except Exception as exc:
                self.native_operation_failures.append({"actor":actor,"operation_id":request["operation_id"],
                    "request_sha256":signature,"error_type":type(exc).__name__,
                    "partial_snapshots_preserved":True,"execution_outcome_not_inferred":True})
                return {"status":"outcome_unknown","operation_id":request["operation_id"],
                        "reason":"SNAPSHOT_OR_REGISTRATION_INCOMPLETE","error_type":type(exc).__name__}
        elif action=="A12":
            if set(payload)!={"artifact_id"} or type(payload["artifact_id"]) is not str or payload["artifact_id"] not in self.artifacts:
                return {"status":"rejected","reason":"ARTIFACT_ID"}
            aid=payload["artifact_id"];valid=self._verify_artifact_snapshot(deepcopy(self._files[aid]))
            require(type(valid) is bool,"EXACT_SNAPSHOT_VERIFIER_BOOL")
            self.artifacts[aid]["mechanically_verified"]=valid
            result={"status":"succeeded","artifact_id":aid,"bytes_valid":valid,
                    "actual_execution_verified":self.artifacts[aid]["actual_execution_verified"],
                    "scientific_validity":None}
        else:
            fields={"run_id","expected_collection_version","expected_design_version","interpretation","supersedes_run_id"}
            if set(payload)!=fields or type(payload["run_id"]) is not str or payload["run_id"] not in self.artifacts or any(type(payload[k]) is not int for k in ("expected_collection_version","expected_design_version")):
                return {"status":"rejected","reason":"PUBLICATION_SCHEMA"}
            run=self.artifacts[payload["run_id"]]
            if run["kind"]!="analysis" or not run["mechanically_verified"] or self.usage[run["id"]]=="restricted":
                return {"status":"rejected","reason":"ARTIFACT_NOT_CURRENT_OR_BYTES_UNVERIFIED"}
            if payload["expected_collection_version"]!=self.collection_version or payload["expected_design_version"]!=self.design["version"] or run["collection_version"]!=self.collection_version or run["design_version"]!=self.design["version"]:
                return {"status":"rejected","reason":"VERSION_CONFLICT"}
            old=payload["supersedes_run_id"]
            if old is not None and (type(old) is not str or old not in self.artifacts or old==run["id"]):
                return {"status":"rejected","reason":"SUPERSESSION_REFERENCE"}
            if type(payload["interpretation"]) is not str or not 0<len(payload["interpretation"])<=8192:
                return {"status":"rejected","reason":"INTERPRETATION"}
            pid="P"+str(len(self.publications)+1).zfill(2)
            pub={"id":pid,"kind":"publication","run_id":run["id"],"collection_version":self.collection_version,
                 "design_version":self.design["version"],"interpretation":payload["interpretation"],
                 "supersedes_run_id":old,"producer":"evaluated_agent",
                 "publication_scope":"internal_candidate_record_not_external_publication",
                 "execution_and_scientific_validation":"pending_independent_evidence"}
            self.publications[pid]=pub;self.publication_id=pid;self.usage[pid]="current"
            result={"status":"succeeded","publication":deepcopy(pub),"metadata_committed":True,
                    "scientific_validity":None}
        return self._commit_native(actor,request,before,result)
