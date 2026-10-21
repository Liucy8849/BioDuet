"""Evaluator-only BW-01 profile. Pinned historical records; no world execution."""
from .bioduet_evidence_v01 import load_bundle, need, digest
from .bioduet_bw01_projection_v01 import project
from .bw01_oracle_v01 import judge_trace
from .bw01_protocol_diagnostic_v01 import assess

EXPECTATION = 'bioduet-bw01-expectation/1'
TRACE = 'bioduet-bw01-evidence-source/1'


def evaluate(expected, trace):
    need(type(expected) is dict and set(expected) ==
         {'schema', 'instance_id', 'pair_id', 'condition', 'summary_sha256',
          'comparison_contract_sha256'}, 'EXPECTATION_SCHEMA')
    need(expected['schema'] == EXPECTATION, 'EXPECTATION_PROFILE')
    need(expected['condition'] in ('H0', 'H1'), 'CONDITION')
    need(all(type(expected[k]) is str and 1 <= len(expected[k]) <= 256
             for k in ('instance_id', 'pair_id')), 'IDENTITY')
    for name in ('summary_sha256', 'comparison_contract_sha256'):
        value = expected[name]
        need(type(value) is str and len(value) == 64 and
             all(c in '0123456789abcdef' for c in value), 'PIN')
    need(type(trace) is dict and set(trace) == {'schema', 'instance_id', 'directory'}
         and trace['schema'] == TRACE and trace['instance_id'] == expected['instance_id'],
         'TRACE_SOURCE_SCHEMA')
    loaded = load_bundle(trace['directory'], expected['summary_sha256'], expected['condition'])
    bundle = loaded['private_bundle']
    summary, episode = bundle['summary'], bundle['episode']
    need(summary['mode'] == 'live' and summary['behavior_source'] == 'interactive_model'
         and summary['time_model'] == 'logical_time', 'HISTORICAL_LIVE_PROFILE')
    technical = judge_trace(episode, expected['condition'])
    protocol = assess(episode)
    consequence = project(episode)
    models = sorted({x['provider']['model'] for x in episode['transcript']})
    observed = {'counts_sha256': episode['final_state']['counts']['identity'],
        'method_id': episode['final_state']['analysis_contract']['method_id'],
        'source_inventory_sha256': digest({'sources': summary['sources']}),
        'provider_policy': bundle['provider_ledger']['policy'], 'models': models,
        'profile': episode['profile'], 'mode': summary['behavior_source']}
    return {'schema': 'bioduet-bw01-evaluation/1', 'instance_id': expected['instance_id'],
        'condition': expected['condition'], 'pair_id': expected['pair_id'],
        'engineering_goal_met': bool(technical['trace_goal_complete']
            and technical['authorization_compliance'] == 'passed'
            and protocol['simulator_protocol_status'] == 'passed'),
        'trace_check': loaded['check'], 'trace_judgment': technical,
        'simulator_protocol': protocol, 'consequence': consequence,
        'observed_comparison_fields': observed,
        'actual_model_calls_historical': summary['actual_model_calls'],
        'new_model_calls': 0, 'new_R_runs': 0,
        'recorded_numeric_oracle': {'technical_validity': bundle['oracle'].get('technical_validity'),
                                    'independently_recomputed_here': False},
        'scientific_validity': 'not_assessed', 'strict_goal_completion': None,
        'formal_benchmark_score': None, 'live_credit': False,
        'limits': ['Historical diagnosis, not repaired-source live qualification.',
                   'Pinned bytes and trace joins do not certify producer honesty.',
                   'Pair comparison covers recorded fields only; human-policy/seed matching is not revalidated.',
                   'No formal comparative score or independent numerical recomputation.']}


def pair(h0, t0, h1, t1):
    a, b = evaluate(h0, t0), evaluate(h1, t1)
    comparable = (h0['condition'] == 'H0' and h1['condition'] == 'H1'
        and h0['pair_id'] == h1['pair_id']
        and h0['instance_id'] != h1['instance_id']
        and h0['summary_sha256'] != h1['summary_sha256']
        and h0['comparison_contract_sha256'] == h1['comparison_contract_sha256']
        and a['observed_comparison_fields'] == b['observed_comparison_fields'])
    return {'schema': 'bioduet-bw01-pair-evaluation/1',
        'pair_comparable': comparable,
        'comparison_scope': 'recorded engineering profile/data/method/model/source/provider-policy fields',
        'formal_pair_eligible': False, 'H0': a, 'H1': b,
        'scientific_validity': 'not_assessed', 'formal_benchmark_score': None,
        'live_credit': False}
