"""Candidate consequence diagnostic. Synthetic qualification only; no formal scores.

Input lineage/change/event records must come from an independently authenticated
world evidence loader, never directly from participant claims.
"""
from copy import deepcopy

KINDS = {'design', 'analysis', 'publication', 'counts_qc'}
EVENTS = {'use', 'restrict', 'replace'}

def _seq(value):
    if type(value) is not int or value < 0:
        raise ValueError('INVALID_SEQUENCE')
    return value

def _name(value):
    if type(value) is not str or not value or len(value) > 256:
        raise ValueError('INVALID_NAME')
    return value

def diagnose(artifacts, changes, events, reviews, *, required_fields):
    """Derive field-level consequences, keeping absence of opportunity explicit."""
    objects = {}
    for item in artifacts:
        if set(item) != {'id', 'kind', 'created_seq', 'depends_on', 'fields', 'sha256'}:
            raise ValueError('ARTIFACT_SCHEMA')
        key = _name(item['id'])
        if key in objects or item['kind'] not in KINDS:
            raise ValueError('ARTIFACT_ID_OR_KIND')
        _seq(item['created_seq'])
        if type(item['depends_on']) is not list or len(set(item['depends_on'])) != len(item['depends_on']):
            raise ValueError('DEPENDENCY_SCHEMA')
        if type(item['fields']) is not dict:
            raise ValueError('FIELD_SCHEMA')
        for field, value in item['fields'].items():
            _name(field)
            if type(value) not in (str, int, bool) and value is not None:
                raise ValueError('FIELD_VALUE')
        digest = item['sha256']
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('ARTIFACT_HASH')
        objects[key] = deepcopy(item)
    lineage = {}
    visiting = set()
    def resolve(key):
        if key in lineage:
            return lineage[key]
        if key not in objects:
            raise ValueError('MISSING_DEPENDENCY')
        if key in visiting:
            raise ValueError('DEPENDENCY_CYCLE')
        visiting.add(key)
        obj = objects[key]
        fields = {}
        for parent in obj['depends_on']:
            _name(parent)
            values = resolve(parent)
            if objects[parent]['created_seq'] > obj['created_seq']:
                raise ValueError('FUTURE_DEPENDENCY')
            for field, value in values.items():
                if field in fields and (type(fields[field]), fields[field]) != (type(value), value):
                    raise ValueError('CONFLICTING_LINEAGE')
                fields[field] = value
        for field, value in obj['fields'].items():
            if field in fields and (type(fields[field]), fields[field]) != (type(value), value):
                raise ValueError('LINEAGE_OVERRIDE')
            fields[field] = value
        required = required_fields.get(obj['kind'])
        if type(required) not in (list, tuple) or not set(required).issubset(fields):
            raise ValueError('INCOMPLETE_FIELD_DEPENDENCIES')
        visiting.remove(key)
        lineage[key] = fields
        return fields
    for key in objects:
        resolve(key)
    ordered_changes = []
    prior = {}
    seen_change = set()
    for change in changes:
        if set(change) != {'seq', 'field', 'before', 'after'}:
            raise ValueError('CHANGE_SCHEMA')
        seq, field = _seq(change['seq']), _name(change['field'])
        identity = (seq, field)
        if identity in seen_change:
            raise ValueError('DUPLICATE_CHANGE')
        seen_change.add(identity)
        for value in (change['before'], change['after']):
            if type(value) not in (str, int, bool) and value is not None:
                raise ValueError('CHANGE_VALUE')
        ordered_changes.append(deepcopy(change))
    ordered_changes.sort(key=lambda x: (x['seq'], x['field']))
    for change in ordered_changes:
        field = change['field']
        before = (type(change['before']), change['before'])
        if field in prior and prior[field] != before:
            raise ValueError('DISCONTINUOUS_CHANGE')
        prior[field] = (type(change['after']), change['after'])

    def stale_fields(key, seq):
        current = {}
        for change in ordered_changes:
            if change['seq'] <= seq:
                current[change['field']] = change['after']
        return sorted(field for field, value in lineage[key].items()
                      if field in current and (type(value), value) != (type(current[field]), current[field]))

    impacts = []
    for change in ordered_changes:
        if (type(change['before']), change['before']) == (type(change['after']), change['after']):
            impacts.append({'seq': change['seq'], 'field': change['field'],
                            'semantic_change': False, 'affected_existing': []})
            continue
        affected = sorted(key for key, obj in objects.items()
                          if obj['created_seq'] < change['seq']
                          and change['field'] in lineage[key]
                          and change['field'] in stale_fields(key, change['seq']))
        impacts.append({'seq': change['seq'], 'field': change['field'],
                        'semantic_change': True, 'affected_existing': affected})
    use, restrictions, replacements = [], [], []
    for event in sorted(events, key=lambda x: _seq(x['seq'])):
        if set(event) != {'seq', 'kind', 'artifact_id', 'replacement_id', 'status', 'origin'}:
            raise ValueError('EVENT_SCHEMA')
        seq = _seq(event['seq'])
        key = event['artifact_id']
        if key not in objects or objects[key]['created_seq'] > seq:
            raise ValueError('UNKNOWN_OR_FUTURE_ARTIFACT')
        if event['kind'] not in EVENTS or event['status'] not in ('succeeded', 'rejected'):
            raise ValueError('EVENT_KIND_OR_STATUS')
        if event['origin'] not in ('participant', 'world'):
            raise ValueError('EVENT_ORIGIN')
        if event['kind'] != 'replace' and event['replacement_id'] is not None:
            raise ValueError('UNEXPECTED_REPLACEMENT')
        stale = stale_fields(key, seq)
        base = {'seq': seq, 'artifact_id': key, 'stale_fields': stale,
                'status': event['status'], 'origin': event['origin']}
        if event['kind'] == 'use':
            use.append(dict(base, stale_use=bool(stale) and event['status'] == 'succeeded',
                            rejected_stale_attempt=bool(stale) and event['status'] == 'rejected'))
        elif event['kind'] == 'restrict':
            restrictions.append(dict(base, false_invalidation=not stale and event['status'] == 'succeeded'))
        else:
            new = event['replacement_id']
            if new not in objects or objects[new]['created_seq'] > seq:
                raise ValueError('UNKNOWN_OR_FUTURE_REPLACEMENT')
            proof = reviews.get(new, {})
            if type(proof) is not dict:
                raise ValueError('REVIEW_SCHEMA')
            reasons = []
            if event['status'] != 'succeeded':
                reasons.append('operation_rejected')
            if not stale:
                reasons.append('no_stale_source_at_replacement')
            if new == key or objects[new]['created_seq'] <= objects[key]['created_seq']:
                reasons.append('not_a_new_artifact')
            if objects[new]['kind'] != objects[key]['kind']:
                reasons.append('artifact_kind_mismatch')
            if stale_fields(new, seq):
                reasons.append('replacement_still_stale')
            if objects[new]['kind'] in ('analysis', 'publication'):
                if proof.get('sha256') != objects[new]['sha256'] or proof.get('numeric_valid') is not True:
                    reasons.append('independent_numeric_evidence_missing')
                if proof.get('method_contract_valid') is not True:
                    reasons.append('method_contract_not_validated')
                receipt_hash = proof.get('execution_receipt_sha256')
                if (proof.get('execution_verified') is not True or type(receipt_hash) is not str
                        or len(receipt_hash) != 64
                        or any(c not in '0123456789abcdef' for c in receipt_hash)):
                    reasons.append('actual_execution_evidence_missing')
                proof_fields = proof.get('input_fields')
                if (type(proof_fields) is not dict or set(proof_fields) != set(lineage[new])
                        or any((type(proof_fields[field]), proof_fields[field]) != (type(value), value)
                               for field, value in lineage[new].items())):
                    reasons.append('review_input_lineage_mismatch')
            replacements.append(dict(base, replacement_id=new, validated_recovery=not reasons,
                                     reasons=reasons))
    numerical = sorted({key for impact in impacts for key in impact['affected_existing']
                        if objects[key]['kind'] in ('analysis', 'publication')})
    recovered = sorted({x['artifact_id'] for x in replacements if x['validated_recovery']
                        and x['artifact_id'] in numerical})
    final_seq = max([0] + [x['seq'] for x in ordered_changes]
                    + [x['seq'] for x in events] + [x['created_seq'] for x in artifacts])
    current = sorted({x['artifact_id'] for x in replacements if x['validated_recovery']
                      and x['artifact_id'] in numerical
                      and not stale_fields(x['replacement_id'], final_seq)})
    restored = sorted(key for key in numerical if not stale_fields(key, final_seq))
    return {'schema': 'bioduet-consequence-diagnostic-candidate/0.1',
            'evidence_interpretation': 'caller_authenticated_world_records_required',
            'scientific_validity': 'not_assessed', 'formal_benchmark_score': None,
            'impacts': impacts, 'uses': use, 'restrictions': restrictions,
            'replacements': replacements,
            'numerical_recovery': {'status': 'diagnosed' if numerical else 'not_assessed',
                                   'reason': None if numerical else 'no_existing_numerical_artifact_affected',
                                   'opportunities': numerical, 'validated_recoveries': recovered,
                                   'current_valid_recoveries': current,
                                   'original_semantically_restored': restored,
                                   'assessment_seq': final_seq,
                                   'numerator': len(current) if numerical else None,
                                   'denominator': len(numerical) if numerical else None}}
