---
description: Merge a Minions task that is ready
argument-hint: [ticket key]
---
Use the Minions skill's Clear blocked work section for `$ARGUMENTS`.
If the key is an epic (a feature), inspect with `get_feature` and land with `merge_feature`, never `merge_task`.
If `$ARGUMENTS` is empty, ask for the ticket key.
Inspect the task first and take an action only after the user explicitly chooses it. If `get_task` reports `blocked.type` `ci_failed` or `ci.state` `failing`, do not call `merge_task`; report the failing checks and run URL instead. Do not attempt a merge until the pull-request checks have been fixed or rerun successfully.