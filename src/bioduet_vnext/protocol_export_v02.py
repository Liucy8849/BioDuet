"""Derived historical protocol counts; leaves original report bytes unchanged."""
import hashlib,json
from .protocol_counts_v01 import read_protocol_errors

def derive_protocol_counts(raw, *, source_sha256, source_schema, mappings):
    if type(raw) is not bytes: raise TypeError("raw bytes required")
    actual=hashlib.sha256(raw).hexdigest()
    if actual!=source_sha256: raise ValueError("SOURCE_PIN")
    def unique(pairs):
        row={}
        for key,value in pairs:
            if key in row: raise ValueError("DUPLICATE_JSON_KEY")
            row[key]=value
        return row
    def constant(value): raise ValueError("NONFINITE_JSON")
    report=json.loads(raw,object_pairs_hook=unique,parse_constant=constant)
    if type(report) is not dict: raise ValueError("REPORT_OBJECT")
    if type(mappings) is not dict or set(mappings)!={"A","H"}:
        raise ValueError("ROLE_MAPPINGS")
    rows={}
    for role,mapping in mappings.items():
        if type(mapping) is not dict or set(mapping) not in (
                {"path","list_field","count_field","coverage"},
                {"path","value_field","coverage"}):
            raise ValueError("MAPPING_SCHEMA")
        if type(mapping["path"]) is not list:raise ValueError("MAPPING_PATH")
        current=report
        for key in mapping["path"]:
            if type(key) is not str: raise ValueError("MAPPING_PATH")
            if type(current) is not dict or key not in current:
                current={}
                break
            current=current[key]
        if "value_field" in mapping:
            if type(current) is not dict:raise ValueError("MAPPING_CONTAINER")
            field=mapping["value_field"]
            if type(field) is not str:raise ValueError("MAPPING_FIELD")
            normalized={}
            if field in current:
                value=current[field]
                normalized["events" if type(value) is list else "count"]=value
            current=normalized
            list_field,count_field="events","count"
        else:
            list_field,count_field=mapping["list_field"],mapping["count_field"]
        rows[role]=read_protocol_errors(current,list_field=list_field,
            count_field=count_field,source_schema=source_schema,
            evidence_ref="sha256:"+actual,coverage=mapping["coverage"])
    return {"schema":"bioduet.protocol-count-export/1","source_sha256":actual,
            "source_schema":source_schema,"roles":rows,"formal_score":None,
            "strict_score":None}
