# Prospective runtime scheduling amendment

This package records an operational change before the remaining Mistral and Phi
test generations. The original serial-inference wording is prospectively
superseded for request ordering, an isolated local endpoint, and benchmark-selected
concurrency. It is not represented as an unchanged execution schedule.

The original frozen task identifiers, selected input texts, prompt hashes,
per-task seeds, model digests, context and decoding settings, exact checkers,
detector definitions, thresholds, and analysis rules are preserved. Batching can
change numerical execution. Bit-identical model outputs are not promised.

## Decision before the remaining tests

After the primary Gemma study exits with complete artifacts, an isolated local
server is configured with two request slots per model. A separate synthetic
timing workload compares the same four requests in serial, one request per model,
and two requests per model. Four balanced blocks use identical seeds and output
caps across modes. Actual backend slots and per-slot context are checked.

Two requests per model are selected only with at least a 10 percent median paired
wall-time reduction and at least three wins in four blocks against both the
one-request-per-model condition and serial execution. Otherwise one request per
model is selected only when it meets the corresponding gate against serial.
A valid comparison that supports neither parallel mode retains serial execution.
The comparison also requires identical output-token counts, zero request errors,
and the frozen memory and power conditions. Incomplete or invalid benchmark work
halts the supervisor for inspection.

Mistral timing and sample-size selection finish before Phi is released. The
dispatchers submit each frozen task once, retain recorded errors, and refuse an
automatic retry when a durable submission lacks a final record. Detector scoring
waits until generation clients finish, model work is drained, and the isolated
server is stopped. The absolute stop remains November 19, 2026 at 21:00 UTC.

## Initial conditional timing evidence

The included initial benchmark ran while Gemma continued in the background.
Mistral and Phi together completed their foreground workload 24.0 percent faster
by median paired wall time, with four of four blocks faster and zero errors.
Each timed request produced 128 tokens. This is not evidence of a 24 percent
full-queue speedup, and it does not justify interrupting the primary study.

The four-way benchmark has not run at this checkpoint. No four-way speedup or
remaining-test scientific result is claimed in this package.

## Reproduction and privacy

These are validated scheduling adapters and their synthetic tests, not a
standalone inference distribution. They require the original private project
layout, its frozen scientific implementations and inputs, and the specified
local runtime. In particular, run_remaining_v2.py imports the original
run_remaining.py; the public export does not include a live execution plan or
process identifiers. The original scientific implementations are called by the
adapters rather than silently replaced.

OPERATIONAL_AMENDMENT.json is a compact extraction of the reviewed controller
amendment with scoped provenance hashes. It is not the full private dependency
chain. PRIVACY_HASH_MANIFEST.json records original and public hashes. Absolute
local project paths in JSON documents are replaced with PROJECT_ROOT. Included
Python files are byte-identical to their validated local sources.

Raw source prose, generated responses, individual detector outcomes, rating
sheets, assignment keys, reviewer identities, credentials, Drive links, model
weights, and live process records are excluded. The initial benchmark protocol
contains synthetic timing prompts only. No publication is performed by the
staging script.
