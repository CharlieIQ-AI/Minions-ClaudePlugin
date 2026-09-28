---
description: Report Minions work status
argument-hint: [ticket key]
---
Use the Minions skill to report status without changing anything.
If the key is an epic (a feature), use `get_feature` and report `phase` and `paused` first.
If `$ARGUMENTS` is present, report only that ticket; otherwise report the user's tasks.
Say when the ticket or task list has no matching work.
Keep the report read-only; if a follow-up action is requested, get explicit confirmation before writing anything.
