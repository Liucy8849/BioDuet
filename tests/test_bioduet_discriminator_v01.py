"""Incremental discriminator regressions; no prior suite, engine or model."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from bioduet_eval.bw01_world_port_v01 import BrokeredScienceWorld, ScienceWorldPort
from bioduet_eval.bw01_logical_v01 import LogicalSession
from bioduet_eval.bioduet_mcp_v01 import McpWorldFacade
from bioduet_eval.contract import Rejection


class FakeWorld:
    profile='synthetic-discriminator-test/1'
    tick=0
    expires_at=80
    def __init__(self):self.calls=[]
    def advance(self,tick):self.tick=tick
    def observe(self,actor):return {'status':'synthetic','actor':actor}
    def available_actions(self,actor):return ['A01','A06'] if actor=='A' else ['A01']
    def execute(self,actor,request):
        self.calls.append({'actor':actor,'request':request})
        return {'status':'succeeded'}


class FakeBridge:
    def __init__(self):self.calls=[]
    def exchange(self,decision):
        self.calls.append(decision)
        return {'receipt':{'result':{'status':'waiting'}},
                'next_turn':None,'environment_failure':None}


class DiscriminatorTests(unittest.TestCase):
    def setUp(self):self.evidence=[]

    def tearDown(self):
        root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',
            dir=os.environ['BW01_INTEGRATION_SCRATCH']))
        (root/'cases.json').write_text(json.dumps(self.evidence,indent=2)+'\n')

    def test_invalid_json_action_discriminators_reject_without_executor(self):
        for value in [[],{},None,True,False,0,1,'','A99']:
            with self.subTest(value=value):
                raw=FakeWorld();world=BrokeredScienceWorld(raw)
                result=world.execute('A',{'action_id':value})
                self.assertEqual(result,{'status':'rejected','reason':'ACTION_SCHEMA'})
                self.assertEqual(raw.calls,[])
                self.evidence.append({'action_id':value,'result':result,'executor_calls':0})

    def test_normal_action_and_known_unavailable_action_keep_scope(self):
        raw=FakeWorld();world=BrokeredScienceWorld(raw)
        result=world.execute('A',{'action_id':'A01'})
        self.assertEqual(result,{'status':'succeeded'})
        self.assertEqual(raw.calls,[{'actor':'A','request':{'action_id':'A01'}}])
        denied=world.execute('H',{'action_id':'A06','operation_id':'x','payload':{}})
        self.assertEqual(denied['reason'],'CAPABILITY_UNAVAILABLE')
        self.assertEqual(len(raw.calls),1)
        self.evidence.append({'valid':result,'denied':denied,'calls':raw.calls})

    def test_logical_session_continues_after_list_or_object_action(self):
        for value in [[],{}]:
            raw=FakeWorld();world=BrokeredScienceWorld(raw);session=LogicalSession(world,max_turns=10)
            first=session.next_turn();self.assertEqual(first['actor'],'A')
            failed=session.submit(first['turn_token'],{'kind':'action','request':{'action_id':value}})
            self.assertEqual(failed['result']['reason'],'ACTION_SCHEMA')
            self.assertIsNone(session.terminal);self.assertEqual(raw.calls,[])
            human=session.next_turn();self.assertEqual(human['actor'],'H')
            session.submit(human['turn_token'],{'kind':'finish'})
            following=session.next_turn();self.assertEqual(following['actor'],'A')
            good=session.submit(following['turn_token'],{'kind':'action','request':{'action_id':'A01'}})
            self.assertEqual(good['result']['status'],'succeeded')
            end=session.next_turn();session.submit(end['turn_token'],{'kind':'finish'})
            self.assertIsNone(session.next_turn())
            self.assertEqual(session.terminal,'participants_finished')
            self.assertEqual(len(raw.calls),1)
            self.evidence.append({'bad_action':value,'records':session.records,
                                  'terminal':session.terminal,'executor_calls':raw.calls})

    def test_controller_actor_and_capability_discriminators_are_typed(self):
        for value in [[],{},None,True,1,'unknown']:
            raw=FakeWorld();world=BrokeredScienceWorld(raw)
            result=world.execute(value,{'action_id':'A01'})
            self.assertEqual(result,{'status':'rejected','reason':'ACTOR'})
            with self.assertRaises(Rejection):world.remove_capability('A',value)
            port=ScienceWorldPort(raw)
            with self.assertRaises(Rejection):port.issue_context(value)
            self.assertEqual(raw.calls,[])
            self.evidence.append({'bad_discriminator':value,'actor_result':result,'executor_calls':0})

    def rpc(self,name,arguments=None):
        return {'jsonrpc':'2.0','id':1,'method':'tools/call',
                'params':{'name':name,'arguments':{} if arguments is None else arguments}}

    def test_mcp_invalid_names_return_rpc_error_and_recover(self):
        for value in [[],{},None,True,False,0,1,'','unknown_tool']:
            bridge=FakeBridge();facade=McpWorldFacade(bridge)
            result=facade.dispatch(self.rpc(value))
            self.assertEqual(result['error']['code'],-32602)
            self.assertEqual(bridge.calls,[])
            listed=facade.dispatch({'jsonrpc':'2.0','id':2,'method':'tools/list'})
            self.assertEqual(len(listed['result']['tools']),4)
            self.assertEqual(bridge.calls,[])
            good=facade.dispatch(self.rpc('research_wait',{'until':1}))
            self.assertFalse(good['result']['isError'])
            self.assertEqual(bridge.calls,[{'kind':'wait','until':1}])
            self.evidence.append({'bad_name':value,'error':result,
                                  'recovered':good,'bridge_calls':bridge.calls})

    def test_mcp_method_discriminator_does_not_reach_bridge(self):
        for value in [[],{},None,True,0,'unknown_method']:
            bridge=FakeBridge();facade=McpWorldFacade(bridge)
            result=facade.dispatch({'jsonrpc':'2.0','id':1,'method':value})
            expected=-32601 if value=='unknown_method' else -32600
            self.assertEqual(result['error']['code'],expected)
            self.assertEqual(bridge.calls,[])
            self.evidence.append({'method':value,'result':result,'bridge_calls':0})

    def test_all_known_mcp_names_preserve_chosen_payload(self):
        cases=[('research_action',{'request':{'action_id':'A01'}},
                {'kind':'action','request':{'action_id':'A01'}}),
               ('research_message',{'to':'H','text':'scientist chooses'},
                {'kind':'message','to':'H','text':'scientist chooses'}),
               ('research_wait',{'until':5},{'kind':'wait','until':5}),
               ('research_finish',{}, {'kind':'finish'})]
        for name,args,chosen in cases:
            bridge=FakeBridge();facade=McpWorldFacade(bridge)
            result=facade.dispatch(self.rpc(name,args))
            self.assertFalse(result['result']['isError'])
            self.assertEqual(bridge.calls,[chosen])
            self.evidence.append({'name':name,'arguments':args,'decision':bridge.calls[0]})

    def test_discriminator_fix_does_not_accept_action_metadata_rebinding(self):
        raw=FakeWorld();world=BrokeredScienceWorld(raw)
        port=world._port;context=world._contexts['A']
        for value in [[],{},'A06']:
            envelope=port.envelope(context,{'action_id':'A01'})
            envelope['action']['id']=value
            with self.assertRaises(Rejection):port.execute(context,envelope)
            self.assertEqual(raw.calls,[])
            self.evidence.append({'rebound_action':value,'executor_calls':0})


if __name__=='__main__':unittest.main()
