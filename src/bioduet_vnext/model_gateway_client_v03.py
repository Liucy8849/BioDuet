"""Actor SDK settings carry a newly minted capability, not a provider credential.
Minting a capability does not register a binding or issue Root execution admission.
Root must isolate the credential worker/journals from actor PID/mount access.
"""
import hashlib,secrets
from dataclasses import dataclass,field
from urllib.parse import urlsplit
from .contracts_v01 import Scope,require
_MINT=object()
@dataclass(frozen=True)
class ActorCapability:
    scope: Scope
    value: str=field(repr=False)
    _issuer: object=field(repr=False)
    @property
    def sha256(self):return hashlib.sha256(self.value.encode()).hexdigest()
def issue_actor_capability(scope):
    require(type(scope) is Scope and scope.role in ("A","H"),"ACTOR_CAPABILITY_SCOPE")
    return ActorCapability(scope,secrets.token_urlsafe(32),_MINT)
def actor_client_config(*,gateway_base_url,capability,model):
    parsed=urlsplit(gateway_base_url)
    require(parsed.scheme=="http" and parsed.hostname=="127.0.0.1" and parsed.port is not None
            and parsed.path in ("","/v1") and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment,"PRIVATE_GATEWAY_ENDPOINT")
    require(type(capability) is ActorCapability and capability._issuer is _MINT and
            type(model) is str and bool(model),"MINTED_ACTOR_CAPABILITY")
    return {"connection":{"base_url":gateway_base_url.rstrip("/") if parsed.path=="/v1" else gateway_base_url.rstrip("/")+"/v1",
                          "api_key":capability.value,"model":model},
            "manifest":{"model_call_limit":None,"model_turn_limit":None,
                        "actor_capability_sha256":capability.sha256,"provider_credential_in_connection":False,
                        "runtime_or_OS_isolation_qualified":False,
                        "boundary":"Controller-minted scoped actor capability only; no grant from constructing this config."}}
