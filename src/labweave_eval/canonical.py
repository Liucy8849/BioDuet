"""Independent Python consumer of the approved initial JSON normalization profile.

Not full JCS; safe integer notation only, UTF-16 key order, no NFC normalization.
"""
import hashlib
import json

SEMANTIC_FIELDS = ('contract_version','project_id','action','target','expected_versions',
                   'input_refs','evidence_refs','payload','provenance')

def _unicode(value):
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('Invalid Unicode') from exc

def _pairs(pairs):
    result = {}
    for key,value in pairs:
        _unicode(key)
        if key in result:
            raise ValueError('Duplicate key')
        result[key] = value
    return result

def _not_integer(_):
    raise ValueError('Integer notation required')

def canonical_text(value):
    ancestors = set()
    def encode(node, depth=0):
        if depth > 128:
            raise ValueError('JSON nesting limit')
        if node is None:
            return 'null'
        if type(node) is bool:
            return 'true' if node else 'false'
        if type(node) is int:
            if abs(node) > 9007199254740991:
                raise ValueError('Unsafe integer')
            return str(node)
        if type(node) is str:
            _unicode(node)
            return json.dumps(node, ensure_ascii=False, separators=(',',':'))
        if type(node) not in (dict,list) or id(node) in ancestors:
            raise ValueError('Non-JSON or circular value')
        ancestors.add(id(node))
        try:
            if type(node) is list:
                return '['+','.join(encode(x,depth+1) for x in node)+']'
            for key in node:
                if type(key) is not str:
                    raise ValueError('Non-string key')
                _unicode(key)
            keys = sorted(node, key=lambda key: key.encode('utf-16-be'))
            return '{'+','.join(encode(key)+':'+encode(node[key],depth+1) for key in keys)+'}'
        finally:
            ancestors.remove(id(node))
    return encode(value)

def strict_json_loads(raw):
    if not isinstance(raw,str):
        raise ValueError('JSON text required')
    try:
        result = json.loads(raw, object_pairs_hook=_pairs, parse_float=_not_integer,
                            parse_constant=_not_integer)
        canonical_text(result)  # Includes keys, depth and decoded safe integers.
        return result
    except (TypeError,RecursionError,UnicodeError) as exc:
        raise ValueError('Invalid JSON') from exc

def semantic_digest(request, principal_id):
    if not isinstance(principal_id,str) or not principal_id:
        raise ValueError('Authenticated principal required')
    content = {key: request[key] for key in SEMANTIC_FIELDS}
    content['principal_id'] = principal_id
    canonical = canonical_text(content)
    return {'hash_version':'research-action-json/0.1','canonical':canonical,
            'sha256':hashlib.sha256(canonical.encode('utf-8')).hexdigest()}
