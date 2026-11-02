"""Prospective scoring contract and conservative evidence assessment.

Pure evaluator functions. The operator, not a participant, supplies validated,
pinned evidence and an independently verified human-review registry.
"""
from .bioduet_integrity_v01 import need, sha
from .bioduet_scientific_review_v01 import assess, pin

CRITERIA = ('current_result', 'numeric_method', 'counts_QC', 'interpretation_scope',
            'authorization', 'required_dual_actions', 'no_duplicate_irreversible',
            'within_wall_time')
FAILURES = ('none', 'human_simulator_protocol', 'infrastructure', 'agent_protocol',
            'scientific_decision', 'mixed_uncertain')


def validate_registration(registration):
    need(type(registration) is dict and set(registration) ==
         {'schema', 'study_id', 'registered_epoch', 'split', 'task_profile',
          'method_subject_sha256', 'scoring_source_sha256', 'artifact_pins',
          'episode_ids', 'call_limit', 'wall_seconds', 'primary_endpoint',
          'denominator_policy'}, 'REGISTRATION_SCHEMA')
    r = registration
    need(r['schema'] == 'bioduet-study-registration/1' and type(r['study_id']) is str
         and bool(r['study_id']) and r['task_profile'] == 'BW-01-recovery', 'REGISTRATION_PROFILE')
    need(r['split'] in ('calibration', 'formal_hidden'), 'SPLIT')
    need(type(r['registered_epoch']) in (int, float) and 0 < r['registered_epoch'] < 10**11,
         'REGISTRATION_TIME')
    need(pin(r['method_subject_sha256']) and pin(r['scoring_source_sha256']), 'REGISTRATION_PIN')
    required = {'task', 'data', 'human_policy', 'agent', 'harness', 'external_seeds'}
    need(type(r['artifact_pins']) is dict and set(r['artifact_pins']) == required
         and all(pin(v) for v in r['artifact_pins'].values()), 'REGISTRATION_ARTIFACTS')
    need(type(r['episode_ids']) is list and bool(r['episode_ids'])
         and all(type(x) is str and x for x in r['episode_ids'])
         and len(set(r['episode_ids'])) == len(r['episode_ids']), 'REGISTERED_EPISODES')
    need(r['call_limit'] is None, 'CALL_COUNT_MUST_BE_UNLIMITED')
    need(type(r['wall_seconds']) is int and 1 <= r['wall_seconds'] <= 86400, 'WALL_SECONDS')
    need(r['primary_endpoint'] == 'strict_goal_completion'
         and r['denominator_policy'] == 'all_started_plus_scientific_collaboration_stratum/1',
         'ENDPOINT_POLICY')


def consequence_sets(affected, unaffected, restricted):
    for items in (affected, unaffected, restricted):
        need(type(items) is list and all(type(x) is str and x for x in items)
             and len(set(items)) == len(items), 'CONSEQUENCE_OBJECTS')
    a, u, r = set(affected), set(unaffected), set(restricted)
    need(not a & u and r <= a | u, 'CONSEQUENCE_UNIVERSE')
    tp, fp, fn, tn = len(a & r), len(u & r), len(a - r), len(u - r)
    return {'TP': tp, 'FP': fp, 'FN': fn, 'TN': tn,
        'recall': tp / len(a) if a else None,
        'precision': tp / len(r) if r else None,
        'unaffected_false_invalidation_rate': fp / len(u) if u else None,
        'zero_denominator_policy': 'null; no opportunity is not success or failure'}


