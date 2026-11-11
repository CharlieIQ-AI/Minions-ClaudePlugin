---
description: Watch a Minions task and alert me when it needs me
argument-hint: "[ticket key]"
---
Use the Minions skill's Watch tasks section for `$ARGUMENTS`.
If `$ARGUMENTS` is empty, use the task created, adopted, started or resumed most recently in this session; if there is none, ask for the ticket key.
Call `watch_tasks` with that key, and set `needToken` true unless the plugin said a watch token is already held.
Report each task's current state in one line, and say you will alert the user when it needs them.
