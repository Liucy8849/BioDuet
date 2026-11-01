"""Expose durable notices and operation recovery on the real scoped tool router.
The MCP dependency/server is imported only in a separately admitted runtime.
The bridge supplies no planner, scientific parameters, identity, or resource grant.
"""
import json
from .contracts_v01 import require
from .mcp_bridge_v01 import TOOLS as LEGACY_TOOLS,_pairs,_json_value
TOOLS=frozenset(set(LEGACY_TOOLS)|{"notice.receive","notice.acknowledge","job.lookup","job.result"})

class BoundMCP:
    def __init__(self,router,scope):
        require(callable(getattr(router,"invoke",None)),"PARTICIPANT_ROUTER")
        require(getattr(router,"_scopes",{}).get(scope.principal_id) is scope,"UNBOUND_TOOL_SCOPE")
        self._router=router;self._scope=scope
    def invoke(self,tool_name,arguments_json):
        require(type(tool_name) is str and tool_name in TOOLS,"UNKNOWN_TOOL")
        require(type(arguments_json) is str and len(arguments_json.encode())<=1048576,"TOOL_INPUT")
        args=json.loads(arguments_json,object_pairs_hook=_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
        require(type(args) is dict,"TOOL_ARGUMENTS")
        result=self._router.invoke(self._scope,tool_name,args)
        raw=json.dumps(_json_value(result),ensure_ascii=False,allow_nan=False,separators=(",",":"))
        require(len(raw.encode())<=8*1024*1024,"TOOL_OUTPUT_SIZE")
        return raw
    def manifest(self):
        return {"schema":"bioduet-participant-tool-surface/2","tools":sorted(TOOLS),
                "scope_source":"host-bound object; never tool arguments",
                "job_lookup":"Query the original operation after a lost reply; does not relaunch.",
                "job_result":"Execution evidence; accepted is not completed, exit zero is not scientific validity.",
                "notice_receive":"Minimal committed-object update; no automatic full state or solution.",
                "notice_acknowledge":"Protocol receipt only, not proof of discovery or comprehension.",
                "model_call_limit":None,"model_turn_limit":None,
                "execution_admission_issued":False,"transport_runtime_qualified":False}
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
