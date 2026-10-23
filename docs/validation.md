# Engineering validation
The extracted core was built and installed in an isolated Python 3.11.13 environment, without access to the LabWeave checkout or credentials. The independent reviewer verified 55 + 6 + 20 mutually exclusive passing tests covering all 81 selected tests. This is selective repair validation, not a claim that all 81 passed in one invocation.

Failures were retained: missing ensurepip in the initial system Python; old repository-relative test resource lookup; failure event type overwritten by error metadata; and a missing scratch environment variable. The latter two source/test repairs are included. Subsequent invocations retested failures and continued previously unexecuted stages.

Both installed CLI examples completed as simulated_replay with zero model calls. No R analysis, native Agent, real-model evaluation or scientific score was performed. Formal/strict scores remain null.

Website installation and build succeeded on observed Node 20.19.5. The declared requirement is >=22.15.0 and engine warnings remain in the evidence. This is not validation on the declared Node version. Portable browser configuration is a subsequent change awaiting browser qualification.

The final scope leader was reaped, its cgroup was empty/gone, and host mount information matched. An earlier scope reported different mount information; before/after bytes were not retained, so the cause cannot be established retrospectively. That observation is not upgraded to a clean result.

Original private execution logs and failed attempts remain with the maintainers; they are not included in this public repository. The independent engineering qualification receipt has SHA256 9e45c114afc81eb41be2b1cbda213eaff44de8283b7d4203c26c9de68727f702.
