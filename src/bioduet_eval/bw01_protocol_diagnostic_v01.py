"""Separate simulator protocol diagnostics; never rewrite or rescore an episode.

CLI analyses historical receipts retrospectively. A clear protocol gate does not
establish scientific validity, solvability, or eligibility for a formal score.
"""
import argparse
import hashlib
import json
from pathlib import Path

POLICY_ID = "bw01-simulator-protocol-separation/0.1"
SCHEMA_REASONS = frozenset({
    "DECISION_SCHEMA", "DECISION_OBJECT_REQUIRED", "ACTION_OBJECT_REQUIRED",
    "ACTION_SCHEMA", "MESSAGE_SCHEMA", "SCIENCE_DESIGN_SCHEMA",
})


def assess(report):
    rows = report.get("transcript")
    records = report.get("session_records")
    if not isinstance(rows, list) or not rows or not isinstance(records, list):
        raise ValueError("INCOMPLETE_TRACE")
    # Join the two trusted recorder views; absence is not evidence of no fault.
    submissions = [row.get("submission") for row in rows]
    if submissions != records:
        raise ValueError("TRACE_RECORD_MISMATCH")
    faults = {"A": [], "H": []}
    other_rejections = {"A": [], "H": []}
    turns = {"A": 0, "H": 0}
    for row, record in zip(rows, records):
        if not isinstance(record, dict):
            raise ValueError("TRACE_RECORD")
        actor = row.get("actor")
        if actor not in turns or actor != record.get("actor"):
            raise ValueError("TRACE_ACTOR")
        turns[actor] += 1
        result = record.get("result")
        if not isinstance(result, dict):
            raise ValueError("TRACE_RESULT")
        reason = result.get("reason")
        parse_error = row.get("parse_error")
        code = None
        if parse_error == "INVALID_MODEL_JSON":
            if result.get("status") != "rejected":
                raise ValueError("PARSE_RESULT_MISMATCH")
            code = "INVALID_MODEL_JSON"
        elif parse_error is not None:
            raise ValueError("UNKNOWN_PARSE_ERROR")
        elif result.get("status") == "rejected" and reason in SCHEMA_REASONS:
            code = reason
        event = {"seq": record.get("seq"), "tick": record.get("tick")}
        if code:
            event["code"] = code
            request = record.get("decision", {}).get("request")
            if code == "ACTION_SCHEMA" and isinstance(request, dict):
                if request.get("action_id") != "A01" and "operation_id" not in request:
                    event["detail"] = "missing_operation_id"
            faults[actor].append(event)
        elif result.get("status") == "rejected":
            # E.g. wrong current version, unavailable capability, absent evidence:
            # keep these scientific/coordination decisions out of protocol faults.
            other_rejections[actor].append({**event, "reason": reason})
    if not all(turns.values()):
        raise ValueError("MISSING_PARTICIPANT_TRACE")
    human_failed = bool(faults["H"])
    return {
        "schema": "bw01-protocol-diagnostic/1",
        "policy_id": POLICY_ID,
        "simulator_protocol_status": "failed" if human_failed else "passed",
        "simulator_protocol_faults": faults["H"],
        "agent_protocol_faults": faults["A"],
        "other_rejections": other_rejections,
        "observed_turns": turns,
        "prospective_protocol_gate": "blocked" if human_failed else "clear",
        "agent_scientific_failure_attributable_from_joint_failure": None,
        "formal_benchmark_score": None,
        "limitations": [
            "Protocol status is separate from science, authorization and joint completion.",
            "Absence of a protocol fault does not establish eligibility for a formal score.",
            "Scientific label errors and unavailable evidence are not protocol faults.",
            "All faults count even if later recovered or joint completion succeeds.",
            "This classifier does not repair decisions, retry models or assign agent scores.",
        ],
    }


def _read(path):
    raw = path.read_bytes()
    return json.loads(raw), {"path": str(path), "bytes": len(raw),
                            "sha256": hashlib.sha256(raw).hexdigest()}


def diagnose(directory, output):
    directory = Path(directory).resolve()
    report, report_ref = _read(directory / "episode-private.json")
    summary, summary_ref = _read(directory / "summary.json")
    declared = summary.get("episode", {})
    if declared.get("sha256") != report_ref["sha256"]:
        raise ValueError("EPISODE_HASH_MISMATCH")
    if report.get("condition") != summary.get("condition"):
        raise ValueError("CONDITION_MISMATCH")
    result = assess(report)
    result.update(
        assessment_mode="retrospective_diagnostic",
        policy_applied_after_run=True,
        historical_primary_metric_eligibility=None,
        original_outcomes={
            "condition": summary.get("condition"),
            "terminal": summary.get("terminal"),
            "engineering_scientific_path_passed": summary.get("engineering_scientific_path_passed"),
            "trace_judgment": summary.get("trace_judgment"),
            "technical_science_validity": summary.get("technical_science_validity"),
            "scientific_validity": summary.get("scientific_validity"),
        },
        inputs=[report_ref, summary_ref],
        classifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    # Only a new sidecar; cannot overwrite even an existing diagnostic.
    with Path(output).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = diagnose(args.episode_directory, args.output)
    print(json.dumps({"output": str(args.output),
                      "simulator_protocol_status": result["simulator_protocol_status"],
                      "assessment_mode": result["assessment_mode"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
