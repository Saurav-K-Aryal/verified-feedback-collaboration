"""No-inference tests of T3 dispatch identity, durability and budget guards."""
import json
import fcntl
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
import time
import unittest
import dispatch_t3 as dispatch

study=dispatch.study


def tasks():
    result=[]
    for index in range(2):
        task=dict(task_id=f'unit_{index}',seed=100+index,bridge_depth=1,family='directed_path',
            public=dict(start='a',goal='c',edges=[['a','b'],['b','c']],max_path_nodes=3),
            bridge=dict(entry='a',exit='c',path=['a','b','c']))
        task['task_sha256']=study.old.digest(task)
        result.append(task)
    return result


class FakeClient:
    def __init__(self,path,mode='valid',deadline=None):
        self.out=Path(path);self.out.mkdir(parents=True,exist_ok=True)
        self.base='http://127.0.0.1:11535';self.models=['fake']
        self.metadata={'fake':{'digest':'fake-digest'}};self.version={'version':'fake-version'}
        self.deadline=time.monotonic()+60 if deadline is None else deadline
        self.calls=0;self.cache_hits=0;self.context=8192;self.request_timeout=300
        self.mode=mode;self.seen=[];self.guard=threading.Lock()

    def generate_sweep(self,model,prompt,seed,temperature,top_p):
        with self.guard:self.seen.append((model,prompt,seed,temperature,top_p))
        if self.mode=='budget':raise study.local_models.BudgetExceeded('fake budget')
        if self.mode=='exception':raise RuntimeError('fake request failure')
        if self.mode=='expire':self.deadline=time.monotonic()-1
        time.sleep(.001)
        self.calls+=1
        return dict(text='not JSON' if self.mode=='malformed' else '{"path":["a","b","c"]}',
            done=True,finish_reason='stop',wall_seconds=.001,model=model,seed=seed)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.task_list=tasks();self.configs=[study.CONFIGS[0],study.CONFIGS[-1]]
        self.schedule_seed=221

    def tearDown(self):self.temp.cleanup()

    def run_case(self,client,workers=2,filename='test_calls.jsonl'):
        return dispatch.execute_tests(client,'fake',self.task_list,self.configs,
            self.root/filename,self.schedule_seed,workers,worker_factory=lambda c,i:c)

    def test_parallel_identity_payload_seed_and_exact_checker_parity(self):
        serial=FakeClient(self.root/'serial')
        self.assertTrue(dispatch.ORIGINAL_EXECUTE(serial,'fake',self.task_list,self.configs,
            self.root/'serial.jsonl',self.schedule_seed))
        parallel=FakeClient(self.root/'parallel')
        self.assertTrue(self.run_case(parallel))
        self.assertEqual(sorted(serial.seen),sorted(parallel.seen))
        expected=[(t['task_id'],c['name'],s) for t,c,s in dispatch.schedule_for(self.task_list,self.configs,self.schedule_seed)]
        intents=study.rows(self.root/'test_dispatch_intents.jsonl')
        self.assertEqual([dispatch.identity(r) for r in intents],expected)
        serial_rows={dispatch.identity(r):r for r in study.rows(self.root/'serial.jsonl')}
        parallel_rows=study.rows(self.root/'test_calls.jsonl')
        self.assertEqual(set(serial_rows),{dispatch.identity(r) for r in parallel_rows})
        for row in parallel_rows:self.assertEqual(row['verdict'],serial_rows[dispatch.identity(row)]['verdict'])

    def test_one_worker_call_order_matches_original(self):
        serial=FakeClient(self.root/'serial')
        dispatch.ORIGINAL_EXECUTE(serial,'fake',self.task_list,self.configs,self.root/'serial.jsonl',self.schedule_seed)
        parallel=FakeClient(self.root/'parallel')
        self.assertTrue(self.run_case(parallel,workers=1))
        self.assertEqual(serial.seen,parallel.seen)

    def test_malformed_responses_remain_failed_observations(self):
        client=FakeClient(self.root/'client',mode='malformed')
        self.assertTrue(self.run_case(client))
        records=study.rows(self.root/'test_calls.jsonl')
        self.assertEqual(len(records),12)
        self.assertTrue(all(not r['verdict']['accepted'] and r['verdict']['kind']=='malformed' for r in records))

    def test_exceptions_are_recorded_once_and_never_retried(self):
        client=FakeClient(self.root/'client',mode='exception')
        self.assertTrue(self.run_case(client))
        self.assertEqual(len(client.seen),12)
        self.assertTrue(all('error' in r['response'] and not r['verdict']['accepted'] for r in study.rows(self.root/'test_calls.jsonl')))
        self.assertTrue(self.run_case(client))
        self.assertEqual(len(client.seen),12)

    def test_expired_budget_sends_nothing(self):
        client=FakeClient(self.root/'client',deadline=time.monotonic()-1)
        self.assertFalse(self.run_case(client))
        self.assertEqual(client.seen,[])
        self.assertFalse((self.root/'test_dispatch_intents.jsonl').exists())

    def test_budget_stops_within_one_bounded_wave(self):
        client=FakeClient(self.root/'client',mode='expire')
        self.assertFalse(self.run_case(client))
        self.assertLessEqual(len(client.seen),2)
        self.assertEqual(len(study.rows(self.root/'test_calls.jsonl')),len(client.seen))

    def test_budget_after_intent_requires_manual_resolution(self):
        client=FakeClient(self.root/'client',mode='budget')
        self.assertFalse(self.run_case(client))
        self.assertLessEqual(len(client.seen),2)
        before=len(client.seen)
        with self.assertRaisesRegex(RuntimeError,'Ambiguous prior attempt'):
            self.run_case(client)
        self.assertEqual(len(client.seen),before)

    def test_duplicate_record_refused(self):
        client=FakeClient(self.root/'client')
        self.run_case(client)
        record=study.rows(self.root/'test_calls.jsonl')[0]
        dispatch.durable_append(self.root/'test_calls.jsonl',record)
        with self.assertRaisesRegex(RuntimeError,'duplicate committed'):
            self.run_case(client)

    def test_unknown_slot_refused(self):
        client=FakeClient(self.root/'client')
        self.run_case(client)
        path=self.root/'test_calls.jsonl';records=study.rows(path);records[0]['slot']=99
        path.write_text(''.join(json.dumps(r)+'\n' for r in records))
        with self.assertRaisesRegex(RuntimeError,'Unknown or duplicate'):
            self.run_case(client)

    def test_missing_committed_record_refuses_retry(self):
        client=FakeClient(self.root/'client')
        self.run_case(client)
        path=self.root/'test_calls.jsonl';records=study.rows(path)
        path.write_text(''.join(json.dumps(r)+'\n' for r in records[:-1]))
        with self.assertRaisesRegex(RuntimeError,'Ambiguous prior attempt'):
            self.run_case(client)

    def test_missing_intent_for_completed_result_refused(self):
        client=FakeClient(self.root/'client')
        self.run_case(client)
        path=self.root/'test_dispatch_intents.jsonl';records=study.rows(path)
        path.write_text(''.join(json.dumps(r)+'\n' for r in records[:-1]))
        with self.assertRaisesRegex(RuntimeError,'no durable dispatch intent'):
            self.run_case(client)

    def test_changed_intent_payload_refused(self):
        client=FakeClient(self.root/'client')
        self.run_case(client)
        path=self.root/'test_dispatch_intents.jsonl';original=study.rows(path)
        for field in ['seed','prompt_sha256','task_sha256','temperature','top_p','schedule_index']:
            records=[dict(r) for r in original];records[0][field]='altered'
            path.write_text(''.join(json.dumps(r)+'\n' for r in records))
            with self.assertRaisesRegex(RuntimeError,'differs from the original'):
                self.run_case(client)

    def test_changed_response_seed_refused(self):
        client=FakeClient(self.root/'client')
        self.run_case(client)
        path=self.root/'test_calls.jsonl';records=study.rows(path);records[0]['response']['seed']=-1
        path.write_text(''.join(json.dumps(r)+'\n' for r in records))
        with self.assertRaisesRegex(RuntimeError,'response seed differs'):
            self.run_case(client)

    def test_worker_clone_has_common_deadline_and_separate_ledger(self):
        client=FakeClient(self.root/'client')
        first=dispatch.clone_client(client,0);second=dispatch.clone_client(client,1)
        self.assertEqual(first.deadline,second.deadline)
        self.assertEqual(first.deadline,client.deadline)
        self.assertNotEqual(first.out,second.out)
        self.assertEqual(first.metadata,client.metadata)

    def cli(self,*extra):
        return subprocess.run([sys.executable,str(Path(dispatch.__file__)),
            '--workers','2','replicate','--authorize-run','--out',str(self.root/'run'),
            '--replicate-from',str(self.root/'source'),*extra],capture_output=True,text=True)

    def test_wrong_endpoint_refused_before_any_client(self):
        result=self.cli('--model','mistral-small3.2:24b','--base-url','http://127.0.0.1:11434')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('reviewed isolated localhost endpoint',result.stderr)
        self.assertFalse((self.root/'run').exists())

    def test_model_must_be_explicit_approved_family(self):
        for args in [[],['--model','gemma4:12b']]:
            result=self.cli(*args)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((self.root/'run').exists())

    def test_second_process_cannot_own_same_run(self):
        run=self.root/'run';run.mkdir()
        with (run/'T3_DISPATCH.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=self.cli('--model','mistral-small3.2:24b')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Another dispatcher owns this run directory',result.stderr)
        self.assertFalse((run/'T3_DISPATCH_PLAN.json').exists())


if __name__=='__main__':unittest.main(verbosity=2)
