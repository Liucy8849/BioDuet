"""Evaluator-only method-review gate. Never creates or authenticates signatures.

The trusted receipt registry must be supplied outside participant inputs by an
operator who actually verified the human review. Hash membership cannot prove a
reviewer's identity. Empty registry means pending, never automatic acceptance.
"""
from .bioduet_window_v01 import need, sha
SUBJECT = 'bioduet-method-review-subject/1'
RECEIPT = 'bioduet-human-method-review/1'
CHECKS = ('provenance', 'reuse_scope', 'cell_selection', 'replication',
          'design_confounding', 'normalization_filtering', 'ql_options',
          'multiplicity_tolerances', 'independent_oracle_limits',
          'consequence_truth', 'interpretation_scope', 'reachability')


def pin(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def assess(subject, receipts, trusted_receipt_registry):
    need(type(subject) is dict and set(subject) ==
         {'schema', 'task_profile', 'method_id', 'artifacts', 'author_ids', 'required_reviewers'},
         'SUBJECT_SCHEMA')
    need(subject['schema'] == SUBJECT and subject['task_profile'] == 'BW-01-recovery'
         and subject['method_id'] == 'bw01-paired-edger-ql/0.1', 'SUBJECT_PROFILE')
    artifacts = subject['artifacts']
    need(type(artifacts) is dict and bool(artifacts)
         and all(type(k) is str and pin(v) for k, v in artifacts.items()), 'ARTIFACT_PINS')
    authors, reviewers = subject['author_ids'], subject['required_reviewers']
    need(type(authors) is list and authors and all(type(x) is str and x for x in authors)
         and type(reviewers) is list and len(reviewers) == 2
         and len(set(reviewers)) == 2 and all(type(x) is str and x for x in reviewers)
         and not set(authors) & set(reviewers), 'REVIEW_INDEPENDENCE')
    need(type(receipts) is list and type(trusted_receipt_registry) is dict, 'REGISTRY')
    accepted, pending, rejected = [], list(reviewers), []
    seen = set()
    for receipt in receipts:
        need(type(receipt) is dict and set(receipt) ==
             {'schema', 'reviewer_id', 'role', 'subject_sha256', 'decision',
              'checks', 'unresolved_conditions', 'reviewed_epoch', 'original_evidence_sha256'},
             'REVIEW_RECEIPT_SCHEMA')
        who = receipt['reviewer_id']
        need(type(who) is str and who in reviewers and who not in seen, 'REVIEWER_ID')
        seen.add(who)
        need(receipt['schema'] == RECEIPT and receipt['role'] == 'human_domain'
             and receipt['subject_sha256'] == sha(subject), 'REVIEW_BINDING')
        need(receipt['decision'] in ('accepted', 'conditional', 'rejected')
             and type(receipt['unresolved_conditions']) is list
             and all(type(x) is str and x for x in receipt['unresolved_conditions']),
             'REVIEW_DECISION')
        need(type(receipt['reviewed_epoch']) in (int, float)
             and 0 < receipt['reviewed_epoch'] < 10**11
             and pin(receipt['original_evidence_sha256']), 'REVIEW_PROVENANCE')
        checks = receipt['checks']
        need(type(checks) is dict and set(checks) == set(CHECKS)
             and all(v in ('accepted', 'pending', 'rejected') for v in checks.values()),
             'REVIEW_CHECKS')
        # Operator-owned registry binds both receipt and actual external original.
        trusted = trusted_receipt_registry.get(who)
        verified = (type(trusted) is dict
            and set(trusted) == {'receipt_sha256', 'original_evidence_sha256'}
            and trusted['receipt_sha256'] == sha(receipt)
            and trusted['original_evidence_sha256'] == receipt['original_evidence_sha256'])
        if not verified:
            continue
        if receipt['decision'] == 'rejected' or 'rejected' in checks.values():
            rejected.append(who)
        elif (receipt['decision'] == 'accepted' and not receipt['unresolved_conditions']
              and all(v == 'accepted' for v in checks.values())):
            accepted.append(who); pending.remove(who)
    status = 'rejected' if rejected else 'accepted' if len(accepted) == 2 else 'pending'
    return {'schema': 'bioduet-method-review-gate/1', 'subject_sha256': sha(subject),
        'status': status, 'accepted_reviewers': accepted, 'pending_reviewers': pending,
        'rejected_reviewers': rejected,
        'approval_epoch': max((r['reviewed_epoch'] for r in receipts), default=None)
            if status == 'accepted' else None,
        'authentication_scope': 'operator-verified external human receipts required; pins alone do not authenticate people',
        'formal_benchmark_score': None}
