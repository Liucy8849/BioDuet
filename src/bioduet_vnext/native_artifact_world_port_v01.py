"""Explicit native-artifact profile over the existing ScienceWorldPort/ActionBroker.
One World, one issued-context registry. The changed analysis actions are never
labelled with the legacy fixed-reference-run envelope/version.
"""
from copy import deepcopy
from labweave_eval.bioduet_world_port_v02 import ScienceWorldPort,BrokeredScienceWorld
from labweave_eval.world_port import ActionBroker
from labweave_eval.contract import Rejection
from labweave_eval.bw01_logical_v01 import safe_copy
from .native_science_world_v03 import PROFILE
from .contracts_v01 import require
CONTRACT="bioduet-native-artifact-world-port/1"
NAMES={"A01":"ReadCurrentResearchView","A02":"ReleaseSourceCertificate",
 "A03":"ReviseSourceBoundRecord","A04":"RegisterNativeCountsQCCandidate",
 "A06":"RecordParticipantChosenMethod","A11":"RegisterNativeAnalysisCandidate",
 "A12":"VerifyNativeArtifactBytes","A13":"RecordInternalCandidatePublication",
 "A14":"RestrictPriorResearchArtifact"}
class NativeArtifactWorldPort(ScienceWorldPort):
    def __init__(self,world):
        require(getattr(world,"profile",None)==PROFILE,"EXPLICIT_NATIVE_WORLD_PROFILE")
        super().__init__(world)
    def envelope(self,context,request):
        self.validate_context(context);request=safe_copy(request)
        if type(request) is not dict or request.get("action_id") not in NAMES:raise Rejection("ACTION_SCHEMA")
        action=request["action_id"]
        return {"contract_version":CONTRACT,"world_profile":PROFILE,
            "project_id":self.project_id,"episode_id":self.episode_id,
            "action":{"id":action,"name":NAMES[action],"version":"native-artifact-v1"},
            "request":request}
    def execute(self,context,envelope):
        self.validate_context(context);value=safe_copy(envelope)
        if type(value) is not dict or set(value)!={"contract_version","world_profile",
            "project_id","episode_id","action","request"} or type(value["request"]) is not dict:
            raise Rejection("ENVELOPE_SCOPE_OR_SCHEMA")
        if self.envelope(context,value["request"])!=value:raise Rejection("NATIVE_ACTION_PROFILE_OR_BINDING")
        result=self.world.execute(context.actor,value["request"])
        self.audit.append({"tick":self.world.tick,"actor":context.actor,"profile":PROFILE,
            "contract_version":CONTRACT,"request":deepcopy(value["request"]),"result":deepcopy(result)})
        return result
class BrokeredNativeArtifactWorld(BrokeredScienceWorld):
    def __init__(self,world):
        self._port=NativeArtifactWorldPort(world)
        self._contexts={actor:self._port.issue_context(actor) for actor in ("A","H")}
        self._broker=ActionBroker(self._port)
