# Full replacement follow-up

This bundle records a new execution of every development and test comparison with Qwen, Mistral and Gemma. The original Qwen/Llama/Gemma evidence, original serving error and one-task diagnostics remain unchanged in the main data directory. The follow-up has 48 development tasks, 256 test tasks and 4,848 physical calls, with no request failures. All task inputs were already observed before this follow-up was specified.

The protocol retained the original development selection and comparator definitions, but amended the difficulty gate to be diagnostic: the whole test panel would be collected even if the gate failed. The original gate conditions happened to be met. This does not make the post-study substitution confirmatory. The portable report therefore separates `development_gate_eligible`, `original_gate_conditions_met` and the always-false `scientific_comparison_valid` flag.

Development chooses Mistral for independent sampling and validity feedback, and Gemma for counterexample feedback. The seven logical strategy labels are retained, including matched Gemma controls. Changing the selected models changes the union of physical calls because some strategy trajectories can no longer share identical candidates. The audit reconstructs that union from the planned strategies, model order and seeds instead of assuming the original call count.

## Recompute

```sh
make verify-replacement
```

This checks every response against the exact verifier, the complete planned call membership, model digests, seed identities, development selection, the diagnostic gate, all portfolio costs, and the independent reference tables. Outputs go to `results/replacement/`. Historical costs are re-summed from recorded values, not measured anew. The exact-solver timing artifact is explicitly copied from the original study; only its certificates are rechecked here.

The comparison uses configured systems with different model sizes, quantization and serving backends. Equal scheduled calls and output caps do not establish equal FLOPs, equal realized token usage, or an isolated model-family effect. Fresh outputs on a reused panel do not supply independent test tasks.

The `parameters` field in `generation_models.json` records installed model defaults. Actual requests applied the frozen client overrides, including temperature 0.7, top-p 0.9, repetition penalty 1.0, an 8,192-token context and a 512-token completion cap. The archive audit checked those request values; model defaults should not be read as the executed settings.

## Supplemental cost and repeatability audit

`artifact.supplement` recomputes physical usage, family totals and a post hoc retained-configuration comparison. Its input ledger contains all 2,976 new Qwen/Gemma calls, including 1,911 whose request identity hash matches an original request. The ledger supplies old/new record identifiers, request identity hashes, text hashes and verifier outcomes. All numerical summaries are rederived from the original and follow-up raw responses.

The original archive audit additionally compared the full request objects, including prompt, system instruction, options, model digest and server version. Those objects are not duplicated here. Their archive hashes and the independent audit hash are retained in `provenance/supplement_scope.json`. The portable audit verifies the compact witnesses and their outcomes; it does not reconstruct the omitted full request objects.

This repeatability comparison is exploratory. Matching feedback requests are selected by having identical preceding response context, so their concordance is not an unconditional repeatability estimate or independent model replication. No new significance test is attached to these rows.
