---
description: Stop watching a Minions task or feature
argument-hint: "[ticket key | all]"
---
Use the Minions skill's Watch tasks section for `$ARGUMENTS`.
If `$ARGUMENTS` is empty or `all`, call `watch_tasks` with `stop` set to `["all"]`; the plugin stops every watch on this computer.
Otherwise call `watch_tasks` with `stop` set to the keys named.
Confirm in one line which keys stopped. Stopping applies in every session.
