# Operator adapter boundary

BioDuet core owns role projections, decisions, state transitions, evidence formats,
and scoring contracts. Operators own process isolation, credential delegation,
resource admission, external model/R/native execution and exact cleanup.

The integrity helpers were extracted from the accepted window module with their
function bodies unchanged: canonical encoding remains ASCII escaped, sorted,
compact JSON with nonfinite values rejected. File pins, duplicate-key rejection,
exclusive append-only output and identity checks remain intact. The original
LabWeave window module and its scope policy are untouched.

LabWeave should reference a published tag plus commit and artifact SHA256 in its
own adapter configuration. No floating main dependency, no shared deployment
paths, and no transfer of private truth or raw trajectories into this repository.
Release pin values are pending successful standalone validation and publication.
