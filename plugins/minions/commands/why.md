---
description: Explain what happened on a Minions ticket
argument-hint: "[ticket key]"
---
Use the Minions skill's Diagnose a run section for `$ARGUMENTS`.
If `$ARGUMENTS` is empty, ask for the ticket key.
Keep the diagnosis read-only and change nothing.
`get_task` lists `attachments` with each file's kind, processing state and `stages` (which agent stage receives it as text, an image file, a digest, or not at all); when a user asks whether a stage will see a file, read that rather than guessing.
When a task is in Planning, Ready for Planning Review, Ready for Dev, or Changes Requested without a run, read get_task.dependency; if held is true, report waiting on <key> (<status>) before <stage> rather than a failure.