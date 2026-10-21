"""New CLI parsing and private expectation binding only."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from labweave_eval import dual_control_oracle_v02 as cli


class CliTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',
            dir=os.environ['BW01_INTEGRATION_SCRATCH']))
        self.paths=[]
        for condition in ['H0','H1']:
            path=self.root/(condition+'.json')
            data=json.dumps({'schema':'synthetic_cli_fixture','condition':condition}).encode()
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(data)
            self.paths.append((str(path),hashlib.sha256(data).hexdigest()))
        self.args=['--expectation',self.paths[0][0],'--expectation-sha256',self.paths[0][1]]

    def test_evaluate_cli_preserves_private_pin_and_trace_source(self):
        result={'engineering_goal_met':False,'scientific_validity':'not_assessed',
                'formal_benchmark_score':None}
        with patch.object(cli,'evaluate',return_value=result) as call,contextlib.redirect_stdout(io.StringIO()) as out:
            code=cli.main(['evaluate']+self.args,raw=b'{"source":"synthetic"}')
        self.assertEqual(code,1)
        self.assertEqual(json.loads(out.getvalue()),result)
        self.assertEqual(call.call_args.args[0]['condition'],'H0')
        self.assertEqual(call.call_args.args[1],{'source':'synthetic'})

    def test_pair_cli_requires_two_distinct_explicit_sources(self):
        result={'pair_comparable':True,'H0':{'engineering_goal_met':True},
                'H1':{'engineering_goal_met':True},'formal_benchmark_score':None}
        args=['pair']+self.args+['--h1-expectation',self.paths[1][0],
                                '--h1-expectation-sha256',self.paths[1][1]]
        with patch.object(cli,'pair',return_value=result) as call,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(args,raw=b'{"H0":{"c":0},"H1":{"c":1}}'),0)
        self.assertEqual(call.call_args.args[0]['condition'],'H0')
        self.assertEqual(call.call_args.args[2]['condition'],'H1')
        self.assertEqual(call.call_args.args[1],{'c':0})
        self.assertEqual(call.call_args.args[3],{'c':1})

    def test_wrong_pin_or_duplicate_trace_keys_rejected_before_evaluation(self):
        with patch.object(cli,'evaluate') as call:
            bad=['evaluate','--expectation',self.paths[0][0],
                 '--expectation-sha256','0'*64]
            with self.assertRaises(ValueError):cli.main(bad,raw=b'{}')
            with self.assertRaises(ValueError):
                cli.main(['evaluate']+self.args,raw=b'{"a":1,"a":2}')
            call.assert_not_called()


if __name__=='__main__':unittest.main()
