"""Schedule regressions go beyond internally consistent recorded portfolios."""
import copy,unittest
from artifact.common import read_json,read_rows
from artifact.study import validate_membership
from artifact import frozen_core as core

class MembershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=read_json('data/tasks.json.gz')
        cls.raw=read_rows('data/calls.jsonl.gz')
        cls.portfolios=read_json('data/portfolios.json.gz')
        cls.dev=read_json('data/development_portfolios.json.gz')
        cls.selection=read_json('data/development_selection.json')
        cls.models=[r['model'] for r in cls.selection['scores']]
    def validate(self,**changes):
        args=dict(manifest=self.manifest,raw=self.raw,portfolios=self.portfolios,development=self.dev,selection=self.selection,models=self.models)
        args.update(changes);return validate_membership(**args)
    def test_complete_union_accounts_for_shared_calls(self):
        result=self.validate()
        self.assertEqual(result['expected_physical_calls'],3824)
        self.assertLess(result['expected_physical_calls'],3*(len(self.portfolios)+len(self.dev)))
    def test_internally_consistent_wrong_strategy_portfolio_is_rejected(self):
        rows=copy.deepcopy(self.portfolios)
        index=next(i for i,r in enumerate(rows) if r['method']=='best_validity3')
        target=rows[index]
        other=next(r for r in rows if r['task_id']==target['task_id'] and r['method']=='best_counterexample3')
        calls={r['uid']:r for r in self.raw};task=next(t for t in self.manifest['test'] if t['task_id']==target['task_id'])
        rows[index]=core.portfolio(task,target['method'],[calls[u] for u in other['candidate_uids']])
        with self.assertRaisesRegex(ValueError,'candidate order/model allocation'):self.validate(portfolios=rows)
    def test_reordered_independent_calls_are_rejected(self):
        rows=copy.deepcopy(self.portfolios)
        target=next(r for r in rows if r['method']=='best_independent3')
        target['candidate_uids'][1:]=reversed(target['candidate_uids'][1:])
        with self.assertRaisesRegex(ValueError,'candidate order/model allocation'):self.validate(portfolios=rows)
    def test_extra_valid_but_unreferenced_call_is_rejected(self):
        extra=copy.deepcopy(self.raw[0]);extra['uid']+='/unexpected'
        with self.assertRaisesRegex(ValueError,'Raw call union'):self.validate(raw=self.raw+[extra])
    def test_missing_physical_call_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Raw call union'):self.validate(raw=self.raw[1:])
    def test_task_phase_model_and_seed_each_checked(self):
        for key,value in [('task_id','foreign_task'),('phase','test'),('model',self.models[1]),('seed',-1)]:
            with self.subTest(key=key):
                rows=copy.deepcopy(self.raw);rows[0][key]=value
                with self.assertRaisesRegex(ValueError,'Raw call identity'):self.validate(raw=rows)
    def test_response_identity_checked_separately(self):
        rows=copy.deepcopy(self.raw);rows[0]['response']['seed']+=1
        with self.assertRaisesRegex(ValueError,'Response identity'):self.validate(raw=rows)
    def test_cross_model_development_membership_rejected(self):
        rows=copy.deepcopy(self.dev);target=rows[0]
        other=next(r for r in rows if r['task_id']==target['task_id'] and r['method']==target['method'] and r['selection_model']!=target['selection_model'])
        target['candidate_uids']=other['candidate_uids'][:]
        with self.assertRaisesRegex(ValueError,'candidate order/model allocation'):self.validate(development=rows)

if __name__=='__main__':unittest.main()
