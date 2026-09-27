"""Narrow research-action/0.1 engineering profile; no third-party dependencies."""
import hashlib
import json
import re
from uuid import UUID

CONTRACT = "research-action/0.1"
HASH_VERSION = "research-action-json/0.1"
NAMES = ("state.read evidence.submit metadata.revise qc.record pair.confirm "
         "design.propose design.approve plan.propose task.create task.assign "
         "analysis.start verification.request result.publish result.restrict "
         "job.request receipt.record access.change handoff.record operation.inspect "
         "approval.revoke verification.record").split()
REGISTRY = {f"A{i:02}": {"name": name, "version": "a1", "status":
            "implemented_engineering_subset" if i in (1, 3, 19) else "not_implemented"}
            for i, name in enumerate(NAMES, 1)}

class Rejection(Exception):
    def __init__(self, code, **detail):
        self.code, self.detail = code, detail
        super().__init__(code)

def reject_if(condition, code="SCHEMA_INVALID"):
    if condition:
        raise Rejection(code)

def _pairs(pairs):
    result = {}
    for key, value in pairs:
        reject_if(key in result)
        result[key] = value
    return result

def strict_loads(raw):
    try:
        result = json.loads(raw, object_pairs_hook=_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(Rejection("SCHEMA_INVALID")))
        validate_json(result)
        return result
    except (ValueError, TypeError, RecursionError) as exc:
        raise Rejection("SCHEMA_INVALID") from exc

def validate_json(value):
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise Rejection("SCHEMA_INVALID") from exc
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        reject_if(abs(value) > 9007199254740991)
        return
    if isinstance(value, list):
        for item in value:
            validate_json(item)
        return
    if isinstance(value, dict):
        reject_if(any(not isinstance(k, str) for k in value))
        for item in value.values():
            validate_json(item)
        return
    # First fixture profile has no floating point fields. Scientific numeric
    # schemas and cross-language float canonicalization are deliberately pending.
    raise Rejection("SCHEMA_INVALID")

def exact(value, fields):
    reject_if(not isinstance(value, dict) or set(value) != set(fields))

def text(value):
    reject_if(not isinstance(value, str) or not value.strip())

def uuid(value):
    try:
        reject_if(not isinstance(value, str) or str(UUID(value)) != value)
    except (ValueError, AttributeError) as exc:
        raise Rejection("SCHEMA_INVALID") from exc

def ref(value, versioned=False):
    exact(value, ("object_type", "object_id", "revision") if versioned else ("object_type", "object_id"))
    text(value["object_type"])
    uuid(value["object_id"])
    if versioned:
        reject_if(not isinstance(value["revision"], str) or re.fullmatch(r"[1-9][0-9]*", value["revision"]) is None)

def validate_request(req):
    validate_json(req)
    reject_if(not isinstance(req, dict))
    base = {"contract_version", "project_id", "action", "payload", "trace_context"}
    reject_if(not base.issubset(req) or req["contract_version"] != CONTRACT)
    uuid(req["project_id"])
    exact(req["action"], ("id", "name", "version"))
    aid = req["action"]["id"]
    reject_if(aid not in REGISTRY or req["action"]["name"] != REGISTRY[aid]["name"] or req["action"]["version"] != "a1")
    exact(req["trace_context"], ("request_id", "episode_id"))
    for item in req["trace_context"].values():
        text(item)
    if REGISTRY[aid]["status"] == "not_implemented":
        raise Rejection("NOT_IMPLEMENTED")
    if aid == "A19":
        exact(req, base)
        exact(req["payload"], ("operation_id",))
        uuid(req["payload"]["operation_id"])
        return
    if aid == "A01":
        exact(req, base | {"target"})
        ref(req["target"])
        exact(req["payload"], ())
        return
    exact(req, base | {"target", "operation_id", "idempotency_key", "expected_versions", "input_refs", "evidence_refs", "provenance"})
    ref(req["target"])
    uuid(req["operation_id"])
    key = req["idempotency_key"]
    reject_if(not isinstance(key, str) or not (1 <= len(key) <= 191) or key != key.strip() or any(ord(c) < 32 or ord(c) > 126 for c in key))
    for name in ("expected_versions", "input_refs", "evidence_refs"):
        reject_if(not isinstance(req[name], list))
        for item in req[name]:
            ref(item, True)
        reject_if(len({(v["object_type"], v["object_id"]) for v in req[name]}) != len(req[name]))
    reject_if(len(req["expected_versions"]) != 1 or req["expected_versions"][0]["object_type"] != req["target"]["object_type"] or req["expected_versions"][0]["object_id"] != req["target"]["object_id"])
    reject_if(req["input_refs"] != [] or not req["evidence_refs"])
    exact(req["payload"], ("changes", "reason", "claim_status"))
    changes = req["payload"]["changes"]
    reject_if(not isinstance(changes, dict) or not changes or not set(changes).issubset({"condition", "donor", "time", "batch"}))
    for value in changes.values():
        text(value)
    text(req["payload"]["reason"])
    reject_if(req["payload"]["claim_status"] != "submitted")
    exact(req["provenance"], ("source_kind", "source_ref"))
    reject_if(req["provenance"]["source_kind"] not in ("synthetic", "simulated_replay"))
    text(req["provenance"]["source_ref"])

def request_hash(req, principal_id):
    fields = ("contract_version", "project_id", "action", "target", "expected_versions", "input_refs", "evidence_refs", "payload", "provenance")
    content = {k: req[k] for k in fields}
    content["principal_id"] = principal_id
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
