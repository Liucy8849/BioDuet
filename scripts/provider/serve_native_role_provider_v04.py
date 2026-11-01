"""Native harness provider host preparation; not executed.
Root alone binds existing account/model/upstream/CA, private lazy credential loader,
independent authorizer and fresh finite model admission. Actor never receives a
provider key. Two finite natural protocol cases do not impose model call/turn caps.
"""
import argparse,hashlib,json,math,os,signal,sys,time,importlib.util
from pathlib import Path
from urllib.parse import urlsplit
from http.client import HTTPConnection
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bioduet_vnext.contracts_v01 import Scope,require,sha
from bioduet_vnext.model_gateway_v04 import ActorBinding,PrivateJournal,CredentialBroker
from bioduet_vnext.model_gateway_http_v04 import serve_http
from bioduet_vnext.model_gateway_upstream_v04 import HTTPSUpstream
from bioduet_vnext.model_gateway_client_v03 import issue_actor_capability,actor_client_config

SYNTHETIC_HTTP_REVIEW_SHA="77d8b5d5f18e9bfed504a95440a30dc2da2d40e646d77b21c5fb266846db1762"
def pin(row):
    p=Path(row["path"]);require(p.is_absolute() and not p.is_symlink(),"PINNED_ROOT_INPUT")
    raw=p.read_bytes();require(len(raw)==row["bytes"] and hashlib.sha256(raw).hexdigest()==row["sha256"],
                             "ROOT_INPUT_SHA");return raw
def publish(path,row):
    p=Path(path);require(p.is_absolute(),"ROLE_OUTPUT")
    raw=(json.dumps(row,sort_keys=True,allow_nan=False)+"\n").encode()
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
def wait_json(path,nonce,deadline):
    p=Path(path);require(p.is_absolute(),"ROOT_CONTROL_PATH")
    while time.monotonic()<deadline:
        try:
            require(not p.is_symlink(),"CONTROL_SYMLINK")
            value=json.loads(p.read_bytes());require(value.get("nonce")==nonce,"CONTROL_NONCE")
            return value
        except (FileNotFoundError,json.JSONDecodeError):time.sleep(.05)
    raise TimeoutError("LIVE_GATEWAY_HOST_DEADLINE")
def validate(proof):
    require(proof.get("schema")=="bioduet-root-native-role-model-provider-proof/1"
        and proof.get("source_kind")=="live" and proof.get("role")=="provider"
        and os.getuid()==1008 and os.getgroups()==[],"ROOT_NATIVE_PROVIDER_FRESH_PRIVATE_SCOPE")
    require(proof.get("model_call_limit") is None and proof.get("model_turn_limit") is None,
            "NONE_MODEL_CALLS_AND_TURNS")
    require(proof.get("prior_synthetic_HTTP_review_sha256")==SYNTHETIC_HTTP_REVIEW_SHA
        and sha(proof.get("prior_live_provider_review_sha256")),
            "SEPARATE_ACTUAL_LIVE_PROVIDER_QUALIFICATION_NOT_CURRENT_GRANT")
    require(proof.get("harness_kind") in ("openhands","opencode")
        and proof.get("declared_actor_role") in ("A","H")
        and proof.get("binding_category")==("human_simulator" if proof["declared_actor_role"]=="H" else "model_unclassified"),
            "NATIVE_PRIMARY_AUXILIARY_NOT_GUESSED_FROM_SHARED_CAPABILITY")
    require(type(proof.get("deadline_monotonic")) in (int,float)
        and math.isfinite(proof["deadline_monotonic"]) and time.monotonic()<proof["deadline_monotonic"],
            "FINITE_NATIVE_PROVIDER_HOST_DEADLINE")
    for row in proof["readonly_inputs"]:pin(row)
    return Scope(**proof["actor_scope"])

