import copy,tempfile,unittest
from pathlib import Path
from artifact import frozen_core as core
from artifact.audit import run
from artifact.common import ROOT,read_json

class EvidenceTests(unittest.TestCase):
    def test_protected_output_rejected_before_any_write(self):
        from artifact.common import safe_output
        for path in [ROOT, ROOT.parent, ROOT/'data', ROOT/'data/new', ROOT/'results', ROOT/'results/reference', ROOT/'artifact']:
            with self.assertRaises(ValueError):safe_output(path)
        self.assertEqual(safe_output(ROOT/'results/recomputed'),ROOT/'results/recomputed')
    def test_generic_study_rechecks_original_without_fixed_model_counts(self):
        from artifact.study import run as run_study
        with tempfile.TemporaryDirectory() as out:result=run_study(ROOT,out,verify=True)
        self.assertEqual(result['physical_calls'],3824)
        self.assertTrue(result['original_gate_conditions_met'])
        self.assertFalse(result['scientific_comparison_valid'])
    def test_generic_study_output_cannot_overlap_evidence(self):
        from artifact.study import run as run_study
        with self.assertRaises(ValueError):run_study(ROOT,ROOT/'results/recomputed')
    def test_complete_offline_reference_reconciliation(self):
        with tempfile.TemporaryDirectory() as out:result=run(out,verify=True,plots=False)
        self.assertEqual(result['physical_calls'],3824);self.assertFalse(result['scientific_comparison_valid'])
        self.assertEqual(result['method_solved']['best_counterexample3'],117)
    def test_exact_solver_uses_public_input_without_reference_certificate(self):
        for task in read_json('data/tasks.json.gz')['test']:
            public_only=copy.deepcopy(task);public_only.pop('reference_certificate')
            self.assertTrue(core.check_candidate(public_only,core.canonical(core.exact_solve(public_only)))['accepted'])
    def test_duplicate_keys_and_arbitrary_expression_rejected(self):
        with self.assertRaises(ValueError):core.strict_json('{"expr":true,"expr":false}')
        task=next(t for t in read_json('data/tasks.json.gz')['test'] if t['family']=='boolean_program')
        self.assertFalse(core.check_candidate(task,'{"expr":"__import__(os)"}')['accepted'])
        self.assertFalse(core.check_candidate(task,core.canonical(task['reference_certificate']),finish_reason='length')['accepted'])
    def test_tied_pair_boundary_not_false_equivalence(self):
        rows=[]
        for i in range(40):
            for method in ['a','b']:rows.append({'task_id':str(i),'method':method,'family':'boolean_program','regime':'grade_0','accepted':0})
        bounds=core.conservative_comparison(rows,'a','b')['conservative_paired_interval']
        self.assertLess(bounds[0],0);self.assertGreater(bounds[1],0)
    def test_replacement_diagnostic_is_wrong_and_separate(self):
        record=read_json('data/diagnostics/model_replacement.json');self.assertFalse(record['result']['verdict']['accepted'])
        self.assertFalse(record['result']['original_observation_replaced'])
    def test_readme_has_no_personal_name_or_affiliation(self):
        text=(ROOT/'README.md').read_text().lower()
        for word in ['saurav','aryal','howard','university']:self.assertNotIn(word,text)

if __name__=='__main__':unittest.main()
