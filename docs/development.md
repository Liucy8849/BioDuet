# Development and validation

Local checkout: D:/code/BioDuet.
Server checkout: /data1/Liuchenyu/bioduet/project.
Remote: https://github.com/Liucy8849/BioDuet.git.
Separation branch: codex/bioduet-independent-20261102.

Develop and run lightweight tests locally:

```sh
python scripts/test.py
```

Commit the actual changes and push the working branch. The server then fetches/pulls that branch and performs Linux/full validation. This is ordinary Git collaboration, not a per-file approval process. Never use a shared writable checkout/index with another application.

For the current separation, the full repository regression command on Linux is also `python3 scripts/test.py`. It exercises the repository's offline tests. SDK/native sessions, browser tests, R, real data and model evaluation require their actual dependencies and inputs; this command does not claim those capabilities.

Temporary tests use an explicit temporary scratch directory and clean it up automatically. Datasets, environments, caches and credentials are not committed. Website development is in website/ and has its own package.json; its current Node requirement is >=22.15.0. No browser or dependency installation was performed as part of this separation.

All other functional work remains paused until explicitly resumed.
