"""BioDuet vNext boundary contracts. Pure validators, no scientific planning."""
from dataclasses import dataclass
from collections.abc import Mapping
import re

class ContractError(ValueError): pass

def require(ok, reason):
    if not ok: raise ContractError(reason)

def nonempty(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 512

def sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None

@dataclass(frozen=True)
class Scope:
    episode_id: str
    attempt_id: str
    project_id: str
    principal_id: str
    role: str

    def __post_init__(self):
        require(all(nonempty(x) for x in (self.episode_id,self.attempt_id,
                  self.project_id,self.principal_id)), "SCOPE_ID")
        require(self.role in ("A","H","W","evaluator"), "ROLE")

@dataclass(frozen=True)
class ArtifactRef:
    object_id: str
    revision: int
    sha256: str
    size_bytes: int

    def __post_init__(self):
        require(nonempty(self.object_id), "OBJECT_ID")
        require(type(self.revision) is int and self.revision >= 1, "REVISION")
        require(sha(self.sha256), "SHA256")
        require(type(self.size_bytes) is int and self.size_bytes >= 0, "SIZE")

# Controller-owned registry: roles/semantics are never guessed from the action ID.
class ActionProfiles:
    def __init__(self, profiles):
        self._profiles = {}
        for identity, rows in profiles.items():
            require(type(identity) is tuple and len(identity)==2 and
                    all(nonempty(x) for x in identity), "PROFILE_ID")
            require(isinstance(rows, Mapping), "ACTION_ROWS")
            self._profiles[identity] = {}
            for action_id, declaration in rows.items():
                require(nonempty(action_id) and type(declaration) is tuple and len(declaration)==2,
                        "ACTION_DECLARATION")
                role, semantic = declaration
                require(role in ("A","H","W") and nonempty(semantic), "ACTION_ROLE_SEMANTIC")
                self._profiles[identity][action_id] = (role,semantic)

    def resolve(self, profile_id, action_schema_version, action_id, role, semantic_action):
        rows = self._profiles.get((profile_id, action_schema_version))
        require(rows is not None, "UNKNOWN_PROFILE")
        expected = rows.get(action_id)
        require(expected is not None, "UNKNOWN_ACTION")
        require(expected == (role, semantic_action), "ACTION_SEMANTICS_MISMATCH")
        return semantic_action

def validate_request(value, scope, registry):
    require(type(value) is dict, "REQUEST_OBJECT")
    expected = {"schema","profile_id","action_schema_version","action_id","semantic_action",
                "episode_id","attempt_id","project_id","principal_id","operation_id",
                "idempotency_key","observed_versions","input_refs","payload"}
    require(set(value)==expected and value["schema"]=="bioduet.request/1", "REQUEST_SCHEMA")
    for key in ("episode_id","attempt_id","project_id","principal_id"):
        require(value[key]==getattr(scope,key), "REQUEST_SCOPE_"+key)
    for key in ("operation_id","idempotency_key"):
        require(nonempty(value[key]), key.upper())
    require(type(value["payload"]) is dict, "PAYLOAD")
    require(type(value["observed_versions"]) is dict and
            all(nonempty(k) and type(v) is int and v>=0 for k,v in value["observed_versions"].items()),
            "OBSERVED_VERSIONS")
    require(type(value["input_refs"]) is list, "INPUT_REFS")
    seen=set()
    for row in value["input_refs"]:
        require(type(row) is dict and set(row)=={"object_id","revision","sha256","size_bytes"},
                "ARTIFACT_SCHEMA")
        ref=ArtifactRef(**row)
        require(ref.object_id not in seen, "DUPLICATE_INPUT")
        seen.add(ref.object_id)
    registry.resolve(value["profile_id"],value["action_schema_version"],value["action_id"],
                     scope.role,value["semantic_action"])
    return value

# Structural ports intentionally contain no default implementation or role actions.
class WorldPort:
    def execute(self, scope, request): raise NotImplementedError
class ParticipantPort:
    def observe(self, observation): raise NotImplementedError
    def step(self): raise NotImplementedError
    def close(self): raise NotImplementedError
class WorkspacePort:
    def read(self, scope, path): raise NotImplementedError
    def write(self, scope, path, content, *, code_origin): raise NotImplementedError
class JobPort:
    def submit(self, scope, request): raise NotImplementedError
    def status(self, scope, job_id): raise NotImplementedError
    def cancel(self, scope, job_id): raise NotImplementedError
class TracePort:
    def append(self, event): raise NotImplementedError
class EvaluatorPort:
    def assess(self, bundle, trust): raise NotImplementedError
