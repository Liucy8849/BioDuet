from importlib.resources import files
import csv,gzip,hashlib,json,tempfile,unittest
from pathlib import Path
from labweave_eval.bw01_data_v01 import prepare,FILES,integer_count
from labweave_eval.bw01_science_v01 import validate_design
from labweave_eval.bw01_oracle_v01 import judge
def fixture(root):
    content={
     'genes':'g1\tGene1\ng2\tGene2\n',
     'metadata':'tsne1\ttsne2\tind\tstim\tcluster\tcell\tmultiplets\n'
       'AAAA-1\t0\t0\t101\tctrl\t1\tCD14+ Monocytes\tsinglet\n'
       'BBBB-1\t0\t0\t102\tctrl\t1\tCD14+ Monocytes\tsinglet\n'
       'AAAA-2\t0\t0\t101\tstim\t1\tCD14+ Monocytes\tsinglet\n'
       'CCCC-1\t0\t0\t102\tstim\t1\tCD14+ Monocytes\tsinglet\n',
     'ctrl_barcodes':'AAAA-1\nBBBB-1\n','stim_barcodes':'AAAA-1\nCCCC-1\n',
     'ctrl_matrix':'%%MatrixMarket matrix coordinate real general\n%\n2 2 4\n1 1 10\n2 1 20\n1 2 30\n2 2 40\n',
     'stim_matrix':'%%MatrixMarket matrix coordinate real general\n%\n2 2 4\n1 1 11\n2 1 21\n1 2 31\n2 2 41\n'}
    entries=[]
    for key,text in content.items():
        p=root/FILES[key];p.write_bytes(gzip.compress(text.encode(),mtime=0))
        entries.append({'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    return {'inputs':entries}
def update_manifest(root,manifest,name):
    p=root/name
    for r in manifest['inputs']:
        if r['name']==name:r.update(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def write_table(path,header,rows):
    with path.open('w',newline='') as f:
        w=csv.writer(f,delimiter='\t',lineterminator='\n');w.writerow(header);w.writerows(rows)

class DataTests(unittest.TestCase):
    def test_actual_aggregation_and_target_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest=fixture(root);out=root/'prepared'
            dataset=prepare(root,manifest,out,min_cells=1,source_kind='synthetic_fixture')
            truth=json.loads((out/'private/truth.json').read_text())
            self.assertEqual(dataset['donor_count'],2)
            self.assertIsNone(next(s for s in dataset['samples'] if s['sample_id']=='S01')['condition'])
            self.assertEqual(next(s for s in truth['samples'] if s['sample_id']=='S01')['condition'],'stim')
            self.assertEqual(truth['barcode_mapping']['stim']['suffix_changes'],1)
            with (out/'public/counts.tsv').open() as f:
                rows=list(csv.reader(f,delimiter='\t'))
            self.assertEqual(sum(map(int,rows[1][1:])),82)
            self.assertEqual(sum(map(int,rows[2][1:])),122)
            self.assertEqual(truth['matrix_integrity']['ctrl']['selected_umis'],100)
    def test_hash_tamper_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest=fixture(root)
            (root/FILES['genes']).write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'SOURCE_HASH'):prepare(root,manifest,root/'out',min_cells=1)
            self.assertFalse((root/'out').exists())
    def test_barcode_swap_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest=fixture(root)
            (root/FILES['ctrl_barcodes']).write_bytes(gzip.compress(b'BBBB-1\nAAAA-1\n'))
            update_manifest(root,manifest,FILES['ctrl_barcodes'])
            with self.assertRaisesRegex(ValueError,'BARCODE_ORDER'):prepare(root,manifest,root/'out',min_cells=1)
    def test_duplicate_coordinate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest=fixture(root);p=root/FILES['ctrl_matrix']
            text=gzip.decompress(p.read_bytes()).decode().replace('2 1 20','1 1 20')
            p.write_bytes(gzip.compress(text.encode()));update_manifest(root,manifest,p.name)
            with self.assertRaisesRegex(ValueError,'MATRIX_DUPLICATE'):prepare(root,manifest,root/'out',min_cells=1)
    def test_missing_donor_pair_and_fractional_counts(self):
        for value in ['-1','0','NaN','1.5','Infinity']:
            with self.assertRaises((ValueError,ArithmeticError)):integer_count(value)
        self.assertEqual(integer_count('2.0'),2)
        data={'samples':[{'library_id':'L1','donor_id':'D1'},{'library_id':'L2','donor_id':'D1'}]}
        rows=[{'library_id':'L1','donor_id':'D1','condition':'control'},{'library_id':'L2','donor_id':'D1','condition':'stim'}]
        with self.assertRaisesRegex(ValueError,'PAIRED_DONORS'):validate_design(data,rows)

class OracleTests(unittest.TestCase):
    def setup_case(self,root):
        c=root/'candidate';r=root/'reference';c.mkdir();r.mkdir()
        samples=[{'library_id':'L'+str(i),'donor_id':'D'+str((i-1)//2+1),
                  'condition':'control' if i%2 else 'stim','sample_id':'S01' if i==2 else 'X'+str(i)} for i in range(1,5)]
        header=['library_id','donor_id','condition']
        write_table(c/'design.tsv',header,[[s[k] for k in header] for s in samples])
        results=[['g1',1,4,3,0.01,0.02],['g2',-1,5,1,0.5,0.5]]
        h=['gene_id','logFC','logCPM','F','PValue','FDR']
        write_table(c/'de.tsv',h,results);write_table(r/'reference-de.tsv',h,results)
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        receipt={'status':'succeeded','exit_code':0,'method_id':'bw01-paired-edger-ql/0.1',
                 'counts_sha256':'c'*64,'sample_version':2,'design_version':2,'edgeR_version':'test',
                 'design':{'sha256':sha(c/'design.tsv')},'result':{'sha256':sha(c/'de.tsv')}}
        receipt['script']={'sha256':sha(files('labweave_eval').joinpath('bw01_edger_v01.R'))}
        write_table(r/'truth-design.tsv',header,[[s[k] for k in header] for s in samples])
        (c/'execution.json').write_text(json.dumps(receipt))
        (r/'reference.json').write_text(json.dumps({'status':'succeeded','exit_code':0,'edgeR_version':'test',
             'reference_script_sha256':sha(files('labweave_eval').joinpath('bw01_reference_v01.R')),
             'counts_sha256':'c'*64,'result':{'sha256':sha(r/'reference-de.tsv')}}))
        truth={'samples':samples,'counts':{'sha256':'c'*64}}
        state={'sample':{'condition':'stim','version':2},'design':{'version':2,'sample_version':2}}
        return c,r,truth,state
    def test_pending_review_cannot_claim_science(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.setup_case(Path(tmp));result=judge(*args)
            self.assertEqual(result['technical_validity'],'passed')
            self.assertEqual(result['scientific_validity'],'not_assessed')
            self.assertIsNone(result['strict_goal_completion'])
    def test_stale_version_and_wrong_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,r,t,s=self.setup_case(Path(tmp));s['sample']['version']=3;s['sample']['condition']='control'
            result=judge(c,r,t,s,method_review='accepted')
            self.assertFalse(result['checks']['input_versions_current'])
            self.assertFalse(result['checks']['sample_current_truth'])
            self.assertEqual(result['scientific_validity'],'failed')
    def test_numerical_tamper_even_with_updated_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,r,t,s=self.setup_case(Path(tmp));p=c/'de.tsv'
            p.write_text(p.read_text().replace('g1\t1\t','g1\t9\t'))
            receipt=json.loads((c/'execution.json').read_text());receipt['result']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
            (c/'execution.json').write_text(json.dumps(receipt));result=judge(c,r,t,s)
            self.assertFalse(result['checks']['numeric_reference_agreement'])
    def test_fdr_wrong_in_both_outputs_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,r,t,s=self.setup_case(Path(tmp))
            for table_name,receipt_name,directory in [('de.tsv','execution.json',c),('reference-de.tsv','reference.json',r)]:
                p=directory/table_name;p.write_text(p.read_text().replace('0.02','0.01'))
                record=json.loads((directory/receipt_name).read_text());record['result']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
                (directory/receipt_name).write_text(json.dumps(record))
            result=judge(c,r,t,s)
            self.assertTrue(result['checks']['numeric_reference_agreement'])
            self.assertFalse(result['checks']['independent_bh'])
    def test_missing_and_nonfinite_output_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,r,t,s=self.setup_case(Path(tmp));(c/'de.tsv').write_text('gene_id\tlogFC\tlogCPM\tF\tPValue\tFDR\ng1\tNaN\t1\t1\t0.1\t0.1\n')
            result=judge(c,r,t,s);self.assertEqual(result['technical_validity'],'failed')
            self.assertEqual(result['failure_type'],'ValueError')
if __name__=='__main__':unittest.main()
