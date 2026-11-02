# Current state — 2026-11-02

The independent local source checkout is D:/code/BioDuet; the independent server checkout is /data1/Liuchenyu/bioduet/project. They use the existing BioDuet repository and separation branch, rather than another application's checkout or writable Git index.

The evaluator package is now bioduet_eval. Imports and package data use that name directly, without a compatibility alias. Active source paths are relative to this checkout; historical absolute paths remain only as provenance. Existing behavior was not redesigned.

The offline repository suite contains 81 tests. The initial local invocation exposed a missing explicit test scratch variable; the portable test entry now supplies that fixture configuration. The suite passed locally after separation (81/81). The server pulled the separation commit and ran the complete offline repository suite once: 81/81 passed. These checks did not run models, R, SDK sessions, browser tests or scientific evaluations.

The repository includes CLI/runner/evaluators, native-session development sources, a score website and all 24 task cards. It does not include a completed general-purpose digital scientific platform, production database or complete native scientific environment.

No complete autonomous BW-01 scientific episode, all-24 scientific acceptance or formal benchmark score is claimed. Historical engineering/model/computation results are not erased, but do not imply those outcomes.

Historical source-only candidates are preserved separately on the server under /data1/Liuchenyu/bioduet/archive; historical raw data and private run records have not been imported into the source repository. They are not active dependencies.

The former implementation checklist and per-change approval workflow are not current work instructions. Functional development, model/R evaluations, deployment and automated continuation remain paused; only this repository/directory/document separation and its necessary checks were authorized.
