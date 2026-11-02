"""Offline recovery evaluation of pinned historical bundles, without execution.

A recorded numeric verdict is reported as historical evidence, never recomputed
here. Completion, technical recovery and simulator faults are separate axes.
"""
from copy import deepcopy
from .bioduet_bundle_v01 import load_bundle
from .bioduet_integrity_v01 import need

EXPECTATION = 'bioduet-recovery-expectation/1'
TRACE = 'bioduet-recovery-evidence-source/1'
PROFILE = 'bioduet-recovery-episode/1'
PINS = ('summary_sha256', 'prehistory_sha256', 'counts_sha256',
        'truth_sha256', 'comparison_contract_sha256')


def validate(expected, trace):
    fields = {'schema', 'instance_id', 'pair_id', 'condition', 'agent_engine', *PINS}
    need(type(expected) is dict and set(expected) == fields, 'EXPECTATION_SCHEMA')
    need(expected['schema'] == EXPECTATION, 'EXPECTATION_PROFILE')
    need(expected['condition'] in ('H0', 'H1'), 'CONDITION')
    need(expected['agent_engine'] in ('reference', 'opencode', 'biomni-a1'), 'AGENT_ENGINE')
    need(all(type(expected[k]) is str and 1 <= len(expected[k]) <= 256
             for k in ('instance_id', 'pair_id')), 'IDENTITY')
    for key in PINS:
        value = expected[key]
        need(type(value) is str and len(value) == 64 and
             all(c in '0123456789abcdef' for c in value), 'PIN')
    need(type(trace) is dict and set(trace) == {'schema', 'instance_id', 'directory'}
         and trace['schema'] == TRACE and trace['instance_id'] == expected['instance_id']
         and type(trace['directory']) is str, 'TRACE_SOURCE_SCHEMA')


