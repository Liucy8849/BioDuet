# Current separation validation — 2026-11-02

After package/path separation, all 81 offline repository tests passed both locally on Windows and on the independent Linux server checkout. This validates the separation against the existing suite; it does not establish native/model/R/browser or scientific qualification. The older results below describe their original versions.

# Engineering validation
The extracted core was built and installed in an isolated Python 3.11.13 environment, without access to the LabWeave checkout or credentials. The independent reviewer verified 55 + 6 + 20 mutually exclusive passing tests covering all 81 selected tests. This is selective repair validation, not a claim that all 81 passed in one invocation.

Failures were retained: missing ensurepip in the initial system Python; old repository-relative test resource lookup; failure event type overwritten by error metadata; and a missing scratch environment variable. The latter two source/test repairs are included. Subsequent invocations retested failures and continued previously unexecuted stages.

Both installed CLI examples completed as simulated_replay with zero model calls. No R analysis, native Agent, real-model evaluation or scientific score was performed. Formal/strict scores remain null.

The initial website installation and build used Node 20.19.5; its engine warnings are retained. Subsequent isolated validation used the official pinned Node 22.15.0 binary and the existing Chromium runtime. The declared version gate, TypeScript/Vue type checking, production build and demo-data integrity checks all passed. Twelve browser cases passed in that invocation; the remaining accessibility/mobile case initially failed because its report used a legacy repository-relative output path.

The report now uses Playwright testInfo.outputPath. A selective attempt then found no tests because an anchored filter incorrectly assumed a leaf-only test title; that attempt is retained as a failure and is not counted as a test pass. With the corrected full-title suffix filter, the one remaining case passed in 8.7 seconds: all five views had zero reported accessibility violations and all five mobile horizontal-layout assertions completed. The accepted browser set is 12 + 1 = 13 distinct cases, not 13 repeated full runs. Previously passing core tests, builds and browser cases were not repeated for these repairs.

The three website scopes were independently checked: each leader exited, its process group/cgroup was empty, and host mount information matched. This does not resolve the earlier core scope's unrecorded mount difference. The final website qualification receipt has SHA256 17e677f71ed1ec96b993ab27bd95ce996415664c8c875a082092b5d845ff5e63.

The distributed Python wheel is the exact previously qualified artifact, not a later untested rebuild: bioduet_benchmark-0.1.0a1-py3-none-any.whl, SHA256 a8b18fa6adc7595849f4de68ba0587df8fbe2d7f576dea814b37e49941bdc6f0. Its 65 packaged source files match the qualified source, and all 71 RECORD entries were checked. Later website-test and validation-document edits do not change the Python package sources.

The final scope leader was reaped, its cgroup was empty/gone, and host mount information matched. An earlier scope reported different mount information; before/after bytes were not retained, so the cause cannot be established retrospectively. That observation is not upgraded to a clean result.

Original private execution logs and failed attempts remain with the maintainers; they are not included in this public repository. The independent engineering qualification receipt has SHA256 9e45c114afc81eb41be2b1cbda213eaff44de8283b7d4203c26c9de68727f702.
