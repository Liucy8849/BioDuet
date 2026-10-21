"""Fresh, append-only controller budget journal candidate.

No resume-dispatch capability. Recovery is read-only evidence inspection, never
permission to reuse a grant or resend a request. Partial files remain untouched.
The caller owns a private output directory; raw provider responses live elsewhere.
"""
import hashlib
import json
import math
import os
import stat

MAX_LINE = 32768
MAX_FILE = 1024 * 1024
KINDS = {
    "opened": {"hard_deadline", "work_deadline", "max_attempts"},
    "reserved": {"token", "number", "actor", "purpose", "request_sha256", "status",
                 "deadline", "usage", "response_sha256", "dispatch_started"},
    "dispatch_authorized": {"token", "at", "timeout_seconds"},
    "completed": {"token", "number", "actor", "purpose", "request_sha256", "status",
                  "deadline", "usage", "response_sha256", "dispatch_started",
                  "completed_at", "late"},
    "closed": {"reason", "unsettled_classified", "closed_at", "physical_cleanup_confirmed"},
}
class JournalError(ValueError):
    pass

def need(ok, code):
    if not ok:
        raise JournalError(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def strict(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            need(key not in out, "DUPLICATE_JSON_KEY")
            out[key] = value
        return out
    def constant(value):
        raise JournalError("NONFINITE")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        # Also rejects exponent overflow into infinity.
        canonical(value)
        return value
    except JournalError:
        raise
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise JournalError("INVALID_JSON") from None

def open_directory(path):
    path = os.fspath(path)
    need(type(path) is str and path.startswith("/"), "ABSOLUTE_DIRECTORY")
    parts = path.split("/")[1:]
    need(parts and all(x and x not in (".", "..") for x in parts), "DIRECTORY_PATH")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise

def validate_record(record, sequence, previous, identity):
    need(type(record) is dict and set(record) ==
         {"episode_id", "grant_id", "sequence", "previous_sha256", "kind", "fields", "sha256"},
         "RECORD_SCHEMA")
    need(type(record["sequence"]) is int and record["sequence"] == sequence, "SEQUENCE")
    need(record["previous_sha256"] == previous, "CHAIN")
    pair = (record["episode_id"], record["grant_id"])
    need(all(type(v) is str and 1 <= len(v) <= 128 for v in pair), "IDENTITY")
    need(identity is None or pair == identity, "CROSS_EPISODE_OR_GRANT")
    need(record["kind"] in KINDS and type(record["fields"]) is dict
         and set(record["fields"]) == KINDS[record["kind"]], "FIELDS")
    body = {k: v for k, v in record.items() if k != "sha256"}
    need(hashlib.sha256(canonical(body)).hexdigest() == record["sha256"], "HASH")
    return pair

def inspect_records(records):
    need(bool(records) and records[0]["kind"] == "opened", "OPEN_REQUIRED")
    opened = records[0]["fields"]
    need(type(opened["max_attempts"]) is int and 1 <= opened["max_attempts"] <= 30, "ATTEMPT_LIMIT")
    attempts, closed = {}, False
    for record in records[1:]:
        need(not closed, "AFTER_CLOSE")
        kind, f = record["kind"], record["fields"]
        need(kind != "opened", "DUPLICATE_OPEN")
        if kind == "reserved":
            token = f["token"]
            need(type(token) is str and token not in attempts and len(attempts) < opened["max_attempts"], "RESERVATION")
            need(type(f["number"]) is int and f["number"] == len(attempts) + 1
                 and token == "call-%04d" % f["number"] and f["status"] == "reserved"
                 and f["dispatch_started"] is False, "RESERVATION")
            attempts[token] = {"reservation": f, "dispatch": False, "result": None}
        elif kind == "dispatch_authorized":
            need(f["token"] in attempts, "UNKNOWN_ATTEMPT")
            a = attempts[f["token"]]
            need(not a["dispatch"] and a["result"] is None, "DUPLICATE_DISPATCH")
            a["dispatch"] = True
        elif kind == "completed":
            need(f["token"] in attempts, "UNKNOWN_ATTEMPT")
            a = attempts[f["token"]]
            need(a["result"] is None and f["status"] in ("succeeded", "failed", "unknown"), "COMPLETION")
            need(f["dispatch_started"] is a["dispatch"], "DISPATCH_JOIN")
            need(f["status"] == "failed" or a["dispatch"], "UNSENT_SUCCESS_OR_UNKNOWN")
            for key in ("token", "number", "actor", "purpose", "request_sha256", "deadline"):
                need(canonical(f[key]) == canonical(a["reservation"][key]), "RESERVATION_JOIN")
            a["result"] = f["status"]
        elif kind == "closed":
            pending = [k for k, a in attempts.items() if a["result"] is None]
            need(f["unsettled_classified"] == pending and f["physical_cleanup_confirmed"] is False, "CLOSE_JOIN")
            closed = True
    outcomes = {"succeeded": 0, "failed": 0, "unknown": 0, "not_dispatched": 0}
    for a in attempts.values():
        status = a["result"] or ("unknown" if a["dispatch"] else "not_dispatched")
        outcomes[status] += 1
    return {"attempts_consumed": len(attempts), "outcomes": outcomes, "closed_record_present": closed,
            "resume_dispatch_permitted": False, "physical_cleanup_confirmed": False,
            "interpretation": "Dispatch authorization without completion is conservatively unknown; it does not prove that an HTTP request was sent."}

class FreshJournal:
    def __init__(self, directory, filename="budget.jsonl"):
        need(filename == "budget.jsonl", "FILENAME")
        self._dir = open_directory(directory)
        self._fd = None
        self._records = []
        self._broken = False
        self._bytes = 0
        try:
            st = os.fstat(self._dir)
            need(st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o700, "PRIVATE_DIRECTORY")
            self._fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                               0o600, dir_fd=self._dir)
            os.fsync(self._fd)
            os.fsync(self._dir)
        except BaseException:
            self.close()
            raise

    def __call__(self, record):
        need(not self._broken and self._fd is not None, "JOURNAL_UNAVAILABLE")
        try:
            seq = len(self._records)
            previous = self._records[-1]["sha256"] if seq else "0" * 64
            identity = (self._records[0]["episode_id"], self._records[0]["grant_id"]) if seq else None
            validate_record(record, seq, previous, identity)
            data = canonical(record) + b"\n"
            need(len(data) <= MAX_LINE and self._bytes + len(data) <= MAX_FILE, "JOURNAL_SIZE")
            snapshot = strict(data)
            inspect_records(self._records + [snapshot])
            offset = 0
            while offset < len(data):
                count = os.write(self._fd, data[offset:])
                need(count > 0, "SHORT_WRITE")
                offset += count
            os.fsync(self._fd)
            self._bytes += len(data)
            self._records.append(snapshot)
        except Exception:
            self._broken = True
            raise

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self._dir is not None:
            os.close(self._dir)
            self._dir = None

def inspect_journal(directory):
    fd = open_directory(directory)
    f = None
    try:
        f = os.open("budget.jsonl", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        before = os.fstat(f)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o600, "PRIVATE_FILE")
        need(0 < before.st_size <= MAX_FILE, "JOURNAL_SIZE")
        data = b""
        while len(data) <= MAX_FILE:
            block = os.read(f, min(65536, MAX_FILE + 1 - len(data)))
            if not block:
                break
            data += block
        after = os.fstat(f)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode, s.st_nlink)
        need(identity(before) == identity(after) and len(data) == before.st_size, "FILE_CHANGED")
        need(data.endswith(b"\n"), "PARTIAL_TAIL")
        records, pair, previous = [], None, "0" * 64
        for line in data.splitlines():
            need(0 < len(line) < MAX_LINE, "LINE_SIZE")
            record = strict(line)
            pair = validate_record(record, len(records), previous, pair)
            records.append(record)
            previous = record["sha256"]
        result = inspect_records(records)
        result.update(records=len(records), sha256=hashlib.sha256(data).hexdigest(),
                      journal_tail_sha256=previous, file_bytes=len(data), file_modified=False,
                      durability_claim="Successful write callbacks required fsync; reading a valid file cannot prove the final pre-crash fsync completed.")
        return result
    finally:
        if f is not None:
            os.close(f)
        os.close(fd)
