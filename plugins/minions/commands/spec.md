---
description: File an already-written spec with Minions verbatim
argument-hint: "[spec text or file path]"
---
Use the Minions skill's File a written spec section with `$ARGUMENTS`.
If `$ARGUMENTS` is empty, ask for the spec text or file path.
First ask whether this work already has a tracker ticket and wait for the answer. If it does, preview it with `preview_ticket` and get explicit confirmation to file the spec on it instead of filing a duplicate.
Run the pre-flight and wait for the user's explicit confirmation before writing anything.
File with `create_task`, `verbatimSpec: true` and the accepted text in `story`; for an existing ticket also pass its URL or key as `existingTicket` and its title as `title`. `dependsOnJiraKey` and attached `files` apply either way. When the user wants the spec built as a feature in waves on an existing ticket, follow the skill's Features section instead: `create_feature` with `existingTicket`.
Creation requires the repo to have an assigned tracker board; `list_repos` shows it as `board`. If it is null, ask the user to assign one (or, on an Optional-mode repo, offer an internal-only task with `trackerBoard: "none"`) before filing. An existing ticket cannot be filed as an internal-only task.
