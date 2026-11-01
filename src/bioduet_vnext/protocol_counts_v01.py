"""Versioned protocol-error evidence reader. Not a task-success evaluator."""
from collections.abc import Mapping

SCHEMA = "bioduet.protocol-error-count/1"

def read_protocol_errors(record, *, list_field, count_field, source_schema,
                         evidence_ref, coverage="recorded_events_only"):
    """Read one declared schema mapping; never infer missing observations as zero."""
    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping")
    if list_field == count_field:
        raise ValueError("list and count fields must differ")
    if not all(isinstance(x, str) and x for x in
               (list_field, count_field, source_schema, evidence_ref, coverage)):
        raise ValueError("nonempty source identity and field names required")
    result = dict(schema=SCHEMA, source_schema=source_schema,
                  evidence_ref=evidence_ref, coverage=coverage, count=None,
                  state="unknown", reason="missing", observed={})
    has_list, has_count = list_field in record, count_field in record
    values = []
    for field, present, expected in ((list_field, has_list, list),
                                    (count_field, has_count, int)):
        if not present:
            continue
        value = record[field]
        if type(value) is not expected or (expected is int and value < 0):
            result.update(state="invalid", reason="invalid_" + field)
            result["observed"][field] = {"type": type(value).__name__}
            return result
        count = len(value) if expected is list else value
        result["observed"][field] = {"type": expected.__name__, "count": count}
        values.append(count)
    if not values:
        return result
    if len(set(values)) != 1:
        result.update(state="conflict", reason="list_count_disagree")
        return result
    result.update(count=values[0], state="known", reason=None)
    return result