def provider(proof):
    scope=validate(proof);require(scope.role in ("A","H") and proof["declared_actor_role"]==scope.role,"EXACT_NEW_ROLE_SCOPE")
    source=proof["Root_private_adapter"];raw=pin(source)
    module=importlib.util.module_from_spec(importlib.util.spec_from_file_location("root_model_adapter",source["path"]))
    # Root independently audits no secret access/import-time I/O here. The actual
    # account access is deferred to authorization_headers after authorize succeeds.
    require(module.__name__ not in sys.modules,"FRESH_ROOT_PRIVATE_ADAPTER_MODULE")
    sys.modules[module.__name__]=module
    exec(compile(raw,source["path"],"exec"),module.__dict__)
    require(all(callable(getattr(module,n,None)) for n in ("authorize","authorization_headers","safe_observations","public_binding")),
            "ROOT_PRIVATE_ADAPTER_CONTRACT")
    public=module.public_binding()
    require(type(public) is dict and public.get("schema")=="bioduet-deferred-DeepSeek-public-binding/1"
            and public.get("upstream_host")==proof["upstream_host"]=="api.deepseek.com"
            and public.get("upstream_port")==443 and public.get("upstream_path")==proof["upstream_path"]
            and public.get("model")==proof["model"] and public.get("actor_scope")==proof["actor_scope"]
            and public.get("category")==proof["binding_category"]==("human_simulator" if proof["declared_actor_role"]=="H" else "model_unclassified")
            and public.get("scope_ref_sha256")==proof["provider_scope_ref_sha256"]
            and public.get("required_phase")==proof["required_provider_phase"]
            and public.get("secret_loader_source_sha256")==proof["secret_loader_source_sha256"]
            and public.get("model_call_limit") is None and public.get("model_turn_limit") is None,
            "PRIVATE_AUTHORIZATION_TARGET_MUST_MATCH_ACTUAL_HTTPS_MODEL_TARGET")
    actor=wait_json(proof["actor_ready_input"],proof["nonce"],proof["deadline_monotonic"])
    require(actor.get("scope")==proof["actor_scope"] and sha(actor.get("capability_sha256")),
            "ACTOR_SCOPE_CAPABILITY_BINDING")
    ca=proof["public_CA"];pin(ca)
    upstream=HTTPSUpstream(host=proof["upstream_host"],path=proof["upstream_path"],
        ca_path=ca["path"],ca_sha256=ca["sha256"],authorization_headers=module.authorization_headers)
    journal=PrivateJournal(proof["private_journal"])
    binding=ActorBinding(scope,proof["model"],actor["capability_sha256"],"human_simulator" if scope.role=="H" else "model_unclassified","live",
                         proof["clock_domain"],proof["boot_id"])
    broker=CredentialBroker(bindings=[binding],journal=journal,authorize=module.authorize,transport=upstream)
    server=serve_http(broker,host="127.0.0.1",port=proof["port"])
    previous=signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    publish(proof["provider_ready_output"],{"nonce":proof["nonce"],"scope":proof["actor_scope"],
        "capability_sha256":binding.token_sha256,"PID":os.getpid(),
        "address":"http://127.0.0.1:"+str(server.server_address[1])+"/v1","passive_listener_READY":True,
        "provider_key_issued_to_actor":False,"grant_from_constructing_listener":False})
    failure=None
    try:server.serve_forever(poll_interval=.1)
    except KeyboardInterrupt:pass
    except BaseException as exc:failure=type(exc).__name__;raise
    finally:
        server.server_close();signal.signal(signal.SIGTERM,previous)
        # Private final receipt; Root exposes only reviewed safe metadata/capture refs.
        publish(proof["provider_final_output"],{"schema":"bioduet-native-role-model-provider-result/1",
            "nonce":proof["nonce"],"source_kind":"live","records":broker.records,
            "Root_adapter_public_binding":public,"harness_kind":proof["harness_kind"],
            "native_component_attribution_complete":False,"Root_adapter_safe_observations":module.safe_observations(),"failure_type":failure,
            "provider_bill":None,"SDK_imported":False,"scientific_episode":False,
            "actual_model_execution_determined_from_private_dispatches_not_HTTP_count":True,
            "independent_Root_retirement_and_credential_boundary_review_required":True,
            "formal_score":None,"strict_score":None})
        journal.close()

def main():
    p=argparse.ArgumentParser();p.add_argument("--proof",required=True);p.add_argument("--proof-sha256",required=True)
    args=p.parse_args();raw=Path(args.proof).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==args.proof_sha256,"ROOT_NATIVE_PROVIDER_PROOF_SHA")
    provider(json.loads(raw))
if __name__=="__main__":main()
