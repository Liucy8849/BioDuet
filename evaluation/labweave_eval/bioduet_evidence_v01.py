"""Candidate pinned evidence reader for BW-01 v0.2. Not a science oracle.

Trust anchor: caller-controlled summary SHA256 from a separately reviewed inventory.
Hashes bind bytes, not scientific truth or producer honesty. Private bundle never
belongs in participant observations. Unsupported traces fail closed.
"""
import hashlib
import json
import math
import os
import re
import stat

LIMIT = 4 * 1024 * 1024
PROFILE = "bw01-participant-science-human-envelope/0.2"
WORLD_PROFILE = "bw01-interaction-science-development/0.1"
FILES = {"episode": "episode-private.json", "oracle": "oracle.json",
         "provider_ledger": "provider-ledger.json"}

class EvidenceError(ValueError):
    pass

def need(ok, code):
    if not ok:
        raise EvidenceError(code)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()

def strict(raw):
    def pairs(rows):
        out = {}
        for k, v in rows:
            need(k not in out, "DUPLICATE_KEY")
            out[k] = v
        return out
    def constant(value):
        raise EvidenceError("NONFINITE")
    try:
        obj = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        stack = [(obj, 0)]
        while stack:
            value, depth = stack.pop()
            need(depth <= 64, "DEPTH")
            if type(value) is float:
                need(math.isfinite(value), "NONFINITE")
            elif type(value) is dict:
                stack.extend((v, depth + 1) for v in value.values())
            elif type(value) is list:
                stack.extend((v, depth + 1) for v in value)
        need(type(obj) is dict, "OBJECT")
        return obj
    except EvidenceError:
        raise
    except (ValueError, RecursionError, UnicodeError):
        raise EvidenceError("INVALID_JSON") from None

def same(a, b):
    return digest(a) == digest(b)

def directory_fd(directory):
    """Open every path component without following symlinks."""
    path = os.fspath(directory)
    need(type(path) is str and path.startswith("/"), "ABSOLUTE_DIRECTORY")
    parts = path.split("/")[1:]
    need(parts and all(x and x not in (".", "..") for x in parts), "DIRECTORY_PATH")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in parts:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                          dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise

