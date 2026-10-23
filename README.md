# BioDuet

Engineering prerelease candidate derived from reviewed LabWeave commit
`b50a8377413785218bc2a3c956d9a0b60d0fb669`. Independent engineering validation covers 81 distinct tests, installed-package
H0/H1 examples and a website build. See [validation](docs/validation.md) for
the selective rerun history and remaining website qualification limits.
BioDuet maintains benchmark contracts and scoring. LabWeave is a participating
system and maintains its own deployment adapter, pinned to a BioDuet release.

## Quick start

Python 3.10 or newer; no runtime Python dependencies for the synthetic example.

```sh
python -m pip install .
bioduet demo --condition H0 --output /tmp/bioduet-h0
bioduet demo --condition H1 --output /tmp/bioduet-h1
```

Output directories must be new. Every turn, decision, result, and failure is
retained locally. The examples are **synthetic engineering replay**, with no
models, R analysis, or formal scientific score. H0/H1 here are examples of the
engineering profile, not the full scientific evaluation.

## Agent integration

`bioduet.runner.run(output, participant=callable)` accepts a trusted callable
that receives a role-specific turn packet and returns a decision. The runner
does not fill in scientific actions. This in-process interface is not a sandbox:
operators must isolate untrusted agents, enforce process deadlines and supply
credential, model-accounting, and cleanup adapters. Unknown call counts remain
null. Calls and turns have no count ceiling; wall time is separate.

The retained `labweave_eval` import namespace preserves source compatibility;
it does not require a LabWeave installation. See `provenance/source-map.json`.
Legacy versioned modules are reference implementations, not default CLI profiles.
Host admission, credential transport, native engine launchers and system adapters
remain outside this package. Their checks have not been bypassed.

## Research and data

The task catalogue contains 24 specifications, not 24 independently validated
runnable tasks. Current public example covers BW-01 engineering interaction.
BW-04/BW-14 expansion remains separate candidate work. Raw datasets, private
truth, models, caches and unreviewed trajectories are not distributed.
Formal and strict scores remain null until their evidence gates are satisfied.
The website contains explicitly labeled demo data, not published results.

## License

Apache-2.0 for project code. Third-party dependencies and external datasets retain
their own licenses; this license does not grant rights to external data.
