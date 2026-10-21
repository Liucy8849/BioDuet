"""Thin native-entry preparation. Does not import or start either engine."""
import inspect
import sys
from .bioduet_mcp_v01 import decode_object

def timeout_plan(*, analysis_seconds=180, human_seconds=60, cleanup_seconds=15,
                 serialization_seconds=15, native_margin_seconds=30,
                 episode_seconds=1200):
    values = [analysis_seconds,human_seconds,cleanup_seconds,serialization_seconds,native_margin_seconds,episode_seconds]
    if any(type(x) is not int or x <= 0 for x in values):
        raise ValueError('TIMEOUT_SCHEMA')
    bridge = sum(values[:4])
    native = bridge + native_margin_seconds
    if native >= episode_seconds or episode_seconds > 1200:
        raise ValueError('TIMEOUT_BUDGET_INCOHERENT')
    return {'analysis_seconds':analysis_seconds,'human_seconds':human_seconds,
            'bridge_seconds':bridge,'opencode_mcp_timeout_ms':native*1000,
            'biomni_execution_timeout_seconds':native,'episode_seconds':episode_seconds,
            'effective_deadline_rule':'min(stage_deadline,remaining_episode_deadline,resource_grant_deadline)'}

def adapt_biomni_action(agent):
    """Convert the known SDK's object/string representation only, in memory.

    No missing request fields or operation identifiers are supplied.
    Call in the isolated native A1 process before agent.configure().
    """
    name='research_action'
    tool=agent.tool_registry.get_tool_by_name(name)
    original=agent._custom_functions.get(name)
    info=agent._custom_tools.get(name)
    module=sys.modules.get('mcp_servers.research')
    if (type(tool) is not dict or tool.get('module')!='mcp_servers.research'
            or not callable(original) or type(info) is not dict
            or info.get('module')!='mcp_servers.research'
            or module is None or getattr(module,name,None) is not original):
        raise ValueError('BIOMNI_TOOL_BINDING')
    required=tool.get('required_parameters')
    if (type(required) is not list or len(required)!=1
            or type(required[0]) is not dict or required[0].get('name')!='request'
            or required[0].get('type') not in ('object','string')
            or tool.get('optional_parameters')!=[]
            or tool.get('parameters')!={'request':{'type':'object'}}
            or type(tool.get('description')) is not str):
        raise ValueError('BIOMNI_TOOL_SCHEMA')
    def wrapper(request):
        return original(request=decode_object(request))
    wrapper.__name__=name
    wrapper.__doc__=original.__doc__
    wrapper.__signature__=inspect.Signature([
        inspect.Parameter('request',inspect.Parameter.POSITIONAL_OR_KEYWORD,annotation=dict)],
        return_annotation=dict)
    setattr(module,name,wrapper)
    agent._custom_functions[name]=wrapper
    tool['fn']=wrapper
    required[0]['type']='dict'
    tool['description']+=' Pass the chosen request as a Python dict; no scientific fields are filled by this adapter.'
    info['description']=tool['description']
    return {'adapter':'bioduet-biomni-object/0.1','tool':name,
            'scientific_fields_filled':False,'operation_id_added':False}
