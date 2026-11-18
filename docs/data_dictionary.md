# Data dictionary

All files under `data/` and existing provenance records are covered by `data/SHA256SUMS.json`. Gzip archives contain UTF-8 JSON or line-delimited JSON and use deterministic gzip timestamps.

`tasks.json.gz` contains demonstration, development and test task lists. Public task data specify graph edges/endpoints or a complete Boolean truth table. Stored reference certificates are construction checks; the audit independently constructs certificates using public-input exact solvers.

`calls.jsonl.gz` contains each physical call once: stable UID, task ID, phase, model, seed, prompt hash, response text/completion state, frozen verifier decision and available token/timing fields. The one request error has no invented response or missing usage values.

`portfolios.json.gz` specifies test strategy membership through candidate UIDs. Initial candidates shared by strategies are stored once. Every strategy is charged the full cost of its own candidate list, while physical calls are counted once. Null aggregate usage means some required component was not recorded; it is not zero cost.

`development_portfolios.json.gz`, `development_selection.json` and `development_gate.json` preserve model selection and eligibility checks made before test evaluation.

`exact_solver_observed_timings.json.gz` retains historical CPU measurements. The portable audit checks exact-solver correctness again but does not substitute new-machine timing for the archived measurements.

`original_pilot_*` files support the narrowly defined retrospective syntax diagnostic and original held-out task counts. Only 720 original test candidates are exported; the earlier complete pilot had 936 physical calls. These records are separate from the extension.

`diagnostics/model_replacement.json` contains the separate single-task replacement-model protocol, response and exact-check result. Its task is included for self-contained rechecking. `provenance/recovery_observation.json` records the separate exact-request recovery result. Neither modifies frozen experimental outcomes.