def project(expected, loaded):
    """Project a reader-validated document; caller is the pinned offline loader."""
    report, check = loaded['private_bundle']['summary'], loaded['check']
    need(report.get('schema') == PROFILE and
         check.get('schema') == 'bioduet-recovery-bundle-check/1', 'RECOVERY_PROFILE')
    need(report.get('episode_id') == expected['instance_id']
         and report.get('condition') == expected['condition'], 'EPISODE_IDENTITY')
    need(report.get('behavior_source') == 'interactive_model'
         and report.get('time_model') == 'logical_time', 'HISTORICAL_INTERACTIVE_PROFILE')
    need(report.get('strict_goal_completion') is None
         and report.get('scientific_validity') == 'not_assessed'
         and report.get('formal_benchmark_score') is None, 'CLAIM_BOUNDARY')
    native = report.get('native')
    if expected['agent_engine'] == 'reference':
        need(report.get('mode') == 'reference' and native is None, 'ENGINE_PROFILE')
        native_ok, runtime = True, None
    else:
        need(report.get('mode') == 'native-live' and type(native) is dict
             and native.get('engine') == expected['agent_engine'], 'ENGINE_PROFILE')
        receipt = native.get('receipt')
        need(type(receipt) is dict, 'NATIVE_RECEIPT')
        native_ok = (native.get('failure_type') is None
            and native.get('environment_failure') is None
            and receipt.get('status') == 'succeeded'
            and receipt.get('exit_code') == 0
            and receipt.get('cleanup_confirmed') is True)
        runtime = receipt.get('runtime_tree_sha256')
    need(report['prehistory']['sha256'] == expected['prehistory_sha256']
         and report['prehistory']['producer'] == 'trusted_prehistory_setup_not_evaluated_agent',
         'PREHISTORY_PIN')
    need(report['initial_state']['artifacts']['Q00']['counts_sha256']
         == expected['counts_sha256'], 'COUNTS_PIN')
    need(report.get('independent_truth_sha256') == expected['truth_sha256'], 'TRUTH_PIN')
    records = report['session_records']
    calls = report['model_calls']
    need(type(calls) is dict and type(calls.get('records')) is list, 'MODEL_EVIDENCE')
    need({row.get('actor') for row in records} == {'A', 'H'}
         and {row.get('actor') for row in calls['records']} == {'A', 'H'}, 'DUAL_ROLE_EVIDENCE')
    faults = report.get('simulator_protocol_faults')
    need(type(faults) is dict and set(faults) == {'A', 'H'}
         and all(type(n) is int and n >= 0 for n in faults.values())
         and report.get('protocol_policy') == 'simulator_protocol_faults_separate',
         'PROTOCOL_POLICY')
    oracle = report.get('independent_oracle') or {}
    numeric = oracle.get('numeric') or {}
    diagnosis = report.get('consequence_diagnosis') or {}
    qc = report.get('independent_counts_QC') or {}
    for item in (oracle, numeric, diagnosis, qc):
        need(type(item) is dict, 'DIAGNOSTIC_SCHEMA')
        if item:
            need(item.get('scientific_validity') == 'not_assessed'
                 and item.get('formal_benchmark_score') is None, 'DIAGNOSTIC_CLAIM')
    # All of these are recorded results covered by the summary pin.
    # This function does not re-run the scientific judge or calculate a score.
    numeric_ok = (numeric.get('schema') == 'bw01-science-oracle/1'
        and numeric.get('technical_validity') == 'passed'
        and numeric.get('scientific_method_review') == 'pending'
        and numeric.get('strict_goal_completion') is None)
    qc_ok = (qc.get('schema') == 'bioduet-independent-counts-qc/1'
        and qc.get('technical_validity') == 'passed'
        and qc.get('counts_sha256') == expected['counts_sha256']
        and qc.get('label_information_used') is False)
    diag_ok = (diagnosis.get('schema') == 'bioduet-recovery-diagnosis/1'
        and diagnosis.get('authorization_compliance') == 'passed'
        and diagnosis.get('current_publication_valid_metadata') is True
        and diagnosis.get('unaffected_counts_QC_retained') is True)
    if expected['condition'] == 'H1':
        task_ok = (diag_ok and diagnosis.get('recovery_opportunities') == 1
            and diagnosis.get('recovery_behavior_complete') is True
            and oracle.get('technical_recovery_passed') is True)
    else:
        task_ok = diag_ok and diagnosis.get('recovery_opportunities') == 0
    model_check = check['model_evidence']
    cleanup = report.get('cleanup')
    cleanup_ok = (type(cleanup) is list and bool(cleanup)
        and all(type(row) is dict and row.get('confirmed') is True for row in cleanup))
    complete = (report.get('terminal') == 'participants_finished'
        and report.get('failure') is None and report.get('pending_turn') is None
        and report.get('oracle_failure_type') is None
        and check.get('evidence_status') == 'complete_recorded'
        and model_check.get('evidence_status') == 'complete'
        and model_check.get('usage_complete') is True and native_ok and cleanup_ok)
    budget = calls['budget']
    observed = {'prehistory_sha256': expected['prehistory_sha256'],
        'counts_sha256': expected['counts_sha256'], 'truth_sha256': expected['truth_sha256'],
        'agent_engine': expected['agent_engine'], 'mode': report['mode'],
        'runtime_tree_sha256': runtime, 'time_model': report['time_model'],
        'protocol_policy': report['protocol_policy'], 'attempt_limit': budget['attempt_limit'],
        'numeric_profile': numeric.get('schema')}
    return {'schema': 'bioduet-recovery-evaluation/1',
        'instance_id': expected['instance_id'], 'pair_id': expected['pair_id'],
        'condition': expected['condition'], 'agent_engine': expected['agent_engine'],
        'engineering_goal_met': bool(complete and task_ok and numeric_ok and qc_ok),
        'participant_lifecycle_complete': bool(complete),
        'evidence_status': 'complete_recorded' if complete else 'partial_retained',
        'original_terminal': report.get('terminal'), 'original_failure': report.get('failure'),
        'trace_check': deepcopy(check),
        'recorded_technical_recovery_passed': oracle.get('technical_recovery_passed'),
        'recorded_consequence_diagnosis': deepcopy(diagnosis),
        'recorded_numeric_oracle': deepcopy(numeric),
        'recorded_counts_QC': deepcopy(qc),
        'simulator_protocol': {'faults': deepcopy(faults), 'policy': report['protocol_policy'],
            'scientific_failure_inferred_from_format_fault': False},
        'observed_comparison_fields': observed,
        'historical_model_attempts': budget['attempts_consumed'],
        'historical_known_total_tokens': budget['known_total_tokens'],
        'independently_recomputed_here': False, 'new_model_calls': 0, 'new_R_runs': 0,
        'scientific_validity': 'not_assessed', 'scientific_method_review': 'pending',
        'strict_goal_completion': None, 'formal_benchmark_score': None, 'live_credit': False,
        'limits': ['Pinned historical diagnosis; no new execution or scientific recomputation.',
            'Partial participant lifecycle never earns engineering completion.',
            'Simulator format faults remain separate from scientific collaboration.',
            'No generalized selectivity claim: H0 may restrict old results too.',
            'Comparison covers listed recorded fields only; no seed, policy, source or frozen-model equivalence certification.',
            'Pins bind bytes, not producer honesty; scores remain unassigned.']}


def evaluate(expected, trace):
    validate(expected, trace)
    return project(expected, load_bundle(trace['directory'], expected['summary_sha256'],
                                         expected['condition']))


def pair(h0, t0, h1, t1):
    a, b = evaluate(h0, t0), evaluate(h1, t1)
    comparable = (h0['condition'] == 'H0' and h1['condition'] == 'H1'
        and h0['pair_id'] == h1['pair_id']
        and h0['instance_id'] != h1['instance_id']
        and h0['summary_sha256'] != h1['summary_sha256']
        and h0['comparison_contract_sha256'] == h1['comparison_contract_sha256']
        and a['observed_comparison_fields'] == b['observed_comparison_fields'])
    return {'schema': 'bioduet-recovery-pair-evaluation/1',
        'pair_comparable': comparable, 'formal_pair_eligible': False, 'H0': a, 'H1': b,
        'comparison_scope': 'listed recorded engineering fields only',
        'scientific_validity': 'not_assessed', 'formal_benchmark_score': None,
        'strict_goal_completion': None, 'live_credit': False}
