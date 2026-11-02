import json,unittest
from copy import deepcopy
from bioduet_eval.bw01_logical_v01 import LogicalSession,Bw01EngineeringWorld
from bioduet_eval.bw01_participant_v01 import ReferenceParticipant,LocalRole,decode,ProtocolError
from bioduet_eval.bw01_episode_v01 import run_episode
def response(decision):
    return {'model':'deepseek-flash','id':'fake-regression','usage':{'total_tokens':0},
            'choices':[{'message':{'content':json.dumps(decision)}}]}
from bioduet_eval.bw01_fixtures_v01 import scripted_response as fake
class Tests(unittest.TestCase):
    def test_separate_history_and_projection(self):
        world=Bw01EngineeringWorld()
        world.execute('A',{'action_id':'A06','operation_id':'first','payload':{'sample_version':1,'declared_condition':'control'}})
        session=LogicalSession(world)
        a,h=ReferenceParticipant('A'),ReferenceParticipant('H')
        pa=session.next_turn();qa=a.prepare(pa)
        session.submit(pa['turn_token'],{'kind':'wait','until':1})
        ph=session.next_turn();qh=h.prepare(ph)
        av=json.loads(qa['request']['messages'][-1]['content'])['turn']
        hv=json.loads(qh['request']['messages'][-1]['content'])['turn']
        self.assertNotIn('private_evidence',av['observation'])
        self.assertEqual(hv['observation']['private_evidence']['id'],'E01')
        h.accept(response({'kind':'finish'}))
        self.assertEqual(len(a.messages),2);self.assertEqual(len(h.messages),3)
        self.assertNotIn('episode_id',av);self.assertNotIn('turn_token',av)
    def test_wrong_actor_private_field_and_previous_result(self):
        packet=LogicalSession(Bw01EngineeringWorld()).next_turn()
        for change,previous in [('actor',None),('private',None),('none',{'actor':'H','result':'secret'})]:
            p=deepcopy(packet)
            if change=='actor':p['actor']='H'
            if change=='private':p['observation']['private_evidence']={}
            with self.assertRaises(ProtocolError):ReferenceParticipant('A').prepare(p,previous)
    def test_invalid_model_json_never_repairs_action(self):
        for content in ['{"kind":"finish","kind":"action"}','[1]','not json','{"x":NaN}']:
            state=ReferenceParticipant('A');state.prepare(LogicalSession(Bw01EngineeringWorld()).next_turn())
            raw=response({});raw['choices'][0]['message']['content']=content
            out=state.accept(raw)
            self.assertEqual(out['decision'],{'kind':'invalid_model_output'})
            self.assertEqual(out['parse_error'],'INVALID_MODEL_JSON')
    def test_model_identity_and_pending(self):
        state=ReferenceParticipant('A');packet=LogicalSession(Bw01EngineeringWorld()).next_turn()
        with self.assertRaises(ProtocolError):state.accept(response({}))
        state.prepare(packet)
        with self.assertRaises(ProtocolError):state.prepare(packet)
        raw=response({'kind':'finish'});raw['model']='different'
        with self.assertRaises(ProtocolError):state.accept(raw)
        self.assertEqual(state.accept(response({'kind':'finish'}))['turn_token'],packet['turn_token'])
    def test_paired_regression_and_no_science_claim(self):
        for condition,version in [('H0',1),('H1',2)]:
            report=run_episode(condition,{r:LocalRole(r) for r in 'AH'},fake)
            self.assertTrue(report['engineering_metadata_design_goal'])
            self.assertEqual(report['final_state']['sample']['version'],version)
            self.assertFalse(report['full_bw01_closed_loop'])
            self.assertIsNone(report['formal_benchmark_score'])
            self.assertEqual(report['scientific_validity'],'not_assessed')
            self.assertNotIn('actual_model_calls',report)
    def test_unrepaired_and_budget_do_not_pass(self):
        def wrong(request):
            turn=json.loads(request['messages'][-1]['content'])['turn']
            if turn['actor']=='H' and turn['observation']['public_evidence']:
                return {'status':'succeeded','response':response({'kind':'finish'})}
            return fake(request)
        for invoke,limit in [(wrong,14),(fake,2)]:
            report=run_episode('H1',{r:LocalRole(r) for r in 'AH'},invoke,max_turns=limit)
            self.assertFalse(report['engineering_metadata_design_goal'])
    def test_provider_and_environment_failure_no_retry_or_text(self):
        calls=[]
        def failed(_):calls.append(1);return {'status':'failed','code':'TIMEOUT','message':'private-secret'}
        report=run_episode('H1',{r:LocalRole(r) for r in 'AH'},failed)
        self.assertEqual(len(calls),1);self.assertEqual(report['terminal'],'provider_failure')
        self.assertNotIn('private-secret',json.dumps(report))
        def error(_):raise RuntimeError('private-secret')
        report=run_episode('H1',{r:LocalRole(r) for r in 'AH'},error)
        self.assertEqual(report['terminal'],'environment_error')
        self.assertNotIn('private-secret',json.dumps(report))
    def test_frame_and_history_limits(self):
        with self.assertRaises(ProtocolError):decode('x'*131073)
        state=ReferenceParticipant('A')
        state.messages*=64
        with self.assertRaises(ProtocolError):state.prepare(LogicalSession(Bw01EngineeringWorld()).next_turn())
if __name__=='__main__':unittest.main(verbosity=2)
