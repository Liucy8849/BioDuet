import json,tempfile,unittest
from pathlib import Path
from labweave_eval.bw01_artifacts_v01 import RoleAdmissionJournal
class AdmissionJournalTests(unittest.TestCase):
    def test_exact_units_durable_before_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);journal=RoleAdmissionJournal(root)
            record={'role':'A','unit':'labweave-bw01-'+'a'*32+'.scope','state':'starting'}
            journal.append(record)
            self.assertEqual(json.loads((root/'role-A-admission.json').read_text()),record)
            record['state']='ready'
            self.assertEqual(journal[0]['state'],'ready')
            with self.assertRaises(FileExistsError):journal.append(record)
            self.assertEqual(len(journal),1)
    def test_foreign_unit_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=RoleAdmissionJournal(tmp)
            with self.assertRaisesRegex(ValueError,'ROLE_ADMISSION_IDENTITY'):
                journal.append({'role':'A','unit':'unowned.service'})
            self.assertEqual(list(Path(tmp).iterdir()),[])
if __name__=='__main__':unittest.main()
