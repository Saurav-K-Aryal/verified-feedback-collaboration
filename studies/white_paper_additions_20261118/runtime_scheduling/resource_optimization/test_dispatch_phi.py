#!/usr/bin/env python3
"""Synthetic scheduling checks. No model endpoint is contacted."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import dispatch_phi as d

class FakeClient:
    def __init__(self, fail_seed=None):
        self.calls=[];self.fail_seed=fail_seed;self.active=0;self.peak=0
    def generate(self,model,prompt,**kwargs):
        self.active+=1;self.peak=max(self.peak,self.active)
        try:
            self.calls.append((model,prompt,kwargs));time.sleep(.005)
            if kwargs['seed']==self.fail_seed:raise RuntimeError('Synthetic request failure')
            return {'text':' '.join(['synthetic']*110),'done':True,'finish_reason':'stop','seed':kwargs['seed']}
        finally:self.active-=1

class DispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.phi=d.scientific_module()
        cls.p={'prompts':{'system':'Synthetic rewrite system','rewrite':'Preserve this synthetic parent\n{text}'}}
        cls.parents={};cls.tasks=[]
        for i in range(8):
            text=f'Synthetic parent {i}.'
            cls.parents[f'p{i}']={'text':text}
            cls.tasks.append({'id':f't{i}','parent_id':f'p{i}','seed':100+i,
                'parent_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'prompt_sha256':hashlib.sha256(cls.p['prompts']['rewrite'].format(text=text).encode()).hexdigest()})
    def run_one(self,c,t):return self.phi.generate_one(c,self.p,t,self.parents[t['parent_id']])
    def test_exact_payload_seed_key_and_outcome_parity(self):
        serial=FakeClient();expected=[self.run_one(serial,t) for t in self.tasks]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);clients=[FakeClient(),FakeClient()]
            got=d.dispatch(self.tasks,clients,root/'records',root/'attempts',self.run_one,time.time()+10)
            self.assertEqual({x['id'] for x in got},{x['id'] for x in expected})
            calls=[x for c in clients for x in c.calls]
            self.assertEqual(sorted(calls,key=lambda x:x[2]['seed']),serial.calls)
            byid={x['id']:x for x in expected}
            for row in got:
                for key in ['seed','text','done','finish_reason','word_count','status','length_contract_pass']:
                    self.assertEqual(row[key],byid[row['id']][key])
            self.assertEqual(len(d.rows(root/'attempts')),8)
            self.assertTrue(all(c.peak==1 for c in clients))
    def test_recorded_errors_are_retained_and_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);clients=[FakeClient(fail_seed=103),FakeClient(fail_seed=103)]
            got=d.dispatch(self.tasks,clients,root/'records',root/'attempts',self.run_one,time.time()+10)
            self.assertEqual(sum(r['status']=='error' for r in got),1)
            again=[FakeClient(),FakeClient()]
            d.dispatch(self.tasks,again,root/'records',root/'attempts',self.run_one,time.time()+10)
            self.assertEqual(sum(len(c.calls) for c in again),0)
    def test_crash_with_unresolved_intent_refuses_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d.append(root/'attempts',self.tasks[0])
            clients=[FakeClient()]
            with self.assertRaisesRegex(RuntimeError,'Ambiguous'):
                d.dispatch(self.tasks,clients,root/'records',root/'attempts',self.run_one,time.time()+10)
            self.assertEqual(clients[0].calls,[])
    def test_deadline_does_not_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);clients=[FakeClient(),FakeClient()]
            with self.assertRaises(RuntimeError):
                d.dispatch(self.tasks,clients,root/'records',root/'attempts',self.run_one,time.time()-1)
            self.assertEqual(sum(len(c.calls) for c in clients),0)
            self.assertEqual(d.rows(root/'attempts'),[])
    def test_duplicate_unknown_and_altered_records_rejected(self):
        row=dict(self.tasks[0]);bad=dict(row,seed=-1)
        for records,intents in [([row,row],[row]),([row],[bad]),([dict(row,id='unknown')],[row])]:
            with self.assertRaises(RuntimeError):d.validate_resume(self.tasks,records,intents)
    def test_worker_exception_stops_new_dispatch_and_keeps_completed_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def fail(c,t):
                if t['id']=='t0':raise RuntimeError('Synthetic worker crash')
                time.sleep(.01);return dict(t,status='completed')
            with self.assertRaisesRegex(RuntimeError,'Synthetic worker crash'):
                d.dispatch(self.tasks,[None,None],root/'records',root/'attempts',fail,time.time()+10)
            self.assertEqual({x['id'] for x in d.rows(root/'attempts')},{'t0','t1'})
            self.assertEqual({x['id'] for x in d.rows(root/'records')},{'t1'})
    def test_one_worker_preserves_frozen_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            got=d.dispatch(self.tasks,[FakeClient()],root/'records',root/'attempts',self.run_one,time.time()+10)
            self.assertEqual([x['id'] for x in got],[t['id'] for t in self.tasks])

if __name__=='__main__':unittest.main(verbosity=2)
