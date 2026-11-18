# Verified feedback and collaboration

Portable evidence and analysis for an exactly checked reasoning experiment with independent sampling, validity feedback, counterexample feedback, and mixed-model strategies.

The repository rechecks the recorded certificates and reconstructs the reported results. It makes no model calls and requires no model weights or external data downloads after dependency installation.

## Run the audit

Use Python 3.12 from this directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
make test
make verify
```

`make verify` audits both studies and the supplemental comparisons. It writes the original tables and figures to `results/recomputed/` and the replacement tables and supplement to `results/replacement/`. Each study is checked against its separate reference tables. Use `make verify-original` or `make verify-replacement` for one study, or `make audit` to recompute both without reference comparisons.

## Evidence and scope

The original frozen experiment contains 3,824 physical calls, 48 development tasks and 256 test tasks. Development selected the same model configuration for the three homogeneous strategies. Counterexample feedback solved 117 test tasks, validity feedback 115 and independent sampling 78. Mixed counterexample and independent strategies solved 106 and 88. The secondary one-call baseline solved 74; public-input exact solvers solve all 256 finite tasks.

One serving error remains in the frozen data. The prespecified any-request-error rule makes the scientific comparison ineligible. The conservative primary bounds also fail to establish the five-percentage-point superiority criterion. These are descriptive diagnostic results, not evidence of a confirmed coalition advantage or scientific discovery.

The artifact includes a retrospective check of 720 original-pilot test candidates. Eight complete expressions admit the narrowly defined associative normalization, but none becomes a verified certificate. Original scores are unchanged.

Two later one-task diagnostics are separate: one exact-request recovery aborted again; one replacement-model request completed but failed exact verification. Neither enters the original call totals, success rates or hypothesis decisions.

## Completed replacement study

A separate full follow-up replaces the Llama configuration with Mistral while retaining Qwen and Gemma. It repeats all 48 development tasks and 256 already observed test tasks, using 4,848 fresh physical calls with no serving errors. Development chooses Mistral for independent and validity-feedback strategies and Gemma for counterexample feedback. These strategies solve 96, 88 and 115 test tasks; mixed independent and counterexample strategies solve 95 and 111. Matched Gemma independent and validity controls solve 81 and 111.

The follow-up is a post-study substitution on the same viewed task panel. Its comparisons remain descriptive, and it does not replace any original observation or eligibility decision. Evidence and reference tables are kept under `studies/model_replacement/`. See [the follow-up scope](docs/replacement_study.md).

A separate exploratory supplement checks physical usage and retained-configuration repeatability. It reconciles 1,911 matching request identities among 2,976 Qwen/Gemma calls. Full request payloads were compared in the original archives; the portable release rechecks hash matches, recorded texts and outcomes without duplicating those payloads.

## Contents

- `artifact/`: portable checker and audit code. Extracted frozen functions have recorded origins and hashes.
- `data/`: compressed tasks, recorded model outputs, portfolio membership, measured costs and separated diagnostics.
- `provenance/`: original source hashes, model digests, environment and scope records.
- `results/reference/`: immutable original comparison tables.
- `studies/model_replacement/`: separate follow-up data, provenance, reference tables and repeatability ledger.
- `docs/`: data dictionary, frozen protocol and reproduction limits.
- `paper/`: ACM `sigconf` sources and the compiled preprint. `make paper` requires `latexmk` and a TeX installation containing `acmart`. `make figures` rebuilds the publication figures from the bundled audited summaries.

The audit can recompute verification outcomes, strategy counts, cost summaries, paired bounds and diagnostic checks from the included evidence. It does not repeat model generation or reproduce machine-specific historical runtimes. Original generation requires the original pinned serving environment, prompt/controller code and model installation; this repository does not provide a turnkey rerun of that environment. See [the execution notes](docs/original_execution.md).

Generated responses are parsed as restricted JSON and are never executed. No model weights, local caches, secrets or private human-review materials are included. Read [the rights note](LICENSE_NOTE.md) before redistribution.
