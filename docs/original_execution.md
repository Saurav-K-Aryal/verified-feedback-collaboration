# Original execution and portability

The portable command is `python -m artifact.audit --verify`. It reads only this repository, uses no network and does not contact a model server. It rechecks 3,823 completed-call verifier decisions, reconstructs all frozen test and development portfolios, reruns the public-input exact solver and reproduces table calculations. The serving-error record is retained as an error rather than passed to a certificate checker.

Selected checker, portfolio, paired-bound and diagnostic functions are verbatim extracts of the original frozen implementation. `provenance/extracted_functions.json` records source files, source hashes, first lines and function-text hashes. A small namespace shim supplies their original checker dependency without a workspace-specific path.

A full model-generation rerun would require the exact pinned model installations and server version, the complete frozen prompting/controller environment and comparable hardware. This repository intentionally does not include a broken path-dependent generation entry point. Original source-file hashes allow correspondence checks against the separately retained original execution archive; they are not a substitute for that archive. Model terms apply independently.

The exported raw responses and exact tasks allow the reported correctness claims to be audited without rerunning the models. Historical token accounting and wall times are observations of the original environment; re-executing the audit does not reproduce those timings or erase missing usage fields.

## Separate follow-up bundles

`artifact.study` accepts a complete separate evidence bundle with `data/`, `provenance/`, and `results/reference/` subdirectories. It rechecks every certificate, reconstructs all development and test portfolios, independently derives their exact ordered candidate memberships and the complete union of physical calls, checks task/phase/model/seed identities and model digests, and rederives development selection and the original difficulty gate. It recomputes tables without fixing model names or physical-call counts. Its output must be separate from the input bundle. For a bundled follow-up, the interface is:

```sh
python -m artifact.study --study studies/model_replacement --output results/replacement --verify
```

The completed bundle is included. `make verify` checks both cohorts; the original-only command is `make verify-original`. A model-replacement follow-up on the already observed task panel must be labeled `post_study_replacement` in its provenance and remains descriptive even if it has no serving errors. It does not replace the original records, erase their error, or become an independent confirmation.
