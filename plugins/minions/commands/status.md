---
description: Report Minions work status
argument-hint: [ticket key]
---
Use the Minions skill to report status without changing anything.
If the key is an epic (a feature), use `get_feature` and report `phase` and `paused` first.
If `$ARGUMENTS` is present, report only that ticket; otherwise report the user's tasks.
Say when the ticket or task list has no matching work.
Keep the report read-only; if a follow-up action is requested, get explicit confirmation before writing anything.
When a task has no run in Planning, Ready for Planning Review, Ready for Dev, or Changes Requested, read get_task.dependency; if held is true, report waiting on <key> (<status>) before <stage> rather than a failure.
`get_task` lists `attachments` with each file's kind, processing state and `stages` (which agent stage receives it as text, an image file, a digest, or not at all); when a user asks whether a stage will see a file, read that rather than guessing.
