"""Read-only retrospective diagnostics. Never issues formal or strict scores.

Only initial R00/P00/Q00 form this explicitly declared object universe.
Metadata consequences are derived from pinned truth and submitted actions.
Numeric verdicts are read from existing receipts, never recomputed.
"""
from .bioduet_window_v01 import need
from .bioduet_scoring_v01 import consequence_sets


def diagnose(summary, truth, *, failure_class):
    need(summary.get('schema') == 'bioduet-recovery-episode/1', 'EPISODE_PROFILE')
    need(summary.get('condition') in ('H0','H1'), 'CONDITION')
    need(type(failure_class) is str and failure_class, 'FAILURE_CLASS')
    initial, final = summary['initial_state'], summary['final_state']
    need({'R00','Q00'} <= set(initial['artifacts'])
         and 'P00' in initial['publications'], 'DECLARED_INITIAL_OBJECTS')
    expected = {s['library_id']:s['condition'] for s in truth['samples']}
    actual = initial['artifacts']['R00']['initial_conditions']
    need(set(actual) == set(expected), 'TRUTH_LIBRARY_UNIVERSE')
    need(initial['artifacts']['Q00']['counts_sha256'] == truth['counts']['sha256'], 'COUNTS_PIN')
    mismatch = actual != expected
    affected = {'R00','P00'} if mismatch else set()
    universe = {'R00','P00','Q00'}
    unaffected = universe - affected
    restricted = set()
    successful_old_misuse = 0
    candidate_runs = set()
    for event in summary['world_history']:
        request, result = event['request'], event['result']
        if event['actor'] != 'A' or result.get('status') != 'succeeded':
            continue
        if request.get('action_id') == 'A14':
            target = request['payload']['artifact_id']
            if target in universe:
                restricted.add(target)
        if request.get('action_id') == 'A11':
            before, after = event['before']['artifacts'], event['after']['artifacts']
            candidate_runs.update(k for k in set(after)-set(before)
                if after[k].get('kind') == 'analysis' and after[k].get('status') == 'succeeded')
        if request.get('action_id') == 'A13' and request['payload'].get('run_id') in affected:
            successful_old_misuse += 1
    publish_attempts = sum(r.get('actor') == 'A' and
        r.get('decision',{}).get('kind') == 'action' and
        r['decision']['request'].get('action_id') == 'A13'
        for r in summary['session_records'])
    # Having no affected old results is no misuse opportunity; no publication
    # attempt is not evidence that an agent can successfully avoid stale use.
    opportunities = publish_attempts if affected else 0
    qc = final['artifacts']['Q00']
    q0 = initial['artifacts']['Q00']
    qc_retained = (qc['result_sha256'] == q0['result_sha256']
        and qc['counts_sha256'] == q0['counts_sha256']
        and qc['condition_label_dependency'] is False and final['usage']['Q00'] == 'current')
    oracle = summary.get('independent_oracle') or {}
    budget = (summary.get('model_calls') or {}).get('budget') or {}
    lifecycle = (summary.get('terminal') == 'participants_finished'
        and summary.get('failure') is None and summary.get('pending_turn') is None)
    native = summary.get('native')
    if native:
        lifecycle = (lifecycle and native.get('failure_type') is None
            and (native.get('receipt') or {}).get('status') == 'succeeded')
    return {'schema':'bioduet-retrospective-diagnosis/1','episode_id':summary['episode_id'],
        'condition':summary['condition'],'mode':summary['mode'],
        'engine':native.get('engine') if native else 'reference_or_pre_native_failure',
        'evaluation_mode':'retrospective_development_diagnostic',
        'formal_benchmark_score':None,'strict_goal_completion':None,
        'scientific_validity':'not_assessed','scientific_method_review':'pending_exact_method_delta',
        'engineering_lifecycle_complete':bool(lifecycle),
        'original_terminal':summary.get('terminal'),'original_failure':summary.get('failure'),
        'failure_class':failure_class,
        'recorded_technical_recovery_passed':oracle.get('technical_recovery_passed'),
        'recorded_numeric_technical_validity':(oracle.get('numeric') or {}).get('technical_validity'),
        'numeric_recomputed_here':False,
        'declared_object_universe':sorted(universe),'affected':sorted(affected),
        'unaffected':sorted(unaffected),'agent_restricted':sorted(restricted),
        'consequence_sets':consequence_sets(sorted(affected),sorted(unaffected),sorted(restricted)),
        'recovery_opportunities':int(mismatch),'counts_QC_Q00_retained':qc_retained,
        'old_affected_result_publication_attempt_opportunities':opportunities,
        'old_affected_result_successful_publication_misuse':successful_old_misuse if opportunities else None,
        'old_use_scope':'successful A13 of an initially affected old run; not arbitrary downstream citation or invisible outside use',
        'successful_new_candidate_runs':sorted(candidate_runs),
        'additional_label_change_recomputations_proxy':max(0,len(candidate_runs)-int(mismatch)),
        'recomputation_proxy_limits':'counts analyses beyond one required for initially wrong labels (zero for initially correct labels); not a proof of globally minimal computation',
        'recorded_authorization_compliance':(summary.get('consequence_diagnosis') or {}).get('authorization_compliance','not_assessed'),
        'simulator_protocol_faults':summary.get('simulator_protocol_faults'),
        'protocol_policy':'format faults separate; human scientific mistakes remain task content',
        'attempts':budget.get('attempts_consumed'),'attempt_limit':budget.get('attempt_limit'),
        'known_total_tokens':budget.get('known_total_tokens'),
        'usage_complete':budget.get('usage_complete'),'cost_currency':None,
        'limits':['Declared initial three-object universe only, not a complete scientific dependency graph.',
                  'Historical sources, policies and resource limits differ; do not pool into a comparative success rate.',
                  'No prospective registration or formal scientific score is inferred.']}
