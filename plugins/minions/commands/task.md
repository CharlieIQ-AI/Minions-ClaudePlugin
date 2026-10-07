---
description: File a work request with Minions
argument-hint: [what to build]
---
Use the Minions skill to file the work described in `$ARGUMENTS`.
Treat the argument as the work to file; if it is empty, ask what work the user wants to file.
Follow the skill's filing rules and flow instead of restating them here.
Show the proposed ticket details and wait for the user's explicit confirmation before writing anything.
Creation requires the repo to have an assigned tracker board; `list_repos` shows it as `board`. If it is null, ask the user to assign one (or, on an Optional-mode repo, offer an internal-only task with `trackerBoard: "none"`) before filing.
