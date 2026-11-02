import csv,json,tempfile,unittest
from pathlib import Path
from test_bw01_science_v01 import fixture,write_table
from bioduet_eval.bw01_data_v01 import prepare
from bioduet_eval.bw01_result_view_v01 import summarize
class ResultViewTests(unittest.TestCase):
    def test_actual_values_and_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dataset=prepare(root,fixture(root),root/'prepared',min_cells=1,source_kind='synthetic_fixture')
            result=root/'result';result.mkdir()
            write_table(result/'de.tsv',['gene_id','logFC','logCPM','F','PValue','FDR'],[['g1',2,4,10,.001,.002],['g2',-1,4,2,.4,.4]])
            view=summarize(result,dataset,root/'prepared/public')
            self.assertEqual(view['tested_genes'],2);self.assertEqual(view['significant_genes'],1)
            self.assertEqual(view['top_genes'][0]['symbol'],'Gene1')
            self.assertEqual(view['significant_up'],1)
            self.assertEqual(view['top_genes'][0]['logFC'],'2')
            (root/'prepared/public/gene-annotations.tsv').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'ANNOTATION_IDENTITY'):summarize(result,dataset,root/'prepared/public')
if __name__=='__main__':unittest.main()
