import json
import unittest
from labweave_eval.bw01_logical_v01 import Bw01EngineeringWorld, LogicalSession, safe_copy


def action(action_id, op, payload):
    return {'kind': 'action', 'request': {'action_id': action_id, 'operation_id': op, 'payload': payload}}


def draft(version=1, condition='control', op='draft'):
    return action('A06', op, {'sample_version': version, 'declared_condition': condition})


def correct(version=1, condition='stim', op='revise'):
    return action('A03', op, {'expected_version': version, 'condition': condition, 'reason': 'checked evidence'})


def submit(session, decision, actor=None):
    packet = session.next_turn()
    if actor is not None:
        assert packet['actor'] == actor, (packet['actor'], actor)
    return session.submit(packet['turn_token'], decision)


class LogicalTests(unittest.TestCase):
    def test_human_gets_action_without_agent_request(self):
        s = LogicalSession(Bw01EngineeringWorld())
        submit(s, draft(), 'A')
        packet = s.next_turn()
        self.assertEqual(packet['actor'], 'H')
        self.assertEqual(packet['observation']['private_evidence']['condition'], 'stim')

    def test_wait_does_not_skip_other_actor(self):
        s = LogicalSession(Bw01EngineeringWorld())
        submit(s, {'kind': 'wait', 'until': 50}, 'A')
        self.assertEqual(s.next_turn()['actor'], 'H')
        self.assertEqual(s.tick, 1)

    def test_grant_expiry_uses_scheduler_clock(self):
        s = LogicalSession(Bw01EngineeringWorld(expires_at=5))
        submit(s, {'kind': 'wait', 'until': 10}, 'A')
        submit(s, {'kind': 'wait', 'until': 10}, 'H')
        p = s.next_turn()
        self.assertEqual(p['tick'], 10)
        self.assertEqual(p['available_actions'], [])
        r = s.submit(p['turn_token'], draft())
        self.assertEqual(r['result']['reason'], 'CAPABILITY_UNAVAILABLE')

    def test_no_hidden_evidence_in_agent_packet(self):
        s = LogicalSession(Bw01EngineeringWorld())
        p = s.next_turn()
        self.assertNotIn('private_evidence', json.dumps(p))
        self.assertNotIn('simulated-log-01', json.dumps(p))
        p['observation']['sample']['condition'] = 'stim'
        self.assertEqual(s.world.sample['condition'], 'control')

    def test_evidence_opens_only_after_successful_draft(self):
        w = Bw01EngineeringWorld()
        self.assertIsNone(w.observe('H')['private_evidence'])
        self.assertEqual(w.execute('A', draft(version=2)['request'])['reason'], 'VERSION_CONFLICT')
        self.assertIsNone(w.observe('H')['private_evidence'])
        self.assertEqual(w.execute('H', action('A02','e',{'evidence_ref':'E01'})['request'])['reason'], 'EVIDENCE_UNAVAILABLE')

    def test_identity_spoof_rejected(self):
        s = LogicalSession(Bw01EngineeringWorld())
        d = draft(); d['actor'] = 'H'
        r = submit(s, d)
        self.assertEqual(r['result']['reason'], 'DECISION_SCHEMA')
        self.assertIsNone(s.world.design)

    def test_agent_cannot_do_human_action(self):
        s = LogicalSession(Bw01EngineeringWorld())
        self.assertEqual(submit(s, correct())['result']['reason'], 'CAPABILITY_UNAVAILABLE')
        self.assertEqual(s.world.sample['version'], 1)

    def test_stale_token_and_pending_turn(self):
        s = LogicalSession(Bw01EngineeringWorld())
        p = s.next_turn()
        with self.assertRaises(RuntimeError): s.next_turn()
        with self.assertRaises(ValueError): s.submit('H:0', {'kind':'finish'})
        s.submit(p['turn_token'], {'kind':'finish'})
        with self.assertRaises(ValueError): s.submit(p['turn_token'], {'kind':'finish'})

    def test_message_is_not_mutation(self):
        s = LogicalSession(Bw01EngineeringWorld())
        submit(s, {'kind':'message','to':'H','text':'I already changed S01 to stim'})
        p = s.next_turn()
        self.assertEqual(p['messages'][0]['source_kind'], 'participant_statement')
        self.assertEqual(s.world.sample['condition'], 'control')

    def test_all_terminal_paths(self):
        s = LogicalSession(Bw01EngineeringWorld(), max_turns=1)
        submit(s, {'kind':'wait','until':1}); self.assertIsNone(s.next_turn())
        self.assertEqual(s.terminal, 'budget_exhausted')
        s = LogicalSession(Bw01EngineeringWorld(), deadline=2)
        submit(s, {'kind':'wait','until':8}); submit(s, {'kind':'wait','until':8})
        self.assertIsNone(s.next_turn()); self.assertEqual(s.terminal,'deadline')
        s = LogicalSession(Bw01EngineeringWorld())
        submit(s, {'kind':'finish'}); self.assertIsNotNone(s.next_turn())
        s.submit(s.pending['turn_token'], {'kind':'finish'})
        self.assertIsNone(s.next_turn()); self.assertEqual(s.terminal,'participants_finished')

    def test_invalid_decisions_consume_budget(self):
        for bad in [None, {'kind':'wait','until':True}, {'kind':'wait','until':0},
                    {'kind':'message','to':[], 'text':'x'}, {'kind':[]}, {'kind':'finish','model_calls':1}]:
            s = LogicalSession(Bw01EngineeringWorld(), max_turns=1)
            result = submit(s, bad)
            self.assertEqual(result['result']['status'], 'rejected')
            self.assertIsNone(s.next_turn())

    def test_idempotency_and_version_conflicts(self):
        w = Bw01EngineeringWorld()
        req = correct()['request']
        first = w.execute('H', req)
        self.assertEqual(w.execute('H', req), first)
        self.assertEqual(w.sample['version'],2)
        self.assertEqual(w.execute('H',correct(condition='control')['request'])['reason'],'IDEMPOTENCY_CONFLICT')
        self.assertEqual(w.execute('H',correct(op='other')['request'])['reason'],'VERSION_CONFLICT')
        self.assertEqual(len(w.history),1)

    def test_no_oracle_auto_correction_or_invalidation(self):
        w = Bw01EngineeringWorld()
        w.execute('A',draft()['request'])
        w.execute('H',correct(condition='control')['request'])
        self.assertEqual(w.sample['condition'],'control')
        self.assertEqual(w.design['sample_version'],1)
        self.assertEqual(w.design['status'],'draft')

    def test_h0_h1_microloop_and_no_false_interactive_claim(self):
        counts = []
        for condition in ['H0','H1']:
            s = LogicalSession(Bw01EngineeringWorld(condition))
            label = s.world.sample['condition']
            submit(s,draft(condition=label),'A')
            submit(s,action('A02','evidence',{'evidence_ref':'E01'}),'H')
            submit(s,{'kind':'wait','until':5},'A')
            if condition == 'H1': submit(s,correct(),'H')
            else: submit(s,{'kind':'finish'},'H')
            if condition == 'H1': submit(s,{'kind':'finish'},'H')
            p = s.next_turn()
            self.assertEqual(p['actor'],'A')
            self.assertEqual(p['observation']['sample']['condition'],'stim')
            self.assertEqual(p['observation']['sample']['version'],2 if condition=='H1' else 1)
            s.submit(p['turn_token'],{'kind':'finish'});s.next_turn()
            report = s.report()
            self.assertEqual(report['behavior_source'],'simulated_replay')
            self.assertFalse(report['interactive_closed_loop'])
            self.assertEqual(report['actual_model_calls'],0)
            self.assertIsNone(report['formal_benchmark_score'])
            self.assertEqual(report['scientific_validity'],'not_assessed')
            print(json.dumps({'type':'engineering_trace','condition':condition,'trace':report,'world_history':s.world.history}))
            counts.append(s.world.counts)
        self.assertEqual(counts[0],counts[1])

    def test_strict_json_limits(self):
        for bad in [1.2, float('nan'), -1, 2**40, {1:'x'}, 'x'*65537]:
            with self.assertRaises(ValueError): safe_copy(bad)

    def test_deterministic_replay(self):
        def run():
            s=LogicalSession(Bw01EngineeringWorld())
            submit(s,draft());submit(s,correct());submit(s,{'kind':'finish'});submit(s,{'kind':'finish'});s.next_turn()
            report=s.report(); report.pop('episode_id'); return report
        self.assertEqual(run(),run())

    def test_scientific_actions_are_not_advertised(self):
        w=Bw01EngineeringWorld()
        self.assertNotIn('A11',w.available_actions('A'))
        self.assertEqual(w.execute('A',{'action_id':'A11'})['reason'],'CAPABILITY_UNAVAILABLE')


    def test_turn_token_bound_to_session(self):
        first=LogicalSession(Bw01EngineeringWorld()); second=LogicalSession(Bw01EngineeringWorld())
        p1=first.next_turn();p2=second.next_turn()
        self.assertNotEqual(p1['turn_token'],p2['turn_token'])
        with self.assertRaises(ValueError):second.submit(p1['turn_token'],{'kind':'finish'})
        second.submit(p2['turn_token'],{'kind':'finish'})

    def test_message_backpressure_and_later_delivery(self):
        s=LogicalSession(Bw01EngineeringWorld(expires_at=200),deadline=200)
        submit(s,{'kind':'wait','until':100},'A')
        for _ in range(4):
            self.assertEqual(submit(s,{'kind':'message','to':'A','text':'x'*4096},'H')['result']['status'],'message_queued')
        self.assertEqual(submit(s,{'kind':'message','to':'A','text':'x'},'H')['result']['reason'],'MESSAGE_QUEUE_FULL')
        submit(s,{'kind':'finish'},'H')
        p=s.next_turn();self.assertEqual(p['actor'],'A');self.assertEqual(len(p['messages']),4)
        s.submit(p['turn_token'],{'kind':'finish'});s.next_turn()
        self.assertEqual(s.report()['terminal'],'participants_finished')

    def test_report_can_hold_bounded_rejected_deep_payload(self):
        nested={}
        for _ in range(17):nested={'nested':nested}
        s=LogicalSession(Bw01EngineeringWorld())
        submit(s,{'kind':'action','request':{'action_id':'invalid','payload':nested}})
        self.assertEqual(s.report()['records'][0]['result']['status'],'rejected')

    def test_environment_failure_is_not_agent_failure_or_secret(self):
        class BrokenWorld(Bw01EngineeringWorld):
            def execute(self,actor,request):raise RuntimeError('private detail must not escape')
        s=LogicalSession(BrokenWorld())
        submit(s,draft())
        self.assertIsNone(s.next_turn());self.assertEqual(s.terminal,'environment_error')
        self.assertNotIn('private detail',json.dumps(s.report()))

if __name__ == '__main__':
    unittest.main(verbosity=2)
