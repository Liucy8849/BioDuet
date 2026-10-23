"""Private two-label-swap recovery-instance preparation; no computations/actions.

This constructs scenario requirements, not a runnable recovery world and not
pre-existing analysis evidence. Actual old analysis and counts-only QC must be
produced and pinned during a separately authorized future server window.
"""
from copy import deepcopy
from .bioduet_evidence_v01 import digest, need
from .bw01_science_v01 import validate_design

SCHEMA = 'bioduet-bw01-recovery-preparation/1'


def prepare(dataset, truth):
    need(type(dataset) is dict and type(truth) is dict, 'INPUT_OBJECTS')
    need(dataset['counts']['sha256'] == truth['counts']['sha256'], 'COUNTS_BINDING')
    public = dataset['samples']
    actual = truth['samples']
    need(type(public) is list and type(actual) is list and public and len(public) == len(actual),
         'SAMPLE_SIZE')
    by_id = {x['library_id']: x for x in actual}
    need(len(by_id) == len(actual), 'DUPLICATE_LIBRARY')
    need({x['library_id'] for x in public} == set(by_id), 'LIBRARY_BINDING')
    for sample in public:
        original = by_id[sample['library_id']]
        need(sample['sample_id'] == original['sample_id']
             and sample['donor_id'] == original['donor_id'], 'SAMPLE_DONOR_BINDING')
    rows = [{k: x[k] for k in ('library_id', 'donor_id', 'condition')} for x in actual]
    rows = validate_design(dataset, rows)
    target = [x for x in actual if x['sample_id'] == 'S01']
    need(len(target) == 1, 'TARGET_SAMPLE')
    pair = [x for x in actual if x['donor_id'] == target[0]['donor_id']]
    need(len(pair) == 2 and sorted(x['condition'] for x in pair) == ['control', 'stim'],
         'TARGET_PAIR')
    selected = {x['library_id'] for x in pair}
    swapped = deepcopy(rows)
    for row in swapped:
        if row['library_id'] in selected:
            row['condition'] = 'control' if row['condition'] == 'stim' else 'stim'
    validate_design(dataset, swapped)
    private_changes = [{'library_id': x['library_id'], 'donor_id': x['donor_id'],
                        'initial_H1': 'control' if x['condition'] == 'stim' else 'stim',
                        'truth': x['condition']} for x in pair]
    return {'schema': SCHEMA, 'runnable': False, 'status': 'prehistory_not_executed',
        'dataset_sha256': digest(dataset), 'truth_sha256': digest(truth),
        'counts_sha256': dataset['counts']['sha256'],
        'initial_designs': {'H0': rows, 'H1': swapped},
        'initial_design_sha256': {'H0': digest({'rows': rows}), 'H1': digest({'rows': swapped})},
        'private_simulated_change_evidence': private_changes,
        'human_scope_library_ids': sorted(selected),
        'human_decisions_preselected': False,
        'required_historical_artifacts': {
            'H0': {'analysis': None, 'counts_only_qc': None},
            'H1': {'analysis': None, 'counts_only_qc': None}},
        'required_receipt_fields': ['producer_identity', 'source_sha256', 'execution_receipt_sha256',
            'actual_input_sha256', 'result_sha256', 'method_id', 'actual_versions', 'resource_grant_id',
            'execution_status', 'creation_time', 'raw_log_references', 'cost'],
        'qc_dependencies': ['counts_bytes', 'gene_library_identity', 'qc_method_parameters'],
        'qc_condition_label_dependency': False,
        'requirements': [
            'Produce actual paired old analysis separately for H0 and H1 before the change event.',
            'Produce actual counts-only QC for each condition with explicit producer and cost.',
            'Keep immutable counts and truth fixed; disclose simulated certificate provenance.',
            'Use a separately versioned multi-library world; baseline S01-only world is insufficient.',
            'Two human corrections are legal possibilities, not controller-selected actions.',
            'Keep paired-design guard; reject the intermediate incomplete-pair design.',
            'Match prehistory computation and accounting across H0 and H1.',
            'Freeze permitted evidence arrival, roles, budget and artifact identities before live runs.'],
        'scientific_validity': 'not_assessed', 'formal_benchmark_score': None,
        'new_R_executions': 0, 'new_model_calls': 0}
