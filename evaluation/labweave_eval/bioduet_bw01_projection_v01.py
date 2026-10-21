"""Post-hoc consequences from a pinned BW-01 world trace.

No execution/numerical receipt is inferred from a successful tool return.
This historical projection has no QC or prehistory artifacts unless they were
actually present; it never invents replacement events or scientific repairs.
"""
from .bioduet_consequence_v01 import diagnose
from .bioduet_evidence_v01 import digest, same, need

REQUIRED = {'design': ['sample.condition', 'method_id'],
            'analysis': ['sample.condition', 'method_id', 'counts_sha256'],
            'publication': ['sample.condition', 'method_id', 'counts_sha256'],
            'counts_qc': ['counts_sha256', 'qc_method']}


def project(episode):
    need(type(episode) is dict, 'EPISODE')
    records = {x['tick']: x for x in episode['session_records']}
    artifacts, changes, events, limitations = [], [], [], []
    designs, runs = {}, {}
    publications = []
    for h in episode['world_history']:
        tick, action = h['tick'], h['action_id']
        seq = tick + 1
        row = records[tick]
        request, result = row['decision']['request'], row['result']
        need(h['actor'] == row['actor'] and action == request['action_id'], 'HISTORY_BINDING')
        if 'result' in h:
            need(same(h['result'], result), 'HISTORY_RESULT')
        before, after = h['before'], h['after']
        if action == 'A03':
            old, new = before['sample'], after['sample']
            need(old['version'] + 1 == new['version'], 'SAMPLE_VERSION_CHAIN')
            changes.append({'seq': seq, 'field': 'sample.condition',
                            'before': old['condition'], 'after': new['condition']})
        elif action == 'A06':
            design = after['design']
            need(design['sample_version'] == before['sample']['version'], 'DESIGN_SAMPLE_INPUT')
            key = 'design:' + str(design['version'])
            need(key not in designs, 'DESIGN_REUSED')
            designs[key] = design
            artifacts.append({'id': key, 'kind': 'design', 'created_seq': seq,
                'depends_on': [], 'fields': {'sample.condition': design['declared_condition'],
                    'method_id': design['method_id']}, 'sha256': digest(design)})
            if design['declared_condition'] != before['sample']['condition']:
                limitations.append('design_declaration_disagrees_with_observed_sample')
        elif action == 'A11':
            key = 'run:' + result['run_id']
            need(key not in runs, 'RUN_REUSED')
            design_key = 'design:' + str(result['design_version'])
            need(design_key in designs, 'RUN_DESIGN_MISSING')
            design = designs[design_key]
            need(result['sample_version'] == design['sample_version'], 'RUN_INPUT_BINDING')
            runs[key] = result
            result_hash = (result.get('result') or {}).get('sha256')
            if result.get('status') != 'succeeded' or not result_hash:
                limitations.append('failed_analysis_has_no_numerical_artifact')
                continue
            artifacts.append({'id': key, 'kind': 'analysis', 'created_seq': seq,
                'depends_on': [design_key],
                'fields': {'counts_sha256': episode['final_state']['counts']['identity']},
                'sha256': result_hash})
        elif action == 'A13':
            pub = result['publication']
            run_key = 'run:' + pub['run_id']
            need(run_key in runs, 'PUBLICATION_RUN_MISSING')
            run = runs[run_key]
            if (pub['sample_version'], pub['design_version']) != (run['sample_version'], run['design_version']):
                limitations.append('publication_version_relabelled')
            key = 'publication:' + str(seq)
            artifacts.append({'id': key, 'kind': 'publication', 'created_seq': seq,
                'depends_on': [run_key], 'fields': {}, 'sha256': digest(pub)})
            publications.append((key, run_key))
            events.append({'seq': seq, 'kind': 'use', 'artifact_id': run_key,
                'replacement_id': None, 'status': 'succeeded', 'origin': 'participant'})
        elif action == 'A14':
            run_key = 'run:' + request['payload']['run_id']
            if any(a['id'] == run_key for a in artifacts):
                events.append({'seq': seq, 'kind': 'restrict', 'artifact_id': run_key,
                    'replacement_id': None, 'status': 'succeeded', 'origin': 'participant'})
                for pub_key, dependency in publications[-1:]:
                    if dependency == run_key:
                        events.append({'seq': seq, 'kind': 'restrict', 'artifact_id': pub_key,
                            'replacement_id': None, 'status': 'succeeded', 'origin': 'world'})
    # Rejected attempts have no world mutation/history, but remain observable
    # participant decisions. Do not count them as successful stale use.
    artifact_ids = {a['id'] for a in artifacts}
    for row in episode['session_records']:
        decision, result = row.get('decision', {}), row.get('result', {})
        request = decision.get('request', {})
        if (decision.get('kind') == 'action' and result.get('status') == 'rejected'
                and request.get('action_id') in ('A13', 'A14')):
            run_key = 'run:' + str(request.get('payload', {}).get('run_id', ''))
            if run_key in artifact_ids:
                events.append({'seq': row['tick'] + 1,
                    'kind': 'use' if request['action_id'] == 'A13' else 'restrict',
                    'artifact_id': run_key, 'replacement_id': None,
                    'status': 'rejected', 'origin': 'participant'})
    final_runs = {r['run_id']: r for r in episode['final_state']['analysis_runs']}
    need(set(final_runs) == {r['run_id'] for r in runs.values()}, 'FINAL_RUN_SET')
    for run in runs.values():
        final = final_runs[run['run_id']]
        for field in ('run_id', 'sample_version', 'design_version', 'status', 'result'):
            need(same({'v': run.get(field)}, {'v': final.get(field)}), 'FINAL_RUN_BINDING')
    report = diagnose(artifacts, changes, events, {}, required_fields=REQUIRED)
    report['schema'] = 'bioduet-bw01-historical-consequence/1'
    report['projection'] = {'artifacts': artifacts, 'changes': changes, 'events': events}
    report['evidence_limits'] = sorted(set(limitations + [
        'trace_reported_execution_and_result_hashes_only',
        'numerical_execution_files_not_opened_by_this_projection',
        'no_explicit_replacement_events_in_this_profile',
        'no_counts_only_qc_artifact_in_this_profile']))
    report['actual_scientific_receipts_verified'] = False
    report['scientific_validity'] = 'not_assessed'
    return report
