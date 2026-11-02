# Adapter boundary

BioDuet owns task specifications, participant-facing views, task transitions and scientific evaluation. An external application or common scientific platform is accessed through its documented API/adapter rather than imported source or a shared writable database.

This repository does not contain or require a second full scientific-platform frontend, backend or database. The score website is a benchmark website, not that platform.

The common-platform integration boundary has not been redesigned or implemented in this separation. Existing process/native utilities are development sources and are not a requirement to reproduce the earlier host-control workflow.
