# Exact finite tree search

This CPU study evaluates Levin search against an exact rank floor and upper bound. It uses only the Python standard library. Run these commands from this folder.

```sh
python validate.py --out local_validation.json
python t3b.py --out local_runs/T3-B
```

Each new run freezes its protocol and source before enumeration and refuses to overwrite an existing run. Use `--prepare-only` to freeze without execution, then `--execute-frozen` with the same output folder. A custom protocol can be supplied with `--protocol` during preparation.

The archived results contain 640 exact finite tree cases. All satisfied the stated bounds. At binary depth eight and dead end mass one half, changing dead branch topology changed the expansion count from 16 to 510 with the same rank floor and Levin bound. The finite full-scan crossover does not establish an asymptotic phase transition.

`results/T3-B/` contains the original frozen protocol, compact result and exact-cell CSV. `DESIGN.txt` gives definitions and proofs. `provenance/` records source hashes, validation and public execution adaptations. The scientific entrypoint is unchanged. Private scheduling guards were removed from the public adapter.

The archived default waiting-window timestamp was overridden by an explicit start instruction before the original runs. Historical protocols and timestamps are preserved. The scheduling note in `provenance/PORTABLE_ADAPTATIONS.json` explains this without including private authorization records.
