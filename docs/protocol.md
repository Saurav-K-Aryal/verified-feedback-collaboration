# Frozen protocol and analysis

The model configurations were Qwen3.5:4b, Llama3.1:8b and Gemma4:12b, with different model sizes, quantization and serving backends. Exact digests are in the provenance records. Forty-eight development tasks cover two families and three grades; 256 disjoint test tasks retain all prespecified strata. Semantic signatures screen overlapping generated tasks, but graph signatures are not a complete graph-isomorphism quotient.

Each strategy receives three scheduled calls even if an earlier response succeeds. Homogeneous independent, validity-feedback and exact-counterexample strategies select their model on development data only. Mixed-model strategies and matched same-model controls are retained. The initial candidate is shared for matched refinement branches; its cost is fully charged to each strategy. Equal call/token caps do not imply equal FLOPs or equal prompt lengths.

The two primary comparisons require counterexample feedback to exceed independent sampling and validity-only feedback by more than five percentage points. Within each fixed family/grade stratum, simultaneous Clopper–Pearson bounds on positive and negative discordance are combined using task-count weights. Each comparison has nominal 97.5% coverage under the working within-stratum independent-binomial assumptions. The finite procedural panel and semantic deduplication limit that sampling interpretation.

The frozen rule disqualifies scientific superiority inference if any serving error occurs. One such error occurred. Rechecking, a later exact-request recovery, or a replacement model cannot remove that rule after seeing outcomes. Counts and intervals remain descriptive, and the intervals do not establish the prespecified gain anyway.

First-call results are a secondary descriptive analysis. The exact solver is a substantive public-input baseline, not a learned model. Its inexpensive success does not support a practical model advantage on these finite tasks.

The retrospective normalization accepts only complete n-ary associative Boolean expressions and rechecks their truth-table semantics. It does not repair truncated answers, invent missing operators or alter original scores.