def read_pinned(fd, name, expected_sha, expected_size=None):
    need(name in {"summary.json", *FILES.values()}, "FILE_NAME")
    need(type(expected_sha) is str and re.fullmatch("[0-9a-f]{64}", expected_sha),
         "SHA256")
    if expected_size is not None:
        need(type(expected_size) is int and 0 < expected_size <= LIMIT, "SIZE")
    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(file_fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "REGULAR_SINGLE_LINK")
        need(0 < before.st_size <= LIMIT, "SIZE")
        if expected_size is not None:
            need(before.st_size == expected_size, "SIZE_MISMATCH")
        chunks = []
        left = LIMIT + 1
        while left:
            chunk = os.read(file_fd, min(left, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(file_fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                              s.st_ctime_ns, s.st_nlink, s.st_mode)
        need(identity(before) == identity(after), "FILE_CHANGED")
        need(len(raw) == before.st_size, "READ_SIZE")
        need(hashlib.sha256(raw).hexdigest() == expected_sha, "HASH_MISMATCH")
        return strict(raw)
    finally:
        os.close(file_fd)

def check_envelope(entry):
    """Check exact raw decision preservation, allowing only the authorized H ID envelope."""
    raw = entry["raw_model_response"]
    need(digest(raw) == entry["response_sha256"], "RAW_RESPONSE_HASH")
    try:
        original = strict(raw["choices"][0]["message"]["content"])
        error = None
    except EvidenceError:
        original = {"kind": "invalid_model_output"}
        error = "INVALID_MODEL_JSON"
    need(entry["parse_error"] == error, "PARSE_ERROR")
    adapter = entry["protocol_adapter"]
    changed = adapter["changed_fields"]
    expected = json.loads(json.dumps(original))
    if changed:
        need(entry["actor"] == "H" and changed == ["request.operation_id"] and error is None,
             "SCIENTIFIC_ADAPTER_CHANGE")
        need(set(original) == {"kind", "request"} and original["kind"] == "action", "H_ENVELOPE")
        request = original["request"]
        need(type(request) is dict and set(request) == {"action_id", "payload"}
             and type(request["action_id"]) is str and request["action_id"] != "A01"
             and type(request["payload"]) is dict, "H_ENVELOPE")
        canonical = json.dumps(original, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        generated = "h-" + hashlib.sha256((entry["packet"]["episode_id"] + "\n" + canonical).encode()).hexdigest()[:40]
        expected["request"]["operation_id"] = generated
        need(adapter["generated_operation_id"] == generated
             and same(adapter["original_decision"], original)
             and same(adapter["submitted_decision"], expected), "H_ENVELOPE_ID")
    if entry["actor"] == "A":
        need(not changed and adapter["version"] == "unchanged-agent-v01", "AGENT_ADAPTER")
    submission = entry["submission"]
    if "decision" not in submission:
        need(error == "INVALID_MODEL_JSON" and not changed
             and submission["result"] == {"reason": "DECISION_SCHEMA", "status": "rejected"},
             "MISSING_DECISION")
    else:
        need(same(submission["decision"], expected), "SCIENTIFIC_DECISION_CHANGED")
    return error

def validate_trace(summary, episode):
    try:
        return _validate_trace(summary, episode)
    except EvidenceError:
        raise
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        raise EvidenceError("TRACE_SCHEMA") from None

def _validate_trace(summary, episode):
    need(summary["schema"] == "bw01-scientific-development-run/2", "SUMMARY_SCHEMA")
    need(episode["profile"] == PROFILE, "PROFILE")
    need(summary["condition"] == episode["condition"] and episode["condition"] in ("H0", "H1"),
         "CONDITION")
    need(summary["formal_benchmark_score"] is None and episode["formal_benchmark_score"] is None
         and summary["scientific_validity"] == episode["scientific_validity"] == "not_assessed",
         "CLAIM_BOUNDARY")
    records, transcript, history = (episode[k] for k in ("session_records", "transcript", "world_history"))
    need(all(type(x) is list and len(x) <= 1024 for x in (records, transcript, history)), "TRACE_SIZE")
    need(bool(records) and len(records) == len(transcript), "TURN_JOIN")
    need(type(summary["actual_model_calls"]) is int and summary["actual_model_calls"] == len(transcript),
         "MODEL_CALL_COUNT")
    seen_ticks, episode_ids, operations, expected_history = {}, set(), {}, {}
    faults = []
    prior_tick = -1
    for i, (record, entry) in enumerate(zip(records, transcript)):
        need(type(record["seq"]) is int and record["seq"] == i, "SEQUENCE")
        tick = record["tick"]
        need(type(tick) is int and tick > prior_tick, "TICK")
        prior_tick = tick
        actor = record["actor"]
        need(actor in ("A", "H") and entry["actor"] == actor, "ACTOR")
        need(same(record, entry["submission"]), "SUBMISSION_JOIN")
        packet = entry["packet"]
        need(packet["profile"] == WORLD_PROFILE, "WORLD_PROFILE")
        need(digest(packet) == entry["packet_sha256"], "PACKET_HASH")
        need(packet["actor"] == actor and type(packet["tick"]) is int and packet["tick"] == tick,
             "PACKET_JOIN")
        need(type(packet["episode_id"]) is str and bool(packet["episode_id"]), "EPISODE_ID")
        episode_ids.add(packet["episode_id"])
        error = check_envelope(entry)
        if error:
            faults.append({"seq": i, "tick": tick, "actor": actor, "code": error})
        seen_ticks[tick] = record
        decision = record.get("decision", {})
        if decision.get("kind") != "action":
            continue
        request, result = decision["request"], record["result"]
        action = request.get("action_id")
        if result.get("status") not in ("succeeded", "failed"):
            continue
        # This frozen profile has no mutating A01 observation history.
        if action == "A01":
            continue
        need(action in ("A02", "A03", "A04", "A05", "A06", "A11", "A12", "A13", "A14"),
             "UNSUPPORTED_ACTION")
        key = (actor, request["operation_id"])
        if key in operations:
            old_request, old_result = operations[key]
            need(same(old_request, request) and same(old_result, result), "IDEMPOTENCY")
        else:
            operations[key] = (request, result)
            expected_history[tick] = (actor, action)
    need(len(episode_ids) == 1, "CROSS_EPISODE")
    observed_history, known = {}, {}
    prior_tick = -1
    for event in history:
        tick = event["tick"]
        need(type(tick) is int and tick > prior_tick, "HISTORY_ORDER")
        prior_tick = tick
        need(tick in expected_history and expected_history[tick] == (event["actor"], event["action_id"]),
             "HISTORY_ACTION_JOIN")
        need(type(event["before"]) is dict and type(event["after"]) is dict
             and set(event["before"]) == set(event["after"]), "SNAPSHOT_FIELDS")
        need(set(event["before"]) <= {"sample", "design", "public_evidence", "publication"},
             "UNSUPPORTED_SNAPSHOT")
        for field, value in event["before"].items():
            if field in known:
                need(same(known[field], value), "STATE_DISCONTINUITY")
        known.update(event["after"])
        observed_history[tick] = True
    need(set(observed_history) == set(expected_history), "MISSING_WORLD_HISTORY")
    for field, value in known.items():
        need(field in episode["final_state"] and same(value, episode["final_state"][field]),
             "FINAL_STATE_JOIN")
    return {"schema": "bioduet-evidence-trace-check/1",
            "episode_id_sha256": hashlib.sha256(next(iter(episode_ids)).encode()).hexdigest(),
            "condition": episode["condition"], "turns": len(records), "world_events": len(history),
            "retained_protocol_faults": faults, "partial_snapshot_fields_checked": sorted(known),
            "numeric_execution_receipts_verified": False,
            "scientific_validity": "not_assessed", "formal_score": None,
            "limitations": ["Pinned bytes and trace consistency do not prove producer honesty.",
                           "Partial world snapshots omit analysis-run mutations.",
                           "No numerical result, execution receipt or method-review authentication yet.",
                           "No science consequence/recovery score is computed."]}

def load_bundle(directory, expected_summary_sha256, expected_condition):
    need(expected_condition in ("H0", "H1"), "CONDITION")
    fd = directory_fd(directory)
    try:
        summary = read_pinned(fd, "summary.json", expected_summary_sha256)
        need(summary.get("condition") == expected_condition, "CONDITION")
        bundle = {"summary": summary}
        for key, filename in FILES.items():
            ref = summary.get(key)
            need(type(ref) is dict and set(ref) == {"name", "bytes", "sha256"}
                 and ref["name"] == filename, "REFERENCE")
            bundle[key] = read_pinned(fd, filename, ref["sha256"], ref["bytes"])
        check = validate_trace(summary, bundle["episode"])
        attempts = bundle["provider_ledger"]["attempts"]
        need(type(attempts) is list and type(summary["provider_attempt_count"]) is int
             and len(attempts) == summary["provider_attempt_count"], "ATTEMPT_COUNT")
        # Do not reinterpret legacy provider-ledger raw-availability wording.
        check["summary_sha256"] = expected_summary_sha256
        check["pinned_files"] = {key: summary[key] for key in FILES}
        check["provider_attempts"] = len(attempts)
        return {"private_bundle": bundle, "check": check}
    except EvidenceError:
        raise
    except (KeyError, TypeError, IndexError, AttributeError):
        raise EvidenceError("BUNDLE_SCHEMA") from None
    finally:
        os.close(fd)
