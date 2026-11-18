import tempfile,unittest
from artifact.common import ROOT,read_json
from artifact.study import run
from artifact.supplement import run as supplement

class ReplacementTests(unittest.TestCase):
    def test_complete_followup_reconciliation_remains_descriptive(self):
        with tempfile.TemporaryDirectory() as out:result=run(ROOT/'studies/model_replacement',out,verify=True)
        self.assertEqual(result['physical_calls'],4848);self.assertEqual(result['request_errors'],0)
        self.assertEqual(result['test_tasks'],256);self.assertEqual(result['first_call_solved'],73)
        self.assertTrue(result['original_gate_conditions_met']);self.assertFalse(result['scientific_comparison_valid'])
        self.assertEqual(result['selected_models']['independent'],'mistral-small3.2:24b')
        self.assertEqual(result['selected_models']['counterexample'],'gemma4:12b')
        self.assertEqual(result['method_solved']['matched_validity3'],111)
    def test_repeatability_and_physical_usage_reconcile(self):
        with tempfile.TemporaryDirectory() as out:result=supplement(ROOT/'studies/model_replacement',out,verify=True)
        self.assertEqual(result['matched_identity_pairs'],1911)
        self.assertEqual(result['retained_configuration_calls'],2976)
        self.assertFalse(result['full_request_payloads_rechecked_here'])
    def test_original_cohort_remains_ineligible(self):
        original=read_json('results/reference/summary.json')
        self.assertEqual(original['request_errors'],1);self.assertEqual(original['physical_calls'],3824)
        self.assertFalse(original['scientific_comparison_valid'])

if __name__=='__main__':unittest.main()
