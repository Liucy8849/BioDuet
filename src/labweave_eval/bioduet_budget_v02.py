"""Pure controller-side candidate; no grant authorization or process enforcement.

A trusted controller must validate a fresh Root grant before construction. It must
serialize calls to this object, persist journal entries, apply returned timeouts
to transports, capture raw responses separately, and enforce cleanup externally.
An attempt consumes budget before external dispatch. Unknown/failed calls are
never refunded. This object never retries, fills actions, or decides science.
"""
import copy
import hashlib
import json
import math

class BudgetError(ValueError):
    pass

def need(condition, code):
    if not condition:
        raise BudgetError(code)

def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0

def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()

class EpisodeBudget:
    def __init__(self, *, episode_id, grant_id, clock, journal,
                 trusted_wall_now, grant_expires_wall, episode_seconds=1200,
                 max_attempts=None, cleanup_seconds=15):
        need(type(episode_id) is str and 1 <= len(episode_id) <= 128, "EPISODE_ID")
        need(type(grant_id) is str and 1 <= len(grant_id) <= 128, "GRANT_ID")
        need(callable(clock) and callable(journal), "CALLBACK")
        need(positive(trusted_wall_now) and positive(grant_expires_wall), "WALL_TIME")
        need(positive(episode_seconds) and episode_seconds <= 14400
             and positive(cleanup_seconds), "DURATION")
        need(max_attempts is None, "CALL_COUNT_MUST_BE_UNLIMITED")
        remaining_grant = grant_expires_wall - trusted_wall_now
        need(remaining_grant > cleanup_seconds and episode_seconds > cleanup_seconds,
             "EXPIRED_OR_INSUFFICIENT_GRANT")
        self._clock, self._journal = clock, journal
        now = clock()
        need(type(now) in (int, float) and math.isfinite(now) and now >= 0, "CLOCK")
        self._last_clock = now
        self._hard_deadline = now + min(remaining_grant, episode_seconds)
        self._work_deadline = self._hard_deadline - cleanup_seconds
        self._max_attempts = max_attempts
        self._attempts = {}
        self._last_hash = "0" * 64
        self._sequence = 0
        self._closed = False
        self._broken = False
        self._identity = {"episode_id": episode_id, "grant_id": grant_id}
        self._write("opened", {"hard_deadline": self._hard_deadline,
                               "work_deadline": self._work_deadline,
                               "max_attempts": max_attempts})

    def _now(self):
        need(not self._broken, "BROKEN")
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now < self._last_clock:
            self._broken = True
            raise BudgetError("CLOCK_ROLLBACK_OR_INVALID")
        self._last_clock = now
        return now

    def _write(self, kind, fields):
        record = {**self._identity, "sequence": self._sequence,
                  "previous_sha256": self._last_hash, "kind": kind,
                  "fields": copy.deepcopy(fields)}
        record["sha256"] = sha(record)
        try:
            # Never allow a sink to mutate the controller's internal record.
            self._journal(copy.deepcopy(record))
        except Exception:
            self._broken = True
            raise BudgetError("JOURNAL_FAILED") from None
        self._last_hash = record["sha256"]
        self._sequence += 1

    def deadline(self, stage_seconds, *, parent_deadline=None):
        need(not self._closed, "CLOSED")
        need(positive(stage_seconds), "STAGE_DURATION")
        now = self._now()
        stop = min(now + stage_seconds, self._work_deadline)
        if parent_deadline is not None:
            need(positive(parent_deadline), "PARENT_DEADLINE")
            stop = min(stop, parent_deadline)
        need(stop > now, "DEADLINE_EXHAUSTED")
        return {"absolute_monotonic": stop, "timeout_seconds": stop - now,
                "hard_deadline": self._hard_deadline}

    def reserve(self, *, actor, purpose, request_sha256, stage_seconds,
                parent_deadline=None):
        need(not self._closed, "CLOSED")
        need(actor in ("A", "H") and purpose in ("primary", "auxiliary", "retry"), "CALL_KIND")
        need(type(request_sha256) is str and len(request_sha256) == 64
             and all(c in "0123456789abcdef" for c in request_sha256), "REQUEST_HASH")
        # Count every attempt; no call-count refusal. Deadlines still gate dispatch.
        timing = self.deadline(stage_seconds, parent_deadline=parent_deadline)
        number = len(self._attempts) + 1
        token = "call-%04d" % number
        row = {"number": number, "actor": actor, "purpose": purpose,
               "request_sha256": request_sha256, "status": "reserved",
               "deadline": timing["absolute_monotonic"], "usage": None,
               "response_sha256": None, "dispatch_started": False}
        # Consume first. Journal failure is fail-stop; dispatch receives no token.
        self._attempts[token] = row
        self._write("reserved", {"token": token, **row})
        return {"token": token, **timing}

    def authorize_dispatch(self, token):
        """Only this second gate permits one transport send, with a fresh timeout."""
        need(not self._closed, "CLOSED")
        now = self._now()
        need(token in self._attempts, "UNKNOWN_ATTEMPT")
        row = self._attempts[token]
        need(row["status"] == "reserved" and not row["dispatch_started"], "ALREADY_DISPATCHED_OR_SETTLED")
        remaining = row["deadline"] - now
        need(remaining > 0, "DEADLINE_EXHAUSTED")
        row["dispatch_started"] = True
        self._write("dispatch_authorized", {"token": token, "at": now,
                                            "timeout_seconds": remaining})
        return {"token": token, "timeout_seconds": remaining,
                "absolute_monotonic": row["deadline"]}

    def complete(self, token, *, status, response_sha256=None, usage=None):
        need(not self._closed, "CLOSED")
        now = self._now()
        need(token in self._attempts, "UNKNOWN_ATTEMPT")
        row = self._attempts[token]
        need(row["status"] == "reserved", "ALREADY_SETTLED")
        need(status in ("succeeded", "failed", "unknown"), "STATUS")
        if response_sha256 is not None:
            need(type(response_sha256) is str and len(response_sha256) == 64
                 and all(c in "0123456789abcdef" for c in response_sha256), "RESPONSE_HASH")
        if status in ("succeeded", "unknown"):
            need(row["dispatch_started"], "NOT_DISPATCHED")
        if status == "succeeded":
            need(response_sha256 is not None, "SUCCESS_REQUIRES_RAW_RESPONSE_PIN")
        if usage is not None:
            need(type(usage) is dict and set(usage) == {"prompt_tokens", "completion_tokens", "total_tokens"},
                 "USAGE_SCHEMA")
            need(all(type(v) is int and v >= 0 for v in usage.values()), "USAGE_VALUE")
            need(usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"],
                 "USAGE_SUM")
        row.update(status=status, response_sha256=response_sha256,
                   usage=copy.deepcopy(usage), completed_at=now,
                   late=now >= row["deadline"])
        self._write("completed", {"token": token, **row})
        return copy.deepcopy(row)

    def close(self, reason):
        need(not self._closed, "CLOSED")
        need(type(reason) is str and 1 <= len(reason) <= 128, "CLOSE_REASON")
        now = self._now()
        # Sent outcomes become unknown; queued reservations remain known not dispatched.
        unsettled = []
        for token, row in self._attempts.items():
            if row["status"] == "reserved":
                row.update(status="unknown" if row["dispatch_started"] else "not_dispatched", usage=None, response_sha256=None)
                unsettled.append(token)
        self._closed = True
        self._write("closed", {"reason": reason, "unsettled_classified": unsettled,
                               "closed_at": now, "physical_cleanup_confirmed": False})
        return self.snapshot()

    def snapshot(self):
        rows = list(self._attempts.values())
        known_usage = [r["usage"] for r in rows if r["usage"] is not None]
        return {"attempts_consumed": len(rows), "attempt_limit": self._max_attempts,
                "remaining_attempts": None,
                "outcomes": {s: sum(r["status"] == s for r in rows)
                             for s in ("reserved", "succeeded", "failed", "unknown", "not_dispatched")},
                "by_actor": {a: sum(r["actor"] == a for r in rows) for a in ("A", "H")},
                "by_purpose": {a: sum(r["purpose"] == a for r in rows)
                               for a in ("primary", "auxiliary", "retry")},
                "usage_reported_attempts": len(known_usage),
                "usage_complete": len(known_usage) == len(rows),
                "known_total_tokens": sum(u["total_tokens"] for u in known_usage),
                "closed": self._closed, "broken": self._broken,
                "journal_tail_sha256": self._last_hash,
                "physical_cleanup_confirmed": False,
                "cost_currency": None,
                "live_enforcement_integrated": False}
