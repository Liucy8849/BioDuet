"""New pure preparation guards; no analysis or world actions."""
import copy
import unittest
from labweave_eval.bioduet_recovery_preparation_v01 import prepare


class RecoveryPreparationTests(unittest.TestCase):
    def fixture(self):
        samples=[{'sample_id':'S01','library_id':'L1','donor_id':'D1','condition':'stim'},
                 {'sample_id':'S02','library_id':'L2','donor_id':'D1','condition':'control'},
                 {'sample_id':'S03','library_id':'L3','donor_id':'D2','condition':'stim'},
                 {'sample_id':'S04','library_id':'L4','donor_id':'D2','condition':'control'}]
        truth={'counts':{'sha256':'a'*64},'samples':samples}
        dataset=copy.deepcopy(truth);dataset['samples'][0]['condition']=None
        return dataset,truth

    def test_swaps_exactly_one_pair_preserving_both_valid_designs(self):
        data,truth=self.fixture();before=copy.deepcopy((data,truth))
        result=prepare(data,truth)
        original=result['initial_designs']['H0'];swapped=result['initial_designs']['H1']
        self.assertEqual([a['library_id'] for a,b in zip(original,swapped)
                          if a['condition']!=b['condition']],['L1','L2'])
        self.assertEqual((data,truth),before)
        for rows in result['initial_designs'].values():
            for donor in ['D1','D2']:
                self.assertEqual(sorted(x['condition'] for x in rows if x['donor_id']==donor),
                                 ['control','stim'])

    def test_does_not_fabricate_prehistory_or_human_actions(self):
        result=prepare(*self.fixture())
        self.assertFalse(result['runnable'])
        self.assertFalse(result['human_decisions_preselected'])
        for value in result['required_historical_artifacts'].values():
            self.assertIsNone(value['analysis']);self.assertIsNone(value['counts_only_qc'])
        self.assertFalse(result['qc_condition_label_dependency'])

    def test_counts_mismatch_rejects(self):
        data,truth=self.fixture();truth['counts']['sha256']='b'*64
        with self.assertRaises(ValueError):prepare(data,truth)

    def test_donor_binding_mismatch_rejects(self):
        data,truth=self.fixture();truth['samples'][0]['donor_id']='other'
        with self.assertRaises(ValueError):prepare(data,truth)

    def test_invalid_or_duplicate_pair_rejects(self):
        data,truth=self.fixture();truth['samples'][1]['condition']='stim'
        with self.assertRaises(ValueError):prepare(data,truth)
        data,truth=self.fixture();truth['samples'][1]['library_id']='L1'
        with self.assertRaises(ValueError):prepare(data,truth)


if __name__=='__main__':unittest.main()
