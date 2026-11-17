---
description: Watch a Minions task or feature and alert me when it needs me
argument-hint: "[ticket key …]"
---
Use the Minions skill's Watch tasks section for `$ARGUMENTS`.
Running this command starts the plugin's watch monitor in this session.
If `$ARGUMENTS` is empty, use the task or feature created, adopted, started or resumed most recently in this session; if there is none, ask for the ticket key.
Call `watch_tasks` with those keys, and set `needToken` true unless the plugin said a watch token is held.
Report each task's or feature's current state in one line, and say you will alert the user when one needs them.
