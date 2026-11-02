# BioDuet

BioDuet is an independent life-science benchmark for human–Agent scientific collaboration under asymmetric information and action permissions.

Paper title: **BioDuet: A Dual-Control Benchmark for Human–Agent Scientific Collaboration in Life Sciences**.

## Repository

- src/bioduet: public CLI and engineering runner.
- src/bioduet_eval: independent evaluator and task-world code.
- src/bioduet_vnext: native-session, workspace, job and evidence implementations under development.
- scripts/: development and native/scientific utilities.
- tests/: lightweight offline regression tests.
- website/: independent Vue score/evidence website, not a general-purpose scientific platform.
- docs/: BioDuet-only project, research and development information.

## Local check

Python 3.10+; the lightweight suite uses the standard library and needs no models, database or R installation.

```sh
python scripts/test.py
```

## Development

Code and lightweight checks run locally. Changes are committed to Git and pulled by the independent Linux server checkout for full validation. See [development](docs/development.md).

The repository contains 24 task specifications and engineering examples. These are not 24 scientifically validated tasks. Simulated replay is engineering regression, not an Agent leaderboard result. Formal scientific results remain unavailable.

See [START_HERE](START_HERE.md), [requirements](docs/requirements.md), and [current state](docs/current-status.md). The earlier per-change admission/handoff workflow is not the development policy of this project. Other functional engineering and evaluations remain paused.

## License

Apache-2.0 for project code. Original attribution and extraction history remain in NOTICE and provenance/. External dependencies and datasets retain their own licenses.
