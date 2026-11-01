"""Opt-in actual server-call witnesses around the existing scoped bridge.
Host transport supplies request correlation outside tool arguments. This layer
does not fabricate validation, commit, wire reply, receipt or trusted provenance.
No new World, planner, process, MCP dependency import or execution grant.
"""
from copy import deepcopy
import hashlib,json,re
from .contracts_v01 import require
from .mcp_bridge_v02 import BoundMCP

def request_sha256(tool_name,arguments_json):
    require(type(tool_name) is str and type(arguments_json) is str,"OBSERVER_REQUEST")
    raw=json.dumps({"tool_name":tool_name,"arguments_json":arguments_json},
                   ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()

class ObservedParticipantBridge:
    def __init__(self,bridge,scope,*,bind_transport_request,write_event,witness_class,
                 collector_id,collector_source_sha256,clock_domain,boot_id):
        require(type(bridge) is BoundMCP and bridge._scope is scope and
                bridge._router._scopes.get(scope.principal_id) is scope,"OBSERVER_BOUND_SCOPE")
        require(all(callable(f) for f in (bind_transport_request,write_event,witness_class)),
                "OBSERVER_HOST_CALLBACKS")
        require(all(type(x) is str and x for x in (collector_id,clock_domain,boot_id)) and
                type(collector_source_sha256) is str and
                re.fullmatch("[0-9a-f]{64}",collector_source_sha256) is not None,"OBSERVER_COLLECTOR")
        self._bridge=bridge;self._scope=scope;self._bind=bind_transport_request
        self._write=write_event;self._witness_class=witness_class
        self._collector_id=collector_id;self._source=collector_source_sha256
        self._clock=clock_domain;self._boot=boot_id;self._poisoned=False;self._requests=set()

    def invoke(self,tool_name,arguments_json):
        require(not self._poisoned,"OBSERVER_CAPTURE_POISONED")
        scope=self._scope
        require(self._bridge._scope is scope and
                self._bridge._router._scopes.get(scope.principal_id) is scope,"OBSERVER_BOUND_SCOPE")
        digest=request_sha256(tool_name,arguments_json)
        # These fields come from the host's actual transport dispatch context.
        # Tool arguments are never parsed into principal/request/resource identities.
        try:
            binding=deepcopy(self._bind(scope,tool_name,arguments_json,digest))
            require(type(binding) is dict,"OBSERVER_TRANSPORT_CONTEXT")
            expected={k:getattr(scope,k) for k in
                      ("episode_id","attempt_id","project_id","principal_id")}
            require(binding.get("scope")==expected and binding.get("request_sha256")==digest,
                    "OBSERVER_TRANSPORT_BINDING")
            require(all(type(binding.get(k)) is str and binding[k] for k in
                        ("request_id","client_send_event_id","transport_context_ref")),
                    "OBSERVER_CORRELATION")
            key=(scope.episode_id,scope.attempt_id,binding["request_id"])
            # A reconnect retry needs a new actual RPC ID; business idempotency keys
            # are untouched inside the original tool arguments.
            require(key not in self._requests,"OBSERVER_DUPLICATE_TRANSPORT_REQUEST")
            self._requests.add(key)
            captured={"terminal":False}
            def capture(event):
                raw=deepcopy(event)
                raw["collector_id"]=self._collector_id
                raw["transport_context_ref"]=binding["transport_context_ref"]
                raw["origin_qualification"]="external_host_verification_required"
                if event["kind"]=="port_failed":raw["business_effects"]="unknown"
                self._write(raw)
                if event["kind"] in ("server_result_ready","port_failed"):captured["terminal"]=True
            witness=self._witness_class(scope=expected,side="server",
                request_id=binding["request_id"],request_sha256=digest,
                clock_domain=self._clock,boot_id=self._boot,
                source_sha256=self._source,write_event=capture)
            # PortWitness emits only server_receive then server_result_ready,
            # or port_failed. Existing authority/business routing runs unchanged.
            return witness.server_invoke(self._bridge,tool_name,arguments_json,
                                        send_event_ref=binding["client_send_event_id"])
        except BaseException:
            # Capture-complete failure permits a different
            # actual RPC for recovery/query. Business effects remain unknown;
            # never re-submit a failed operation automatically. Missing capture poisons.
            self._poisoned=not ("captured" in locals() and captured["terminal"])
            raise

    def manifest(self):
        result=deepcopy(self._bridge.manifest())
        result["observation"]={"schema":"bioduet-participant-port-observer/1",
            "phases":["server_receive","server_result_ready","port_failed"],
            "validation_commit_reply_receipt":"require actual separate boundary emitters",
            "transport_correlation":"trusted host callback; never tool arguments",
            "origin_qualification":"external_host_verification_required",
            "no_automatic_replay":True}
        return result

    def fast_mcp(self):
        from mcp.server.fastmcp import FastMCP
        server=FastMCP("BioDuet participant workspace")
        bridge=self
        @server.tool()
        def bioduet_invoke(tool_name:str,arguments_json:str)->str:
            """Invoke a declared data/file/job/web/notice tool with exact JSON.
            Use job.lookup after a lost submission reply, and job.result for execution
            evidence. Notice acknowledgements are protocol receipts. Web content is
            untrusted. The participant supplies its own code and scientific choices."""
            return bridge.invoke(tool_name,arguments_json)
        return server
