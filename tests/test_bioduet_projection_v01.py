"""New historical projection and pair-boundary regressions."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from labweave_eval.bw01_science_world_v02 import Bw01ScienceWorld
from labweave_eval.bioduet_bw01_projection_v01 import project
from labweave_eval.bw01_evaluation_v01 import pair


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',
            dir=os.environ['BW01_INTEGRATION_SCRATCH']))
        public=self.root/'public';public.mkdir();(self.root/'runs').mkdir()
        (public/'dataset.json').write_text(json.dumps({'counts':{'sha256':'1'*64},
            'source_kind':'synthetic_fixture','cell_type':'synthetic','donor_count':2,
            'samples':[{'sample_id':'S01','library_id':'L1','donor_id':'D1','condition':None},
                       {'sample_id':'S02','library_id':'L2','donor_id':'D1','condition':'control'}]}))
        def execute(public,rows,out,**versions):
            out.mkdir();data=b'fake numerical bytes\n';(out/'de.tsv').write_bytes(data)
            return {'status':'succeeded','result':{'name':'de.tsv','bytes':len(data),
                'sha256':hashlib.sha256(data).hexdigest()}}
        self.world=Bw01ScienceWorld('H0',public,self.root/'runs',execute)
        self.records=[]

    def act(self,actor,action,payload):
        tick=len(self.records);self.world.advance(tick)
        req={'action_id':action,'operation_id':f'op-{tick}','payload':payload}
        result=self.world.execute(actor,req)
        self.records.append({'tick':tick,'actor':actor,'decision':{'kind':'action','request':req},
                             'result':result})
        self.assertEqual(result['status'],'succeeded')
        return result

    def design(self):
        return self.act('A','A06',{'sample_version':self.world.sample['version'],
            'declared_condition':self.world.sample['condition'],'analysis_unit':'donor','paired':True})

    def analyze(self):
        result=self.act('A','A11',{'sample_version':self.world.sample['version'],
                                 'design_version':self.world.design['version']})
        return result['run_id']

    def change(self,condition):
        self.act('H','A03',{'expected_version':self.world.sample['version'],
                           'condition':condition,'reason':'synthetic diagnostic change'})

    def episode(self):
        return copy.deepcopy({'session_records':self.records,'world_history':self.world.history,
                              'final_state':self.world.observe('A')})

    def tearDown(self):
        (self.root/'synthetic-episode.json').write_text(json.dumps(self.episode(),indent=2)+'\n')

    def test_empty_history_has_no_recovery_denominator(self):
        result=project(self.episode())['numerical_recovery']
        self.assertIsNone(result['denominator'])
        self.assertIsNone(result['numerator'])

    def test_label_change_affects_existing_analysis_without_invented_repair(self):
        self.design();self.analyze();self.change('control')
        report=project(self.episode())
        self.assertEqual(report['numerical_recovery']['opportunities'],['run:R01'])
        self.assertEqual(report['numerical_recovery']['denominator'],1)
        self.assertEqual(report['numerical_recovery']['numerator'],0)
        self.assertEqual(report['replacements'],[])
        self.assertFalse(report['actual_scientific_receipts_verified'])

    def test_revision_only_refresh_is_not_semantic_numerical_failure(self):
        self.design();self.analyze();self.change('stim')
        result=project(self.episode())
        self.assertFalse(result['impacts'][0]['semantic_change'])
        self.assertIsNone(result['numerical_recovery']['denominator'])

    def test_design_repair_before_analysis_is_not_old_analysis_recovery(self):
        self.world.sample['condition']='control'
        self.design();self.change('stim');self.design();self.analyze()
        result=project(self.episode())
        self.assertIn('design:1',result['impacts'][0]['affected_existing'])
        self.assertIsNone(result['numerical_recovery']['denominator'])

    def test_successful_publication_uses_actual_run_lineage(self):
        self.design();run=self.analyze();self.act('A','A12',{'run_id':run})
        self.act('A','A13',{'run_id':run,'expected_sample_version':1,
            'expected_design_version':1,'interpretation':'synthetic'})
        report=project(self.episode())
        self.assertFalse(report['uses'][0]['stale_use'])
        self.assertEqual(report['uses'][0]['artifact_id'],'run:R01')

    def test_projection_rejects_run_version_rebinding(self):
        self.design();self.analyze()
        e=self.episode();e['session_records'][1]['result']['sample_version']=999
        with self.assertRaises(ValueError):project(e)

    def test_projection_rejects_history_result_tampering(self):
        self.design();self.analyze()
        e=self.episode();e['world_history'][1]['result']['result']['sha256']='2'*64
        with self.assertRaises(ValueError):project(e)

    def test_projection_rejects_final_run_hash_tampering(self):
        self.design();self.analyze()
        e=self.episode();e['final_state']['analysis_runs'][0]['result']['sha256']='2'*64
        with self.assertRaises(ValueError):project(e)

    def test_recorded_pair_policy_mismatch_never_gets_comparable(self):
        a={'condition':'H0','pair_id':'p','instance_id':'0','summary_sha256':'0'*64,
           'comparison_contract_sha256':'a'*64}
        b=dict(a,condition='H1',instance_id='1',summary_sha256='1'*64)
        with patch('labweave_eval.bw01_evaluation_v01.evaluate',
                   side_effect=[{'observed_comparison_fields':{'max_calls':30}},
                                {'observed_comparison_fields':{'max_calls':31}}]):
            result=pair(a,{},b,{})
        self.assertFalse(result['pair_comparable'])
        self.assertFalse(result['formal_pair_eligible'])
        self.assertIsNone(result['formal_benchmark_score'])

    def test_identical_summary_cannot_be_counted_as_two_conditions(self):
        a={'condition':'H0','pair_id':'p','instance_id':'0','summary_sha256':'0'*64,
           'comparison_contract_sha256':'a'*64}
        b=dict(a,condition='H1',instance_id='1')
        with patch('labweave_eval.bw01_evaluation_v01.evaluate',
                   return_value={'observed_comparison_fields':{'max_calls':30}}):
            result=pair(a,{},b,{})
        self.assertFalse(result['pair_comparable'])

    def test_rejected_stale_publish_is_an_attempt_not_success(self):
        self.design();run=self.analyze();self.act('A','A12',{'run_id':run})
        self.change('control');self.design()
        tick=len(self.records);self.world.advance(tick)
        request={'action_id':'A13','operation_id':'rejected-pub','payload':{
            'run_id':run,'expected_sample_version':2,'expected_design_version':2,
            'interpretation':'synthetic stale attempt'}}
        result=self.world.execute('A',request)
        self.assertEqual(result,{'status':'rejected','reason':'VERSION_CONFLICT'})
        self.records.append({'tick':tick,'actor':'A','decision':{'kind':'action','request':request},
                             'result':result})
        report=project(self.episode())
        self.assertTrue(report['uses'][0]['rejected_stale_attempt'])
        self.assertFalse(report['uses'][0]['stale_use'])
        self.assertIsNone(self.world.publication)

    def test_rejected_restriction_does_not_invalidate_unaffected_run(self):
        self.design();run=self.analyze()
        tick=len(self.records);self.world.advance(tick)
        request={'action_id':'A14','operation_id':'rejected-restrict',
                 'payload':{'run_id':run,'reason':''}}
        result=self.world.execute('A',request)
        self.assertEqual(result['status'],'rejected')
        self.records.append({'tick':tick,'actor':'A','decision':{'kind':'action','request':request},
                             'result':result})
        report=project(self.episode())
        self.assertEqual(report['restrictions'][0]['status'],'rejected')
        self.assertFalse(report['restrictions'][0]['false_invalidation'])


if __name__=='__main__':unittest.main()
