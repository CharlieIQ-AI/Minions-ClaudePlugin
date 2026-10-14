---
description: Report Minions work status
argument-hint: [ticket key]
---
Use the Minions skill to report status without changing anything.
If the key is an epic (a feature), use `get_feature` and report `phase` and `paused` first.
If `$ARGUMENTS` is present, report only that ticket; otherwise report the user's tasks, and say when there is no matching work.
Read `get_task.ci`; when its state is `failing` or `pending`, name the failing checks, commit, and run URL, and say that the code host blocks the merge until CI passes. If `blocked.type` is `ci_failed`, report that blocker too; do not imply that CI auto-fix is enabled.
Keep the report read-only; if a follow-up action is requested, get explicit confirmation before writing anything.
When a task has no run in Planning, Ready for Planning Review, Ready for Dev, or Changes Requested, read get_task.dependency; if held is true, report waiting on <key> (<status>) before <stage> rather than a failure.
`get_task` lists `attachments` with each file's kind, processing state and `stages` (which agent stage receives it as text, an image file, a digest, or not at all); when a user asks whether a stage will see a file, read that rather than guessing.
