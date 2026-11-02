"""Trusted in-process engineering replay; not a participant security sandbox."""
import json
import time
import traceback
from pathlib import Path
from bioduet_eval.bioduet_logical_v02 import LogicalSession, Bw01EngineeringWorld
from bioduet_eval.bw01_fixtures_v01 import scripted_response

def fixture(packet):
    """Explicit synthetic participant; never a model or independent scientist."""
    response = scripted_response({"model": "synthetic", "messages": [
        {"content": json.dumps({"turn": packet})}]})
    return json.loads(response["response"]["choices"][0]["message"]["content"])

def run(output, *, condition="H1", participant=fixture, wall_seconds=30):
    if type(wall_seconds) not in (int, float) or not 0 < wall_seconds <= 3600:
        raise ValueError("FINITE_WALL_REQUIRED")
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    session = LogicalSession(Bw01EngineeringWorld(condition), max_turns=None)
    start = time.monotonic()
    failure = None
    terminal = None
    # Caller-supplied participants are trusted Python callables. The operator must
    # enforce a process deadline for blocking/untrusted participants.
    with (output / "events.jsonl").open("x", encoding="utf-8") as events:
        try:
            while time.monotonic() - start < wall_seconds:
                packet = session.next_turn()
                if packet is None:
                    terminal = session.terminal
                    break
                events.write(json.dumps({"type": "turn", "packet": packet}) + "\n")
                events.flush()
                decision = participant(packet)
                events.write(json.dumps({"type": "decision", "decision": decision}) + "\n")
                events.flush()
                record = session.submit(packet["turn_token"], decision)
                events.write(json.dumps({"type": "result", "record": record}) + "\n")
                events.flush()
            else:
                terminal = "wall_deadline"
        except Exception as exc:
            failure = {"type": type(exc).__name__}
            with (output / "failure.txt").open("x", encoding="utf-8") as raw:
                raw.write(traceback.format_exc())
            terminal = "participant_or_runner_error"
            events.write(json.dumps({"type": "failure", "error": failure}) + "\n")
            events.flush()
        finally:
            report = session.report()
            report.update(terminal=terminal, failure=failure, condition=condition,
                          formal_benchmark_score=None, strict_score=None,
                          max_model_calls=None, max_turns=None,
                          participant_source="synthetic_fixture" if participant is fixture else "caller_supplied",
                          wall_seconds=wall_seconds)
            # Kernel report labels are valid only for the synthetic fixture.
            if participant is not fixture:
                report["behavior_source"] = "caller_supplied_unverified"
                report["actual_model_calls"] = None
            with (output / "report.json").open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2)
    return report
