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

`make verify` writes tables, figures, and `AUDIT_STATUS.json` to `results/recomputed/`, and compares every published reference-table entry with the recomputation. The checked reference tables are under `results/reference/`. Run `make audit` to recompute without the reference comparison.

## Evidence and scope

The main frozen experiment contains 3,824 physical calls, 48 development tasks and 256 test tasks. Development selected the same model configuration for the three homogeneous strategies. Counterexample feedback solved 117 test tasks, validity feedback 115 and independent sampling 78. Mixed counterexample and independent strategies solved 106 and 88. The secondary one-call baseline solved 74; public-input exact solvers solve all 256 finite tasks.

One serving error remains in the frozen data. The prespecified any-request-error rule makes the scientific comparison ineligible. The conservative primary bounds also fail to establish the five-percentage-point superiority criterion. These are descriptive diagnostic results, not evidence of a confirmed coalition advantage or scientific discovery.

The artifact includes a retrospective check of 720 original-pilot test candidates. Eight complete expressions admit the narrowly defined associative normalization, but none becomes a verified certificate. Original scores are unchanged.

Two later one-task diagnostics are separate: one exact-request recovery aborted again; one replacement-model request completed but failed exact verification. Neither enters the original call totals, success rates or hypothesis decisions.

## Contents

- `artifact/`: portable checker and audit code. Extracted frozen functions have recorded origins and hashes.
- `data/`: compressed tasks, recorded model outputs, portfolio membership, measured costs and separated diagnostics.
- `provenance/`: original source hashes, model digests, environment and scope records.
- `results/reference/`: immutable comparison tables.
- `docs/`: data dictionary, frozen protocol and reproduction limits.
- `paper/`: ACM `sigconf` sources and the compiled preprint. `make paper` requires `latexmk` and a TeX installation containing `acmart`. `make figures` rebuilds the publication figures from the bundled audited summaries.

The audit can recompute verification outcomes, strategy counts, cost summaries, paired bounds and diagnostic checks from the included evidence. It does not repeat model generation or reproduce machine-specific historical runtimes. Original generation requires the original pinned serving environment, prompt/controller code and model installation; this repository does not provide a turnkey rerun of that environment. See [the execution notes](docs/original_execution.md).

Generated responses are parsed as restricted JSON and are never executed. No model weights, local caches, secrets or private human-review materials are included. Read [the rights note](LICENSE_NOTE.md) before redistribution.
