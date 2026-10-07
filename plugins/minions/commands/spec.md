---
description: File an already-written spec with Minions verbatim
argument-hint: [spec text or file path]
---
Use the Minions skill's File a written spec section with `$ARGUMENTS`.
If `$ARGUMENTS` is empty, ask for the spec text or file path.
Run the pre-flight and wait for the user's explicit confirmation before writing anything.
Creation requires the repo to have an assigned tracker board; `list_repos` shows it as `board`. If it is null, ask the user to assign one (or, on an Optional-mode repo, offer an internal-only task with `trackerBoard: "none"`) before filing.