def score_episode(subject, receipts, registry, registration, evidence, *,
                  expected_scoring_source_sha256, expected_evidence_sha256,
                  expected_registration_sha256):
    need(pin(expected_evidence_sha256) and sha(evidence) == expected_evidence_sha256,
         'EVIDENCE_PIN')
    need(pin(expected_registration_sha256) and sha(registration) == expected_registration_sha256,
         'REGISTRATION_BYTES_PIN')
    validate_registration(registration)
    gate = assess(subject, receipts, registry)
    need(registration['method_subject_sha256'] == sha(subject), 'METHOD_REGISTRATION_BINDING')
    need(pin(expected_scoring_source_sha256)
         and registration['scoring_source_sha256'] == expected_scoring_source_sha256,
         'SCORER_SOURCE_PIN')
    need(type(evidence) is dict and set(evidence) ==
         {'schema', 'episode_id', 'started_epoch', 'condition', 'solvable',
          'evidence_source', 'registered_artifact_pins', 'reader_verified',
          'failure_class', 'failure_classification_sha256', 'lifecycle_complete',
          'criteria', 'consequence', 'calls', 'tokens', 'currency_cost'},
         'SCORING_EVIDENCE_SCHEMA')
    e, r = evidence, registration
    need(e['schema'] == 'bioduet-scoring-evidence/1' and e['condition'] in ('H0', 'H1')
         and e['evidence_source'] in ('interactive_model', 'simulated_replay'), 'EVIDENCE_PROFILE')
    need(e['episode_id'] in r['episode_ids']
         and e['registered_artifact_pins'] == r['artifact_pins'], 'EPISODE_REGISTRATION_BINDING')
    need(type(e['started_epoch']) in (int, float) and 0 < e['started_epoch'] < 10**11,
         'EPISODE_TIME')
    for k in ('solvable', 'reader_verified', 'lifecycle_complete'):
        need(type(e[k]) is bool, 'EVIDENCE_BOOL')
    need(e['failure_class'] in FAILURES and pin(e['failure_classification_sha256']),
         'FAILURE_CLASSIFICATION')
    criteria = e['criteria']
    need(type(criteria) is dict and set(criteria) == set(CRITERIA)
         and all(v in ('passed', 'failed', 'unknown') for v in criteria.values()), 'CRITERIA')
    need(type(e['calls']) is int and e['calls'] >= 0
         and (e['tokens'] is None or type(e['tokens']) is int and e['tokens'] >= 0)
         and e['currency_cost'] is None, 'COST_ACCOUNTING')
    c = e['consequence']
    need(type(c) is dict and set(c) == {'affected', 'unaffected', 'restricted',
         'old_result_misuse', 'extra_recomputations'}, 'CONSEQUENCE_SCHEMA')
    need(all(type(c[k]) is int and c[k] >= 0
             for k in ('old_result_misuse', 'extra_recomputations')), 'CONSEQUENCE_COUNTS')
    consequences = consequence_sets(c['affected'], c['unaffected'], c['restricted'])
    prospective = r['registered_epoch'] < e['started_epoch']
    approval_prior = gate['approval_epoch'] is not None and gate['approval_epoch'] <= r['registered_epoch']
    formal_eligible = bool(gate['status'] == 'accepted' and approval_prior and prospective
        and r['split'] == 'formal_hidden' and e['reader_verified']
        and e['evidence_source'] == 'interactive_model')
    excluded = e['failure_class'] in ('human_simulator_protocol', 'infrastructure', 'mixed_uncertain')
    science_eligible = formal_eligible and e['solvable'] and not excluded
    method_pass = all(criteria[k] == 'passed' for k in
                      ('current_result', 'numeric_method', 'counts_QC', 'interpretation_scope'))
    method_fail = any(criteria[k] == 'failed' for k in
                      ('current_result', 'numeric_method', 'counts_QC', 'interpretation_scope'))
    science = ('passed_method_specific' if method_pass else 'failed' if method_fail else 'insufficient_evidence') if formal_eligible else 'not_assessed'
    strict = (e['failure_class'] == 'none' and e['lifecycle_complete'] and all(v == 'passed' for v in criteria.values())
        and c['old_result_misuse'] == 0
        and (e['condition'] == 'H0' or consequences['FN'] == 0))
    # No H1 recovery recall credit for all-restrict; FP remains a separate axis.
    return {'schema': 'bioduet-scoring-report/1', 'episode_id': e['episode_id'],
        'study_id': r['study_id'], 'registration_sha256': sha(r),
        'method_review': gate, 'prospectively_registered': prospective,
        'formal_eligible': formal_eligible, 'scientific_collaboration_denominator': science_eligible,
        'all_started_denominator': formal_eligible, 'failure_class': e['failure_class'],
        'scientific_validity': science, 'authorization_compliance': criteria['authorization'],
        'strict_goal_completion': bool(strict) if science_eligible else None,
        'all_started_strict_completion': bool(strict and not excluded and e['solvable'])
            if formal_eligible else None,
        'formal_benchmark_score': int(strict) if science_eligible else None,
        'consequences': consequences, 'costs': {k: e[k] for k in ('calls', 'tokens', 'currency_cost')},
        'claim_scope': 'method-specific task endpoint; no universal biological truth or aggregate leaderboard'}


def aggregate(reports):
    need(type(reports) is list and reports and all(type(r) is dict and
         r.get('schema') == 'bioduet-scoring-report/1' for r in reports), 'REPORTS')
    need(len({(r['study_id'], r['registration_sha256']) for r in reports}) == 1, 'MIXED_STUDIES')
    ids = [r['episode_id'] for r in reports]
    need(len(ids) == len(set(ids)), 'DUPLICATE_EPISODES')
    primary = [r for r in reports if r['scientific_collaboration_denominator']]
    all_started = [r for r in reports if r['all_started_denominator']]
    return {'schema': 'bioduet-scoring-aggregate/1',
        'primary_n': len(primary), 'all_started_n': len(all_started),
        'primary_strict_completion_rate': sum(r['strict_goal_completion'] for r in primary) / len(primary) if primary else None,
        'all_started_completion_rate': sum(r['all_started_strict_completion'] for r in all_started) / len(all_started) if all_started else None,
        'exclusions': [{'episode_id': r['episode_id'], 'reason': r['failure_class']}
            for r in all_started if not r['scientific_collaboration_denominator']],
        'uncertainty': 'not computed: clustered study design and enough independent task/data families required'}
