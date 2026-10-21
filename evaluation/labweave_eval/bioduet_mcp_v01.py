"""Pure BioDuet MCP dispatch candidate; no socket or process startup."""
from copy import deepcopy
import json

def decode_object(value):
    if type(value) is dict:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    elif type(value) is str:
        text = value
    else:
        raise ValueError('REQUEST_OBJECT_REQUIRED')
    if len(text.encode('utf-8')) > 65536:
        raise ValueError('REQUEST_SIZE')
    def pairs(items):
        out = {}
        for key, item in items:
            if key in out:
                raise ValueError('DUPLICATE_JSON_KEY')
            out[key] = item
        return out
    def constant(_):
        raise ValueError('NONFINITE_JSON')
    result = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    if type(result) is not dict:
        raise ValueError('REQUEST_OBJECT_REQUIRED')
    def depth(item, level=0):
        if level > 20:
            raise ValueError('REQUEST_DEPTH')
        if type(item) is dict:
            for child in item.values():depth(child,level+1)
        elif type(item) is list:
            for child in item:depth(child,level+1)
    depth(result)
    return result

TOOLS = [
 {'name':'research_action','description':'Submit an authorized world action exactly as chosen. Use the action schema in the current turn. This does not act for the human.',
  'inputSchema':{'type':'object','properties':{'request':{'type':'object'}},'required':['request'],'additionalProperties':False}},
 {'name':'research_message','description':'Send a message to the independent scientist. A message does not mutate scientific records.',
  'inputSchema':{'type':'object','properties':{'to':{'type':'string','enum':['H']},'text':{'type':'string'}},'required':['to','text'],'additionalProperties':False}},
 {'name':'research_wait','description':'Wait until the specified logical time; this does not assert scientific completion.',
  'inputSchema':{'type':'object','properties':{'until':{'type':'integer','minimum':1}},'required':['until'],'additionalProperties':False}},
 {'name':'research_finish','description':'End your participation. This does not publish or validate any analysis.',
  'inputSchema':{'type':'object','properties':{},'additionalProperties':False}}
]

class McpWorldFacade:
    def __init__(self, bridge, *, max_requests=256):
        if type(max_requests) is not int or not 1 <= max_requests <= 1024:
            raise ValueError('REQUEST_BUDGET')
        self.bridge = bridge
        self.max_requests = max_requests
        self.audit = []

    def dispatch(self, value):
        if len(self.audit) >= self.max_requests:
            raise ValueError('TRANSPORT_BUDGET_EXHAUSTED')
        message = decode_object(value)
        identifier = message.get('id')
        if identifier is not None and type(identifier) not in (str, int):
            raise ValueError('RPC_ID')
        self.audit.append(deepcopy(message))
        def error(code, text):
            return {'jsonrpc':'2.0','id':identifier,'error':{'code':code,'message':text}}
        def result(payload):
            return {'jsonrpc':'2.0','id':identifier,'result':payload}
        if message.get('jsonrpc') != '2.0' or type(message.get('method')) is not str:
            return error(-32600,'Invalid request')
        method = message['method']
        if 'id' not in message:
            return None if method.startswith('notifications/') else error(-32600,'Requests need an ID')
        if identifier is None:
            return error(-32600,'Requests need a non-null ID')
        if method == 'initialize':
            return result({'protocolVersion':'2024-11-05','capabilities':{'tools':{}},
                           'serverInfo':{'name':'bioduet-world','version':'candidate-0.1'}})
        if method == 'ping':
            return result({})
        if method == 'tools/list':
            return result({'tools':deepcopy(TOOLS)})
        if method != 'tools/call':
            return error(-32601,'Method not found')
        params = message.get('params')
        if type(params) is not dict or set(params) != {'name','arguments'}:
            return error(-32602,'Tool call requires name and arguments')
        name, args = params['name'], params['arguments']
        if type(name) is not str or name not in {x['name'] for x in TOOLS}:
            return error(-32602,'Unknown tool')
        if type(args) is not dict:
            decision = {'adapter_protocol_error':'TOOL_ARGUMENT_SCHEMA'}
        elif name == 'research_action' and set(args) == {'request'}:
            # A string is deliberately not repaired here; the known Biomni SDK
            # object/string conversion is a separately recorded thin adapter.
            decision = {'kind':'action','request':deepcopy(args['request'])}
        elif name == 'research_message' and set(args) == {'to','text'}:
            decision = {'kind':'message','to':args['to'],'text':args['text']}
        elif name == 'research_wait' and set(args) == {'until'}:
            decision = {'kind':'wait','until':args['until']}
        elif name == 'research_finish' and not args:
            decision = {'kind':'finish'}
        else:
            decision = {'adapter_protocol_error':'TOOL_ARGUMENT_SCHEMA'}
        try:
            exchange = self.bridge.exchange(decision)
        except ValueError as exc:
            if str(exc) != 'NO_AGENT_TURN':
                raise
            return result({'content':[{'type':'text','text':json.dumps({'status':'episode_closed'})}],
                           'isError':True})
        failed = exchange['receipt']['result']['status'] in ('rejected','environment_error')
        failed = failed or exchange['environment_failure'] is not None
        text = json.dumps(exchange,ensure_ascii=False,allow_nan=False)
        if len(text.encode('utf-8')) > 1048576:
            raise ValueError('RESPONSE_SIZE')
        return result({'content':[{'type':'text','text':text}],'isError':failed})
